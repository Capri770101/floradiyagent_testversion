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

from fastapi import HTTPException, Request
from pydantic import BaseModel, Field

import security
from agent import ReActAgent
from config import settings
from security import get_current_user
from storage import catalog as catalog_store
from storage import commerce, repository

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




class CartUpdateRequest(BaseModel):
    qty: int | None = Field(None, ge=1, description="新的数量（>=1）")
    selected: bool | None = Field(None, description="是否勾选结算")




class OrderItem(BaseModel):
    plan_id: str
    name: str
    price: float = Field(ge=0)
    qty: int = Field(1, ge=1)
    shop: str | None = None
    item_id: str | None = Field(None, description="来自购物车的项 id（下单后移除该项）")




class OrderCreateRequest(BaseModel):
    user_id: str | None = Field(None, min_length=1, max_length=64, description="鉴权模式下可省略，由 JWT 解析")
    items: list[OrderItem]
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
        "merchant_name": p.get("merchant_name", ""),  # 透传给商品详情/加购/下单
        "shop_id": catalog_store.plan_shop_id(p["plan_id"]),  # 商品对应的店家（跳转店铺页）
        "label": _plan_label(p),  # Premium / Limited / New 角标
        "rating": "4.8",
        "sold": 200 + (abs(hash(p["plan_id"])) % 300),
        "tags": p.get("tags", []),
        "desc": p.get("desc", ""),
        "image": None,  # H5 用占位色块渲染，不依赖真实图
    }




def _plan_full(p: dict[str, Any]) -> dict[str, Any]:
    """方案详情（商品详情页）。"""
    base = _plan_card(p)
    base["detail"] = p.get("desc", "")
    base["aiReason"] = f"根据你的需求，这束「{p['name']}」{p.get('desc', '')}"
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
        "min_delivery": (int(float(s.get("price_range", "0").split("-")[0])) // 10 * 10)
        if s.get("price_range") and s["price_range"].split("-")[0].strip().isdigit()
        else 30,
        "delivery_fee": 3 if float(s.get("distance_km") or 1) <= 1 else 5 if float(s.get("distance_km") or 1) <= 2.5 else 8,
    }




def _shop_menu_item(p: dict[str, Any]) -> dict[str, Any]:
    """店铺详情菜单项（美团式商品卡字段）。

    sales 为演示推导值（与列表页 sold 同思路）：真实上线后应由订单数据统计。
    """
    return {
        "id": p["plan_id"],
        "name": p["name"],
        "price": p["price"],
        "desc": p.get("desc", ""),
        "tags": p.get("tags", []),
        "style": p.get("style", ""),
        "image": p.get("effect_image_url"),
        "label": _plan_label(p),
        "sales": 100 + (abs(hash(p["plan_id"])) % 900),
    }




def _shop_full(s: dict[str, Any]) -> dict[str, Any]:
    """店铺详情（美团外卖式）：经营信息 + 分类菜单（左栏分类 / 右栏商品）。

    以下字段为演示推导值（基于现有真实字段稳定生成，零迁移）：
    min_delivery / delivery_fee / hours / address / notice；真实上线应由商家后台维护。
    """
    plans = [p for p in (repo.get_plan(pid) for pid in s.get("plan_ids", [])) if p]
    # 分类菜单：按 categories 排序分组，未分类的兜底到「其他」
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

    # 经营信息推导
    m = re.match(r"\s*(\d+)\s*-\s*(\d+)\s*", str(s.get("price_range", "")))
    lo = float(m.group(1)) if m else None
    d = float(s.get("distance_km") or 1.0)
    delivery_fee = 3 if d <= 1 else 5 if d <= 2.5 else 8
    min_delivery = (int(lo) // 10 * 10) if lo else 30
    zone = "盐田"
    z = re.search(r"\((.+?)店\)", str(s.get("name", "")))
    if z:
        zone = z.group(1)
    addr_no = 8 + (abs(hash(s.get("shop_id", ""))) % 88)

    return {
        "id": s["shop_id"],
        "name": s["name"],
        "rating": str(s.get("rating", "4.8")),
        "status": "营业中",
        "dist": f"{s.get('distance_km')}km",
        "intro": s.get("intro", "专注鲜花定制与同城速递，包装精致、准时送达。"),
        # 美团式经营信息（演示推导值）
        "sales": 200 + (abs(hash(s.get("shop_id", ""))) % 800),   # 月售
        "min_delivery": min_delivery,                             # 起送价（元）
        "delivery_fee": delivery_fee,                             # 配送费（元）
        "delivery_time": "约30分钟",
        "hours": "09:00 - 21:00",
        "address": f"深圳市{zone}区海景路 {addr_no} 号（示例地址）",
        "notice": s.get("intro", "专注鲜花定制与同城速递，包装精致、准时送达。"),
        # 分类菜单
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
    """商家校验：必须携带有效 JWT 且角色为 merchant 或 admin，否则 401/403。"""
    uid = security.resolve_strict(request)
    role = await asyncio.to_thread(security.get_user_role, uid)
    if role not in ("merchant", "admin"):
        raise HTTPException(status_code=403, detail="需要商家权限")
    return uid




class OrderActionRequest(BaseModel):
    action: str = Field(..., description="ship | complete | cancel", pattern="^(ship|complete|cancel)$")




class ReviewRequest(BaseModel):
    order_id: str = Field(..., min_length=1, max_length=64)
    rating: int = Field(..., ge=1, le=5, description="1-5 星")
    content: str = Field("", max_length=500, description="评价内容（选填）")


