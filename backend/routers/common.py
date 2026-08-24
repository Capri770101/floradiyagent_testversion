"""routers/common.py —— 路由共享层：单例、限流器、身份解析、序列化辅助、请求模型。

从 api.py 拆分而来（2026-08 重构），保持符号与行为完全一致。
"""
from __future__ import annotations

import asyncio
import re
import threading
import time
from collections import deque
from typing import Any

import backend.security as security
from agent.agent import ReActAgent
from backend.config import settings
from backend.security import get_current_user
from backend.storage import catalog as catalog_store
from backend.storage import commerce, repository
from fastapi import HTTPException, Request
from pydantic import BaseModel, Field

#: 进程级单例仓储（按 DATA_SOURCE 选择；含 MockRepository 的示例方案/店铺）
repo = repository.repo

agent = ReActAgent()

#: 轻量运行时指标（进程内，重启清零；生产可换 Prometheus  exporter）
METRICS: dict[str, Any] = {"requests_total": 0, "requests_by_path": {}, "status_codes": {}}


class SlidingWindowLimiter:
    """按 key 的滑动窗口计数：窗口内请求数 ≥ limit 则拒绝（返回 False）。

    仅用于单进程部署；多 worker 需换 Redis（接口不变）。
    """



    def __init__(self) -> None:
        self._hits: dict[str, deque[float]] = {}
        self._lock = threading.Lock()



    def allow(self, key: str, limit: int, window: float = 60.0) -> bool:
        if limit <= 0:
            return False
        now = time.monotonic()
        with self._lock:
            dq = self._hits.setdefault(key, deque())
            while dq and now - dq[0] > window:
                dq.popleft()
            if len(dq) >= limit:
                return False
            dq.append(now)
            return True


_limiter = SlidingWindowLimiter()





def _client_ip(request: Request) -> str:
    """取客户端 IP（透传 X-Forwarded-For 时取第一个值）。"""
    xff = request.headers.get("X-Forwarded-For", "")
    if xff:
        return xff.split(",")[0].strip()
    return request.client.host if request.client else "unknown"





def _check_rate(key: str, limit: int, window: float = 60.0) -> None:
    """限流检查：超限抛 429（HTTPException 由统一 handler 转 JSON）。"""
    if settings.rate_limit_enabled and not _limiter.allow(key, limit, window):
        raise HTTPException(status_code=429, detail="请求过于频繁，请稍后再试")


# --------------------------------------------------------------------------- #
# 请求模型
# --------------------------------------------------------------------------- #





class ChatRequest(BaseModel):
    user_id: str | None = Field(None, min_length=1, max_length=64, description="用户唯一标识（鉴权模式下以 JWT 为准，可不传）")
    message: str = Field(..., min_length=1, max_length=4000, description="用户消息")
    session_id: str | None = Field(None, description="可选，不传则服务端生成")
    user_role: str = Field("user", description="user | merchant | admin（本期仅 user）")
    location: dict[str, float] | None = Field(None, description="可选，{lat, lng} 用于距离计算")





class ResetRequest(BaseModel):
    user_id: str | None = Field(None, min_length=1, max_length=64)
    user_role: str = "user"
    conversation_id: str | None = Field(None, description="可选：仅重置该会话；不传则重置最近一个会话")





class CreateConvRequest(BaseModel):
    user_id: str | None = Field(None, min_length=1, max_length=64, description="鉴权模式下以 JWT 为准，可不传")
    title: str | None = Field(None, description="会话标题（留空则由首条消息自动生成）")





class RenameConvRequest(BaseModel):
    user_id: str | None = Field(None, min_length=1, max_length=64, description="鉴权模式下以 JWT 为准，可不传")
    title: str = Field(..., min_length=1, max_length=50, description="新会话标题")





class WxLoginRequest(BaseModel):
    code: str = Field(..., min_length=1, max_length=128, description="wx.login() 返回的一次性登录凭证 code")





class RegisterRequest(BaseModel):
    username: str = Field(..., min_length=2, max_length=32, description="登录名（唯一）")
    password: str = Field(..., min_length=6, max_length=64, description="明文密码（仅本次哈希，不落库）")
    nickname: str | None = Field(None, max_length=32, description="展示昵称（可选）")





class LoginRequest(BaseModel):
    username: str = Field(..., min_length=1, max_length=32)
    password: str = Field(..., min_length=1, max_length=64)





class MerchantRegisterRequest(BaseModel):
    phone: str = Field(..., min_length=6, max_length=20, description="手机号（全局唯一，作为商家登录账号）")
    password: str = Field(..., min_length=6, max_length=64, description="明文密码（仅本次哈希，不落库）")
    shop_name: str | None = Field(None, max_length=30, description="店铺名（可选，默认 商家+尾号）")





class PhoneCodeRequest(BaseModel):
    phone: str = Field(..., min_length=6, max_length=20, description="手机号（dev 模式不真实发送，验证码见 settings.sms_dev_code）")





class PhoneLoginRequest(BaseModel):
    phone: str = Field(..., min_length=6, max_length=20, description="手机号")
    code: str = Field(..., min_length=4, max_length=8, description="短信验证码")





class WxBindRequest(BaseModel):
    code: str = Field(..., min_length=1, max_length=128, description="wx.login() 返回的一次性登录凭证 code")


# --------------------------------------------------------------------------- #
# 电商请求模型（购物车 / 订单 / 支付）
# --------------------------------------------------------------------------- #





class CartAddRequest(BaseModel):
    user_id: str = Field(..., min_length=1, max_length=64)
    plan_id: str = Field(..., min_length=1, max_length=64)
    name: str = Field(..., min_length=1, max_length=128)
    price: float = Field(..., ge=0)
    shop: str | None = Field(None, description="商家名（用于购物车按店归类展示）")


class CartMergeRequest(BaseModel):
    from_user_id: str = Field(..., min_length=1, max_length=64, description="来源用户（游客匿名 uid）")




class CartUpdateRequest(BaseModel):
    qty: int | None = Field(None, ge=1, description="新的数量（>=1）")
    selected: bool | None = Field(None, description="是否勾选结算")




class OrderItem(BaseModel):
    plan_id: str
    name: str
    price: float = Field(ge=0)
    qty: int = Field(1, ge=1, le=99, description="单商品数量上限 99，防超量下单")
    shop: str | None = None
    item_id: str | None = Field(None, description="来自购物车的项 id（下单后移除该项）")





class OrderCreateRequest(BaseModel):
    user_id: str | None = Field(None, min_length=1, max_length=64, description="鉴权模式下可省略，由 JWT 解析")
    items: list[OrderItem] = Field(..., min_length=1, description="至少 1 件商品，拒绝空订单")
    recipient: dict[str, Any] | None = None
    delivery: str | None = None
    note: str | None = None
    address_id: str | None = Field(None, description="已存收货地址 id；传了则忽略 recipient 字段")




class PayRequest(BaseModel):
    order_id: str = Field(..., min_length=1, max_length=64)
    method: str = Field("wechat", description="wechat | alipay | union | huabei")
    openid: str | None = Field(None, description="微信 JSAPI 必填：支付用户 openid（来自 wx.login/jwt）")
    description: str | None = Field(None, description="订单描述（支付凭证展示）")




class OrderPatchRequest(BaseModel):
    recipient: dict[str, Any] | None = Field(None, description="{name, phone, address} 任意子集")
    delivery: str | None = Field(None, description="配送时间描述")
    note: str | None = Field(None, description="订单备注")




class ImageGenRequest(BaseModel):
    prompt: str = Field(
        ...,
        min_length=1,
        max_length=2000,
        description="生图提示词：DIY 方案的 effect_prompt 或自定义描述",
    )


# --------------------------------------------------------------------------- #
# 生命周期 & 中间件
# --------------------------------------------------------------------------- #





async def resolve_uid(request: Request, body_user_id: str | None = None) -> str | None:
    """解析当前请求归属的用户 ID。

    - 鉴权模式下：以 JWT 中的 openid 为准（令牌存在时忽略请求体 user_id，杜绝越权冒用他人数据）。
    - dev 模式（AUTH_REQUIRED=false，get_current_user 返回 None）：回退到请求体/查询的 user_id，
      兼容 /docs 手测与 H5 匿名 uid 流程。

    Returns:
        用户 ID 字符串，或 None（dev 模式且无可解析身份）。
    """
    token_uid = await get_current_user(request)
    if token_uid:
        return token_uid
    return body_user_id





async def _assert_order_owner(order_id: str, uid: str | None) -> None:
    """订单归属校验：令牌身份存在时，订单必须属于该用户，否则 403。

    dev 模式（uid 为 None）跳过——兼容匿名 uid 直接调接口的验证场景。
    """
    if not uid:
        return
    order = await asyncio.to_thread(commerce.get_order, order_id)
    if not order or order.get("user_id") != uid:
        raise HTTPException(status_code=403, detail="无权访问该订单")


# --------------------------------------------------------------------------- #
# 多会话管理（前端「类 ChatGPT」会话列表 / 新建 / 切换 / 删除 / 历史回放）
# --------------------------------------------------------------------------- #




def _plan_label(p: dict[str, Any]) -> str:
    """Maison 稀缺角标（参考稿 §5）：Premium=金色实底 / Limited=酒红描边 / New=砂色底。"""
    price = p.get("price") or 0
    if price >= 300:
        return "Premium"
    if price >= 150:
        return "Limited"
    return "New"




def _plan_card(p: dict[str, Any]) -> dict[str, Any]:
    """把仓储方案映射成 H5 列表卡所需字段。"""
    return {
        "id": p["plan_id"],
        "name": p["name"],
        "price": p["price"],
        "merchant_name": p.get("merchant_name", ""),
        "shop_id": catalog_store.plan_shop_id(p["plan_id"]),
        "label": _plan_label(p),
        "rating": str(p.get("rating", 4.8)),
        "sold": int(p.get("sold", 0)),
        "tags": p.get("tags", []),
        "desc": p.get("desc", ""),
        "image": p.get("effect_image_url"),
    }



#: 花材识别词表：从商品 desc 第一句提取花材（DIY 详情页花材清单用）
_FLOWER_HINTS = (
    "康乃馨", "玫瑰", "向日葵", "满天星", "郁金香", "牡丹", "百合", "绣球",
    "芍药", "雏菊", "洋桔梗", "尤加利叶", "绿萝", "永生花", "竹", "香槟",
)


def _derive_flowers(p: dict[str, Any]) -> list[str]:
    """从 desc 第一句（"11 支粉色康乃馨 + 满天星，适合…"）解析花材名列表。"""
    desc = p.get("desc", "")
    head = re.split(r"[，,。]", desc)[0] if desc else ""
    out: list[str] = []
    for token in re.split(r"[+、/]|\s+", head):
        t = re.sub(r"^[\d\s支朵枝盆棵个]*", "", token).strip()
        if t and any(h in t for h in _FLOWER_HINTS):
            out.append(t)
    return out


def _derive_packaging(p: dict[str, Any]) -> str:
    """按商品名推断包装形式（礼盒/花篮/盆栽/插花，其余纸包）。"""
    name = p.get("name", "")
    if any(k in name for k in ("礼盒", "花盒")):
        return "礼盒装（丝绒质感内衬）"
    if "花篮" in name:
        return "花篮装（藤编提篮）"
    if "盆栽" in name:
        return "白瓷盆栽"
    if "插花" in name:
        return "竹器插花"
    return "简约纸包（品牌定制雾面纸）"


def _plan_full(p: dict[str, Any]) -> dict[str, Any]:
    """方案详情（商品详情页 / DIY 详情直链兜底）。"""
    base = _plan_card(p)
    base["detail"] = p.get("desc", "")
    base["aiReason"] = p.get("ai_reason") or f"根据你的需求，这束「{p['name']}」{p.get('desc', '')}"
    base["main_flowers"] = p.get("main_flowers") or _derive_flowers(p)
    base["packaging"] = p.get("packaging") or _derive_packaging(p)
    base["effect_image_url"] = p.get("effect_image_url")
    base["style"] = p.get("style")
    return base




def _shop_card(s: dict[str, Any], location: dict[str, float] | None = None) -> dict[str, Any]:
    """店铺列表卡；传入定位时按真实经纬度计算展示距离（否则用静态 distance_km）。"""
    d = s.get("distance_km")
    if location and s.get("lat") is not None and s.get("lng") is not None:
        d = catalog_store.distance_km(location["lat"], location["lng"], s["lat"], s["lng"])
    return {
        "id": s["shop_id"],
        "name": s["name"],
        "rating": str(s.get("rating", "4.8")),
        "dist": f"{d:.1f}km" if isinstance(d, float) else f"{d}km",
        "eta": "配送约30分钟",
        "price_range": s.get("price_range", ""),
        "min_delivery": float(s.get("min_delivery") or (
            (int(float(s.get("price_range", "0").split("-")[0])) // 10 * 10)
            if s.get("price_range") and s["price_range"].split("-")[0].strip().isdigit()
            else 30
        )),
        "delivery_fee": float(s.get("delivery_fee") or (
            3 if float(s.get("distance_km") or 1) <= 1 else 5 if float(s.get("distance_km") or 1) <= 2.5 else 8
        )),
        "image": s.get("image") or "",
    }




def _shop_menu_item(p: dict[str, Any]) -> dict[str, Any]:
    """店铺详情菜单项（美团式商品卡字段）。"""
    return {
        "id": p["plan_id"],
        "name": p["name"],
        "price": p["price"],
        "desc": p.get("desc", ""),
        "tags": p.get("tags", []),
        "style": p.get("style", ""),
        "image": p.get("effect_image_url"),
        "label": _plan_label(p),
        "sales": int(p.get("sold", 0)),
    }




def _shop_full(s: dict[str, Any]) -> dict[str, Any]:
    """店铺详情（美团外卖式）：经营信息 + 分类菜单（左栏分类 / 右栏商品）。"""
    plans = [p for p in (repo.get_plan(pid) for pid in s.get("plan_ids", [])) if p]
    cats = catalog_store.list_categories()
    cat_map = {c["id"]: c["name"] for c in cats}
    menu: list[dict[str, Any]] = []
    for c in cats:
        items = [p for p in plans if p.get("category_id") == c["id"]]
        if items:
            menu.append({"id": c["id"], "name": c["name"], "items": [_shop_menu_item(p) for p in items]})
    others = [p for p in plans if p.get("category_id") not in cat_map]
    if others:
        menu.append({"id": "cat_other", "name": "其他", "items": [_shop_menu_item(p) for p in others]})

    return {
        "id": s["shop_id"],
        "name": s["name"],
        "rating": str(s.get("rating", "4.8")),
        "status": "营业中",
        "distance_km": float(s.get("distance_km") or 0),
        "intro": s.get("intro", "专注鲜花定制与同城速递，包装精致、准时送达。"),
        "sales": int(s.get("sales", 0)),
        "min_delivery": float(s.get("min_delivery") or 30),
        "delivery_fee": float(s.get("delivery_fee") or 5),
        "delivery_time": s.get("delivery_time") or "30分钟",
        "hours": s.get("hours") or "09:00 - 21:00",
        "address": s.get("address") or "深圳市盐田区海景路 1 号（示例地址）",
        "notice": s.get("notice") or s.get("intro", "专注鲜花定制与同城速递，包装精致、准时送达。"),
        "image": s.get("image") or "",
        "cover": s.get("cover") or "",
        "logo": s.get("logo") or "",
        "menu": menu,
        "recommend": [
            {"id": p["plan_id"], "name": p["name"], "price": p["price"]}
            for p in plans
        ],
    }




async def _require_admin(request: Request) -> str:
    """管理员校验：必须携带有效 JWT 且用户角色为 admin，否则 401/403。"""
    uid = security.resolve_strict(request)
    role = await asyncio.to_thread(security.get_user_role, uid)
    if role != "admin":
        raise HTTPException(status_code=403, detail="需要管理员权限")
    return uid




class PlanWriteRequest(BaseModel):
    plan_id: str | None = Field(None, max_length=30)
    name: str | None = Field(None, max_length=60)
    price: float | None = Field(None, ge=0)
    desc: str | None = Field(None, max_length=200)
    merchant_name: str | None = Field(None, max_length=30)
    style: str | None = Field(None, max_length=20)
    category_id: str | None = Field(None, max_length=30)
    tags: list[str] | str | None = None
    effect_image_url: str | None = None



class ShopWriteRequest(BaseModel):
    shop_id: str | None = Field(None, max_length=30)
    name: str | None = Field(None, max_length=40)
    rating: float | None = Field(None, ge=0, le=5)
    distance_km: float | None = Field(None, ge=0)
    price_range: str | None = Field(None, max_length=30)
    lat: float | None = None
    lng: float | None = None
    status: str | None = Field(None, max_length=10)
    intro: str | None = Field(None, max_length=120)
    image: str | None = Field(None, max_length=200)
    cover: str | None = Field(None, max_length=200)
    logo: str | None = Field(None, max_length=200)
    hours: str | None = Field(None, max_length=30)
    address: str | None = Field(None, max_length=120)
    notice: str | None = Field(None, max_length=200)
    plan_ids: list[str] | str | None = None



class AddressWriteRequest(BaseModel):
    name: str = Field(..., min_length=1, max_length=32, description="收货人")
    phone: str = Field(..., min_length=5, max_length=20, description="手机号")
    address: str = Field(..., min_length=1, max_length=120, description="详细地址")
    is_default: bool = False



class AddressPatchRequest(BaseModel):
    name: str | None = Field(None, min_length=1, max_length=32)
    phone: str | None = Field(None, min_length=5, max_length=20)
    address: str | None = Field(None, min_length=1, max_length=120)
    is_default: bool | None = None



class FavoriteRequest(BaseModel):
    plan_id: str = Field(..., min_length=1, max_length=64)




async def _require_merchant(request: Request) -> str:
    """商家校验：必须携带有效 JWT 且角色为 merchant，否则 401/403。"""
    uid = security.resolve_strict(request)
    role = await asyncio.to_thread(security.get_user_role, uid)
    if role != "merchant":
        raise HTTPException(status_code=403, detail="需要商家权限")
    return uid


async def _merchant_scope(request: Request) -> tuple[str, list[str]]:
    """商家身份 + 可管理店铺范围（绑定店铺 id 列表；未绑定返回空列表——严格隔离）。"""
    uid = await _require_merchant(request)
    shop_ids = await asyncio.to_thread(catalog_store.merchant_shop_ids, uid)
    return uid, shop_ids


def _require_shop_in_scope(
    shop_id: str, scope: list[str] | None
) -> None:
    """校验 shop_id 在商家可管理范围内（admin 不受限），否则 403。"""
    if scope is not None and shop_id not in scope:
        raise HTTPException(status_code=403, detail="无权操作该店铺")




class OrderActionRequest(BaseModel):
    action: str = Field(..., description="ship | complete | cancel", pattern="^(ship|complete|cancel)$")



class ReviewRequest(BaseModel):
    order_id: str = Field(..., min_length=1, max_length=64)
    rating: int = Field(..., ge=1, le=5, description="1-5 星")
    content: str = Field("", max_length=500, description="评价内容（选填）")
