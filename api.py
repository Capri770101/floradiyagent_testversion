"""api.py —— FastAPI 接口层。

接口：
- POST /chat            对话主接口（导购全流程）
- GET  /tasks/{task_id} 生图任务轮询
- POST /image/generate 提交生图任务（DIY 详情页「生成效果图」直连入口）
- POST /chat/reset     清空指定用户短期记忆
- GET  /health         健康检查
- GET  /tools          查看已注册工具（调试）

设计要点：
- SQLite 是同步库，所有 DB 访问走 asyncio.to_thread，避免阻塞事件循环。
- 单请求全程超时兜底（asyncio.wait_for）。
- 统一错误返回 {"code", "message"}，密钥不泄露。
- user_role 贯穿接口与 is_allowed 权限钩子（本期仅放行 user）。
"""

from __future__ import annotations

import asyncio
import logging
import re
import time
import uuid
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from pathlib import Path
from typing import Any

import httpx
from fastapi import FastAPI, HTTPException, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse, JSONResponse, RedirectResponse, Response
from pydantic import BaseModel, Field

import security
from agent import ReActAgent, is_allowed
from config import settings, setup_logging
from security import create_token, get_current_user, wx_code2session
from storage import catalog as catalog_store
from storage import commerce, repository, tasks
from storage import memory as mem_store
from storage import payment as payment_module
from storage.db import init_db
from tools import get_tool_specs

#: 进程级单例仓储（按 DATA_SOURCE 选择；含 MockRepository 的示例方案/店铺）
repo = repository.repo

setup_logging()
logger = logging.getLogger("api")

agent = ReActAgent()

#: 轻量运行时指标（进程内，重启清零；生产可换 Prometheus  exporter）
METRICS: dict[str, Any] = {"requests_total": 0, "requests_by_path": {}, "status_codes": {}}


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


@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncIterator[None]:
    init_db()
    # 确保 api2img 中转商 base64 落盘目录存在
    Path(settings.generated_dir).mkdir(parents=True, exist_ok=True)
    # 上线前配置自检：缺失关键项给出明确告警，避免「半成品」直接上线
    if settings.auth_required and not settings.auth_configured:
        logger.warning("⚠️ AUTH_REQUIRED=true 但未配置 WECHAT_APPID/WECHAT_SECRET，微信登录将返回 503")
    if settings.auth_required and not settings.jwt_secret:
        logger.warning("⚠️ AUTH_REQUIRED=true 但 JWT_SECRET 未设置，已用进程内随机密钥（重启即失效），生产务必自设")
    if settings.data_source == "remote" and not settings.remote_api_base:
        logger.warning("⚠️ DATA_SOURCE=remote 但未配置 REMOTE_API_BASE，已回退到 Mock 数据")
    if not settings.auth_required:
        logger.warning(
            "⚠️ AUTH_REQUIRED=false（开发态）：/chat 与 /image/generate 可用任意 user_id 直连，"
            "生产环境务必设 AUTH_REQUIRED=true 并自设 JWT_SECRET（否则令牌可被伪造）"
        )
    if settings.payment_provider != "sandbox" and not settings.payment_configured:
        logger.warning(
            "⚠️ PAYMENT_PROVIDER=%s 但未完整配置凭据，/pay 将返回 400；如需端到端验证请先用 PAYMENT_PROVIDER=sandbox",
            settings.payment_provider,
        )
    logger.info("=" * 64)
    logger.info("%s 启动 | LLM=%s | 生图=%s | 鉴权=%s | 数据源=%s",
                settings.app_name,
                "live" if settings.llm_enabled else "mock",
                "live" if settings.image_enabled else "mock",
                "required" if settings.auth_required else "dev",
                settings.data_source)
    logger.info("已注册工具: %s", ", ".join(t.name for t in get_tool_specs()))
    logger.info("=" * 64)
    yield


app = FastAPI(title="Flora Agent Service", version="1.0.0", lifespan=lifespan)
# CORS 安全约束：通配符 "*" 与 allow_credentials=True 在浏览器侧互斥
# （带凭证的通配符请求会被浏览器拒绝），且「任意源可带凭证」存在安全隐患。
# 因此当 origins 含 "*" 时强制关闭 credentials，避免该矛盾组合；生产环境请
# 将 CORS_ORIGINS 设为具体前端域名（逗号分隔），而非 "*"。
_allow_credentials = settings.cors_allow_credentials
if "*" in settings.cors_origins:
    _allow_credentials = False
app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.cors_origins,
    allow_credentials=_allow_credentials,
    allow_methods=["*"],
    allow_headers=["*"],
)


#: H5 前端已下线（用户要求移除），服务现为纯 API。根路径重定向到交互式
#: API 文档，便于直接调试 /chat 等端点。
@app.get("/")
async def index() -> RedirectResponse:
    """根路径重定向到 API 文档。"""
    return RedirectResponse("/docs")


@app.middleware("http")
async def request_logging(request: Request, call_next: Any) -> Any:
    request_id = uuid.uuid4().hex[:12]
    request.state.request_id = request_id
    started = time.perf_counter()
    try:
        response = await call_next(request)
    except Exception:
        logger.exception("[%s] 未捕获异常", request_id)
        raise
    elapsed = (time.perf_counter() - started) * 1000
    response.headers["X-Request-ID"] = request_id
    logger.info("[%s] %s %s -> %d (%.0fms)", request_id, request.method, request.url.path, response.status_code, elapsed)
    # 累计指标
    METRICS["requests_total"] += 1
    path = request.url.path
    METRICS["requests_by_path"][path] = METRICS["requests_by_path"].get(path, 0) + 1
    METRICS["status_codes"][response.status_code] = METRICS["status_codes"].get(response.status_code, 0) + 1
    return response


@app.exception_handler(HTTPException)
async def http_exc_handler(request: Request, exc: HTTPException) -> JSONResponse:
    return JSONResponse(status_code=exc.status_code, content={"code": exc.status_code, "message": exc.detail})


@app.exception_handler(Exception)
async def unhandled_exc_handler(request: Request, exc: Exception) -> JSONResponse:
    logger.exception("[%s] 未处理异常", getattr(request.state, "request_id", "-"))
    return JSONResponse(status_code=500, content={"code": 500, "message": "服务内部错误，请稍后重试"})


# --------------------------------------------------------------------------- #
# 路由
# --------------------------------------------------------------------------- #


@app.post("/auth/wx-login")
async def wx_login(req: WxLoginRequest) -> dict[str, Any]:
    """微信小程序登录：用临时 code 换取 openid 并签发 JWT。"""
    if not settings.auth_configured:
        raise HTTPException(
            status_code=503,
            detail="微信登录未配置：请在 .env 设置 WECHAT_APPID / WECHAT_SECRET",
        )
    try:
        info = await asyncio.to_thread(wx_code2session, req.code)
    except httpx.HTTPError as exc:
        logger.error("[wx-login] code2session 网络错误: %s", exc)
        raise HTTPException(status_code=502, detail="微信接口调用失败") from exc

    if info.get("errcode") not in (0, None):
        logger.warning("[wx-login] 微信返回错误: %s", info.get("errmsg"))
        raise HTTPException(status_code=400, detail=f"微信登录失败: {info.get('errmsg')}")
    openid = info.get("openid")
    if not openid:
        raise HTTPException(status_code=400, detail="微信未返回 openid")
    token = create_token(openid, info.get("unionid"))
    return {
        "token": token,
        "openid": openid,
        "unionid": info.get("unionid"),
        "expires_in": settings.jwt_expire_minutes * 60,
        "token_type": "Bearer",
    }


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


@app.post("/auth/register")
async def register(req: RegisterRequest) -> dict[str, Any]:
    """账号注册（非微信场景）：创建 users 行并签发 JWT。

    用户名已存在返回 409；密码过短返回 422（pydantic）或 400（业务校验）。
    """
    try:
        uid, token = security.register_user(req.username, req.password, req.nickname)
    except ValueError as exc:
        raise HTTPException(status_code=409 if "已存在" in str(exc) else 400, detail=str(exc)) from exc
    profile = security.get_user_profile(uid) or {}
    return {
        "token": token,
        "user_id": uid,
        "openid": uid,
        "nickname": profile.get("nickname", req.username),
        "expires_in": settings.jwt_expire_minutes * 60,
        "token_type": "Bearer",
    }


@app.post("/auth/login")
async def login(req: LoginRequest) -> dict[str, Any]:
    """账号登录：校验凭据并签发 JWT；失败返回 401。"""
    token = security.login_user(req.username, req.password)
    if not token:
        raise HTTPException(status_code=401, detail="用户名或密码错误")
    uid = security.verify_token(token)
    profile = security.get_user_profile(uid) or {}
    return {
        "token": token,
        "user_id": uid,
        "openid": uid,
        "nickname": profile.get("nickname", req.username),
        "expires_in": settings.jwt_expire_minutes * 60,
        "token_type": "Bearer",
    }


@app.get("/auth/me")
async def auth_me(request: Request) -> dict[str, Any]:
    """获取当前登录用户资料（需 Bearer 令牌）。"""
    uid = await get_current_user(request)
    if not uid:
        raise HTTPException(status_code=401, detail="未登录或令牌无效")
    profile = security.get_user_profile(uid)
    if not profile:
        raise HTTPException(status_code=404, detail="用户不存在")
    return {"user": profile}


@app.post("/chat")
async def chat(req: ChatRequest, request: Request) -> Any:
    """与智能体对话，跑完 ReAct + 状态机后返回结构化 UI 响应。"""
    request_id = getattr(request.state, "request_id", "-")
    # 身份解析：鉴权模式以 JWT openid 为准（忽略请求体 user_id，防冒用）；dev 模式回退 body user_id。
    user_id = await resolve_uid(request, req.user_id)
    logger.info("[%s] chat user=%s role=%s msg=%s", request_id, user_id, req.user_role, req.message[:80])

    if not is_allowed(req.user_role, "chat"):
        raise HTTPException(status_code=403, detail=f"角色 {req.user_role} 无权执行 chat")

    # 会话归属校验：若前端带了会话 ID，确认其属于该用户；否则为其新建一个会话
    sid = req.session_id
    if sid:
        conv = await asyncio.to_thread(mem_store.get_conversation, sid)
        if not conv or conv.get("user_id") != user_id:
            sid = None
    if not sid:
        sid = await asyncio.to_thread(
            mem_store.create_conversation, user_id, title=req.message[:20]
        )

    try:
        result = await asyncio.wait_for(
            agent.arun(user_id, req.message, sid, req.user_role, req.location),
            timeout=settings.request_timeout,
        )
    except TimeoutError:
        logger.error("[%s] 处理超时 >%.0fs", request_id, settings.request_timeout)
        raise HTTPException(
            status_code=504,
            detail=f"处理超时（>{settings.request_timeout:.0f}s），请简化问题后重试",
        ) from None
    except PermissionError as exc:
        raise HTTPException(status_code=403, detail=str(exc)) from exc
    except Exception as exc:  # noqa: BLE001
        logger.exception("[%s] 智能体执行失败", request_id)
        raise HTTPException(status_code=500, detail=f"智能体执行失败: {type(exc).__name__}") from exc

    # 更新会话列表预览（取用户本轮消息摘要），便于前端「类 ChatGPT」会话列表展示
    final_sid = result.session_id
    await asyncio.to_thread(mem_store.update_conversation_preview, final_sid, req.message[:60])
    return result.model_dump()


@app.get("/tasks/{task_id}")
async def get_task(task_id: str, request: Request) -> dict[str, Any]:
    """轮询生图任务结果（同步 DB 在线程池执行）。

    鉴权模式下强制校验 Bearer 令牌（dev 模式放行），防止越权轮询他人生图任务。
    """
    await get_current_user(request)
    return await asyncio.to_thread(tasks.get_image_task, task_id)


@app.post("/image/generate")
async def generate_image(req: ImageGenRequest, request: Request) -> dict[str, Any]:
    """提交生图任务（前端 DIY 详情页「生成效果图」直连入口）。

    鉴权模式下强制校验 Bearer 令牌（dev 模式放行）。立即返回 task_id，
    客户端轮询 GET /tasks/{task_id} 获取最终图片 URL。

    说明：真实 provider 的提交可能是网络调用，故放在 asyncio.to_thread 中执行，
    避免阻塞事件循环；mock 模式则直接落本地占位图并立即 done。
    """
    await get_current_user(request)
    task_id = await asyncio.to_thread(tasks.create_image_task, req.prompt)
    return {"task_id": task_id, "status": "submitted", "poll": f"/tasks/{task_id}"}


@app.get("/generated/{filename}")
async def serve_generated(filename: str) -> FileResponse:
    """托管 api2img 中转商生成的本地图片（base64 落盘产物）。

    仅允许安全文件名，且路径必须严格落在 generated_dir 内，杜绝目录穿越。
    """
    if not re.fullmatch(r"[A-Za-z0-9_.\-]+", filename):
        raise HTTPException(status_code=400, detail="非法文件名")
    root = Path(settings.generated_dir).resolve()
    path = (root / filename).resolve()
    if path.parent != root or not path.is_file():
        raise HTTPException(status_code=404, detail="图片不存在")
    return FileResponse(path)


@app.post("/chat/reset")
async def reset(req: ResetRequest, request: Request) -> dict[str, Any]:
    """清空短期记忆（会话与消息），便于测试。

    - conversation_id 给定：仅清该会话（会话级重置）。
    - 否则：清该用户最近的一个会话。
    鉴权模式下身份以 JWT openid 为准，忽略请求体 user_id，防止越权清他人会话；
    dev 模式沿用请求体 user_id（兼容本地手测）。
    """
    if not is_allowed(req.user_role, "reset"):
        raise HTTPException(status_code=403, detail=f"角色 {req.user_role} 无权执行 reset")
    openid = await get_current_user(request)
    user_id = openid or req.user_id
    ok = await asyncio.to_thread(mem_store.reset_session, user_id, req.conversation_id)
    return {"user_id": user_id, "reset": ok}


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


@app.get("/conversations")
async def list_conversations(request: Request, user_id: str | None = None) -> dict[str, Any]:
    """列出某用户的全部会话（按最近活跃倒序）。"""
    uid = await resolve_uid(request, user_id)
    if not uid:
        raise HTTPException(status_code=401, detail="缺少用户身份")
    convs = await asyncio.to_thread(mem_store.list_conversations, uid)
    return {"conversations": convs}


@app.post("/conversations")
async def create_conversation(req: CreateConvRequest, request: Request) -> dict[str, Any]:
    """新建会话，返回会话 ID。"""
    uid = await resolve_uid(request, req.user_id)
    if not uid:
        raise HTTPException(status_code=401, detail="缺少用户身份")
    cid = await asyncio.to_thread(mem_store.create_conversation, uid, req.title or "新对话")
    return {"conversation_id": cid, "id": cid}


@app.get("/conversations/{conv_id}/messages")
async def get_conversation_messages(conv_id: str, request: Request, user_id: str | None = None) -> dict[str, Any]:
    """获取会话内消息（user/assistant，含 ui/data），供前端历史回放。

    归属校验：鉴权模式下会话须属于当前令牌用户，防止越权读取他人对话历史。
    """
    uid = await resolve_uid(request, user_id)
    if uid:
        conv = await asyncio.to_thread(mem_store.get_conversation, conv_id)
        if not conv or conv.get("user_id") != uid:
            raise HTTPException(status_code=404, detail="会话不存在")
    msgs = await asyncio.to_thread(mem_store.load_display_messages, conv_id)
    return {"messages": msgs}


@app.patch("/conversations/{conv_id}")
async def rename_conversation(conv_id: str, req: RenameConvRequest, request: Request) -> dict[str, Any]:
    """重命名会话标题。"""
    uid = await resolve_uid(request, req.user_id)
    if uid:
        conv = await asyncio.to_thread(mem_store.get_conversation, conv_id)
        if not conv or conv.get("user_id") != uid:
            raise HTTPException(status_code=404, detail="会话不存在")
    ok = await asyncio.to_thread(mem_store.rename_conversation, conv_id, req.title)
    if not ok:
        raise HTTPException(status_code=404, detail="会话不存在")
    return {"ok": True}


@app.delete("/conversations/{conv_id}")
async def delete_conversation(conv_id: str, request: Request, user_id: str | None = None) -> dict[str, Any]:
    """删除会话（级联清消息与控制标记）。"""
    uid = await resolve_uid(request, user_id)
    if uid:
        conv = await asyncio.to_thread(mem_store.get_conversation, conv_id)
        if not conv or conv.get("user_id") != uid:
            raise HTTPException(status_code=404, detail="会话不存在")
    ok = await asyncio.to_thread(mem_store.delete_conversation, conv_id)
    if not ok:
        raise HTTPException(status_code=404, detail="会话不存在")
    return {"ok": True}


@app.get("/health")
async def health() -> dict[str, Any]:
    return {
        "status": "ok",
        "llm_mode": "live" if settings.llm_enabled else "mock",
        "image_mode": "live" if settings.image_enabled else "mock",
        "auth": "required" if settings.auth_required else "dev",
        "data_source": settings.data_source,
        "rag_enabled": settings.rag_enabled,
        "tools": len(get_tool_specs()),
    }


@app.get("/metrics")
async def metrics() -> dict[str, Any]:
    """轻量运行时指标 + 配置快照（接入 Prometheus 前先用这个看板）。"""
    return {
        "requests_total": METRICS["requests_total"],
        "requests_by_path": METRICS["requests_by_path"],
        "status_codes": METRICS["status_codes"],
        "config": {
            "llm_mode": "live" if settings.llm_enabled else "mock",
            "image_mode": "live" if settings.image_enabled else "mock",
            "auth": "required" if settings.auth_required else "dev",
            "data_source": settings.data_source,
            "rag_enabled": settings.rag_enabled,
            "rag_top_k": settings.rag_top_k,
            "tools": len(get_tool_specs()),
        },
    }


@app.get("/tools")
async def list_tools() -> dict[str, Any]:
    return {
        "count": len(get_tool_specs()),
        "tools": [
            {"name": t.name, "description": t.description, "parameters": t.parameters, "tags": list(t.tags)}
            for t in get_tool_specs()
        ],
    }


# --------------------------------------------------------------------------- #
# 电商接口（方案 / 店铺 / 购物车 / 订单 / 支付）
# 说明：方案与店铺数据来自 storage.repository.repo（默认 MockRepository，含示例
# 数据；DATA_SOURCE=remote 时自动切真实后端），购物车/订单/支付走 SQLite 持久化。
# H5 通过 /api 代理访问，本服务路由不带 /api 前缀。
# --------------------------------------------------------------------------- #


def _plan_card(p: dict[str, Any]) -> dict[str, Any]:
    """把仓储方案映射成 H5 列表卡所需字段。"""
    return {
        "id": p["plan_id"],
        "name": p["name"],
        "price": p["price"],
        "merchant_name": p.get("merchant_name", ""),  # 透传给商品详情/加购/下单
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


def _shop_card(s: dict[str, Any]) -> dict[str, Any]:
    return {
        "id": s["shop_id"],
        "name": s["name"],
        "rating": str(s.get("rating", "4.8")),
        "dist": f"{s.get('distance_km')}km",
        "eta": "配送约30分钟",
        "price_range": s.get("price_range", ""),
    }


def _shop_full(s: dict[str, Any]) -> dict[str, Any]:
    plans = [repo.get_plan(pid) for pid in s.get("plan_ids", [])]
    recommend = [
        {"id": p["plan_id"], "name": p["name"], "price": p["price"]}
        for p in plans
        if p
    ]
    return {
        "id": s["shop_id"],
        "name": s["name"],
        "rating": str(s.get("rating", "4.8")),
        "status": "营业中",
        "dist": f"{s.get('distance_km')}km",
        "intro": "专注鲜花定制与同城速递，包装精致、准时送达。",
        "recommend": recommend,
    }


@app.get("/plans")
async def list_plans(keyword: str = "") -> dict[str, Any]:
    """浏览/搜索方案（空关键词 = 全部）。"""
    plans = await asyncio.to_thread(repo.search_plans, keyword)
    return {"plans": [_plan_card(p) for p in plans]}


@app.get("/plans/{plan_id}")
async def plan_detail(plan_id: str) -> dict[str, Any]:
    p = await asyncio.to_thread(repo.get_plan, plan_id)
    if not p:
        raise HTTPException(status_code=404, detail="方案不存在")
    return {"plan": _plan_full(p)}


@app.get("/shops")
async def list_shops_endpoint() -> dict[str, Any]:
    shops = await asyncio.to_thread(repo.list_shops, None)
    return {"shops": [_shop_card(s) for s in shops]}


@app.get("/shops/{shop_id}")
async def shop_detail_endpoint(shop_id: str) -> dict[str, Any]:
    s = await asyncio.to_thread(repo.get_shop, shop_id)
    if not s:
        raise HTTPException(status_code=404, detail="店铺不存在")
    return {"shop": _shop_full(s)}


# --------------------------------------------------------------------------- #
# 管理后台（方案 / 店铺 CRUD）
# 权限：仅 admin 角色可访问；未登录 401，非管理员 403（users.role 字段，
# 用 `python cli.py make-admin <username>` 授予管理员角色）。
# --------------------------------------------------------------------------- #


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


@app.get("/admin/plans")
async def admin_list_plans(request: Request) -> dict[str, Any]:
    """后台管理列表：返回全字段方案（含 style/category_id）。"""
    await _require_admin(request)
    return {"plans": await asyncio.to_thread(catalog_store.list_plans)}


@app.post("/admin/plans")
async def admin_create_plan(req: PlanWriteRequest, request: Request) -> dict[str, Any]:
    await _require_admin(request)
    p = await asyncio.to_thread(catalog_store.create_plan, req.model_dump(exclude_none=True))
    return {"plan": p}


@app.put("/admin/plans/{plan_id}")
async def admin_update_plan(plan_id: str, req: PlanWriteRequest, request: Request) -> dict[str, Any]:
    await _require_admin(request)
    p = await asyncio.to_thread(
        catalog_store.update_plan, plan_id, req.model_dump(exclude_none=True)
    )
    if not p:
        raise HTTPException(status_code=404, detail="方案不存在")
    return {"plan": p}


@app.delete("/admin/plans/{plan_id}")
async def admin_delete_plan(plan_id: str, request: Request) -> dict[str, Any]:
    await _require_admin(request)
    if not await asyncio.to_thread(catalog_store.delete_plan, plan_id):
        raise HTTPException(status_code=404, detail="方案不存在")
    return {"ok": True}


@app.get("/admin/shops")
async def admin_list_shops(request: Request) -> dict[str, Any]:
    """后台管理列表：返回全字段店铺（含 plan_ids 关联）。"""
    await _require_admin(request)
    return {"shops": await asyncio.to_thread(catalog_store.list_shops)}


@app.post("/admin/shops")
async def admin_create_shop(req: ShopWriteRequest, request: Request) -> dict[str, Any]:
    await _require_admin(request)
    s = await asyncio.to_thread(catalog_store.create_shop, req.model_dump(exclude_none=True))
    return {"shop": s}


@app.put("/admin/shops/{shop_id}")
async def admin_update_shop(shop_id: str, req: ShopWriteRequest, request: Request) -> dict[str, Any]:
    await _require_admin(request)
    s = await asyncio.to_thread(
        catalog_store.update_shop, shop_id, req.model_dump(exclude_none=True)
    )
    if not s:
        raise HTTPException(status_code=404, detail="店铺不存在")
    return {"shop": s}


@app.delete("/admin/shops/{shop_id}")
async def admin_delete_shop(shop_id: str, request: Request) -> dict[str, Any]:
    await _require_admin(request)
    if not await asyncio.to_thread(catalog_store.delete_shop, shop_id):
        raise HTTPException(status_code=404, detail="店铺不存在")
    return {"ok": True}


@app.get("/cart")
async def get_cart(request: Request, user_id: str | None = None) -> dict[str, Any]:
    """查看某用户购物车。"""
    uid = await resolve_uid(request, user_id)
    if not uid:
        raise HTTPException(status_code=401, detail="缺少用户身份")
    items = await asyncio.to_thread(commerce.list_cart, uid)
    return {"items": items}


@app.post("/cart")
async def post_cart(req: CartAddRequest, request: Request) -> dict[str, Any]:
    uid = await resolve_uid(request, req.user_id)
    if not uid:
        raise HTTPException(status_code=401, detail="缺少用户身份")
    item = await asyncio.to_thread(
        commerce.add_to_cart, uid, req.plan_id, req.name, req.price, req.shop
    )
    return {"item": item}


@app.put("/cart/{item_id}")
async def put_cart(item_id: str, req: CartUpdateRequest) -> dict[str, Any]:
    item = await asyncio.to_thread(commerce.update_cart_item, item_id, req.qty, req.selected)
    if not item:
        raise HTTPException(status_code=404, detail="购物车项不存在")
    return {"item": item}


@app.delete("/cart/{item_id}")
async def del_cart(item_id: str) -> dict[str, Any]:
    ok = await asyncio.to_thread(commerce.remove_cart_item, item_id)
    return {"ok": ok}


@app.post("/orders")
async def post_order(req: OrderCreateRequest, request: Request) -> dict[str, Any]:
    uid = await resolve_uid(request, req.user_id)
    if not uid:
        raise HTTPException(status_code=401, detail="缺少用户身份")
    order = await asyncio.to_thread(
        commerce.create_order,
        uid,
        [it.model_dump() for it in req.items],
        req.recipient,
        req.delivery,
        req.note,
        req.address_id,
    )
    return {"order": order}


@app.get("/orders")
async def list_orders_endpoint(request: Request, user_id: str | None = None) -> dict[str, Any]:
    """列出某用户全部订单（新→旧，含物流时间线）。"""
    uid = await resolve_uid(request, user_id)
    if not uid:
        raise HTTPException(status_code=401, detail="缺少用户身份")
    orders = await asyncio.to_thread(commerce.list_orders, uid)
    return {"orders": orders}


@app.get("/coupons")
async def list_coupons_endpoint(request: Request, user_id: str | None = None) -> dict[str, Any]:
    """列出用户优惠券（新用户自动发放新人立减券）。"""
    uid = await resolve_uid(request, user_id)
    if not uid:
        raise HTTPException(status_code=401, detail="缺少用户身份")
    coupons = await asyncio.to_thread(commerce.list_coupons, uid)
    return {"coupons": coupons}


@app.get("/points")
async def points_endpoint(request: Request, user_id: str | None = None) -> dict[str, Any]:
    """查询用户积分余额与流水。"""
    uid = await resolve_uid(request, user_id)
    if not uid:
        raise HTTPException(status_code=401, detail="缺少用户身份")
    points = await asyncio.to_thread(commerce.get_points, uid)
    return points


# --------------------------------------------------------------------------- #
# 收货地址
# --------------------------------------------------------------------------- #


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


@app.get("/addresses")
async def list_addresses_endpoint(request: Request, user_id: str | None = None) -> dict[str, Any]:
    """列出用户收货地址（默认排前）。"""
    uid = await resolve_uid(request, user_id)
    if not uid:
        raise HTTPException(status_code=401, detail="缺少用户身份")
    return {"addresses": await asyncio.to_thread(commerce.list_addresses, uid)}


@app.post("/addresses")
async def post_address(req: AddressWriteRequest, request: Request) -> dict[str, Any]:
    uid = await resolve_uid(request, None)
    if not uid:
        raise HTTPException(status_code=401, detail="缺少用户身份")
    a = await asyncio.to_thread(
        commerce.add_address, uid, req.name, req.phone, req.address, req.is_default
    )
    return {"address": a}


@app.put("/addresses/{addr_id}")
async def put_address(addr_id: str, req: AddressPatchRequest, request: Request) -> dict[str, Any]:
    uid = await resolve_uid(request, None)
    if not uid:
        raise HTTPException(status_code=401, detail="缺少用户身份")
    a = await asyncio.to_thread(
        commerce.update_address, addr_id, uid, req.name, req.phone, req.address, req.is_default
    )
    if not a:
        raise HTTPException(status_code=404, detail="地址不存在")
    return {"address": a}


@app.delete("/addresses/{addr_id}")
async def del_address(addr_id: str, request: Request) -> dict[str, Any]:
    uid = await resolve_uid(request, None)
    if not uid:
        raise HTTPException(status_code=401, detail="缺少用户身份")
    if not await asyncio.to_thread(commerce.delete_address, addr_id, uid):
        raise HTTPException(status_code=404, detail="地址不存在")
    return {"ok": True}


# --------------------------------------------------------------------------- #
# 收藏
# --------------------------------------------------------------------------- #


class FavoriteRequest(BaseModel):
    plan_id: str = Field(..., min_length=1, max_length=64)


@app.get("/favorites")
async def list_favorites_endpoint(request: Request, user_id: str | None = None) -> dict[str, Any]:
    """列出收藏（含方案信息，新→旧）。"""
    uid = await resolve_uid(request, user_id)
    if not uid:
        raise HTTPException(status_code=401, detail="缺少用户身份")
    items = await asyncio.to_thread(commerce.list_favorites, uid)
    return {"favorites": items, "count": len(items)}


@app.post("/favorites")
async def post_favorite(req: FavoriteRequest, request: Request) -> dict[str, Any]:
    uid = await resolve_uid(request, None)
    if not uid:
        raise HTTPException(status_code=401, detail="缺少用户身份")
    await asyncio.to_thread(commerce.add_favorite, uid, req.plan_id)
    return {"ok": True, "favorited": True}


@app.delete("/favorites/{plan_id}")
async def del_favorite(plan_id: str, request: Request) -> dict[str, Any]:
    uid = await resolve_uid(request, None)
    if not uid:
        raise HTTPException(status_code=401, detail="缺少用户身份")
    await asyncio.to_thread(commerce.remove_favorite, uid, plan_id)
    return {"ok": True, "favorited": False}


@app.get("/favorites/{plan_id}/status")
async def favorite_status(plan_id: str, request: Request, user_id: str | None = None) -> dict[str, Any]:
    """查询某方案是否已收藏（商品详情页心形按钮状态）。"""
    uid = await resolve_uid(request, user_id)
    if not uid:
        raise HTTPException(status_code=401, detail="缺少用户身份")
    return {"plan_id": plan_id, "favorited": await asyncio.to_thread(commerce.is_favorite, uid, plan_id)}


# --------------------------------------------------------------------------- #
# 商家端（店铺维度经营数据 / 代发货）
# 权限：仅 merchant / admin 角色可访问（users.role 字段）。
# --------------------------------------------------------------------------- #


async def _require_merchant(request: Request) -> str:
    """商家校验：必须携带有效 JWT 且角色为 merchant 或 admin，否则 401/403。"""
    uid = security.resolve_strict(request)
    role = await asyncio.to_thread(security.get_user_role, uid)
    if role not in ("merchant", "admin"):
        raise HTTPException(status_code=403, detail="需要商家权限")
    return uid


@app.get("/merchant/stats")
async def merchant_stats_endpoint(request: Request, shop_id: str = "") -> dict[str, Any]:
    """店铺维度经营统计（订单 / GMV / 待发货 / 已完成 / 评价）。"""
    await _require_merchant(request)
    return await asyncio.to_thread(commerce.merchant_stats, shop_id)


@app.get("/merchant/orders")
async def merchant_orders_endpoint(
    request: Request, shop_id: str = "", status: str = "", limit: int = 50
) -> dict[str, Any]:
    """商家视角订单列表（任意用户，可按店铺 / 状态过滤）。"""
    await _require_merchant(request)
    return {"orders": await asyncio.to_thread(commerce.merchant_orders, shop_id, status, limit)}


@app.post("/merchant/orders/{order_id}/ship")
async def merchant_ship_endpoint(order_id: str, request: Request) -> dict[str, Any]:
    """商家代发货（不受订单归属限制）：paid -> shipped。"""
    await _require_merchant(request)
    try:
        o = await asyncio.to_thread(commerce.merchant_ship, order_id)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    if not o:
        raise HTTPException(status_code=404, detail="订单不存在")
    return {"order": o}


@app.get("/merchant/reviews")
async def merchant_reviews_endpoint(request: Request, shop_id: str = "") -> dict[str, Any]:
    """店铺维度评价列表。"""
    await _require_merchant(request)
    return {"reviews": await asyncio.to_thread(commerce.merchant_reviews, shop_id)}


@app.get("/orders/{order_id}")
async def get_order_endpoint(order_id: str, request: Request, user_id: str | None = None) -> dict[str, Any]:
    uid = await resolve_uid(request, user_id)
    await _assert_order_owner(order_id, uid)
    o = await asyncio.to_thread(commerce.get_order, order_id)
    if not o:
        raise HTTPException(status_code=404, detail="订单不存在")
    return {"order": o}


@app.patch("/orders/{order_id}")
async def patch_order(order_id: str, req: OrderPatchRequest, request: Request) -> dict[str, Any]:
    """更新订单收货信息（收货人 / 配送时间 / 备注），仅订单主人可改，且只能改传入字段。"""
    uid = await resolve_uid(request, None)
    await _assert_order_owner(order_id, uid)
    o = await asyncio.to_thread(
        commerce.update_order, order_id, req.recipient, req.delivery, req.note
    )
    if not o:
        raise HTTPException(status_code=404, detail="订单不存在")
    return {"order": o}


class OrderActionRequest(BaseModel):
    action: str = Field(..., description="ship | complete | cancel", pattern="^(ship|complete|cancel)$")


@app.post("/orders/{order_id}/action")
async def order_action_endpoint(
    order_id: str, req: OrderActionRequest, request: Request
) -> dict[str, Any]:
    """订单状态流转（物流模拟）：发货 / 签收 / 取消，仅订单主人可操作。"""
    uid = await resolve_uid(request, None)
    await _assert_order_owner(order_id, uid)
    try:
        if req.action == "ship":
            o = await asyncio.to_thread(commerce.ship_order, order_id)
        elif req.action == "complete":
            o = await asyncio.to_thread(commerce.complete_order, order_id)
        else:
            o = await asyncio.to_thread(commerce.cancel_order, order_id)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    if not o:
        raise HTTPException(status_code=404, detail="订单不存在")
    return {"order": o}


@app.post("/pay")
async def pay_endpoint(req: PayRequest, request: Request) -> dict[str, Any]:
    """发起支付：按配置渠道（默认 sandbox）调统一下单，返回前端拉起支付所需参数。

    微信返回 ``pay.pay_params`` 即 ``wx.requestPayment`` 入参；支付宝返回 ``pay_params.pay_url``
    供前端跳转。真实网关返回的 ``paid`` 为 False，待 ``/pay/notify/{provider}`` 回调确认。
    """
    uid = await resolve_uid(request, None)
    await _assert_order_owner(req.order_id, uid)
    extra = {}
    if req.openid:
        extra["openid"] = req.openid
    if req.description:
        extra["description"] = req.description
    try:
        result = await asyncio.to_thread(commerce.pay_order, req.order_id, req.method, extra)
    except payment_module.PaymentConfigError as exc:
        # 真实渠道凭据未配置：明确 400，避免「半成品」上线
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    except payment_module.PaymentGatewayError as exc:
        raise HTTPException(status_code=502, detail=str(exc)) from exc
    if not result:
        raise HTTPException(status_code=404, detail="订单不存在")
    return {"pay": result}


@app.post("/pay/notify/{provider}")
async def pay_notify(provider: str, request: Request) -> Response:
    """支付回调（微信 v3 / 支付宝）。验签解密通过后标记订单已支付。

    微信期望返回 ``200 + {"code":"SUCCESS","message":"成功"}``；支付宝期望返回纯文本 ``success``。
    验签失败返回渠道约定的「重试」响应（微信 FAIL / 支付宝 failure）。
    """
    try:
        prov = payment_module.get_provider(provider)
    except payment_module.PaymentConfigError as exc:
        logger.warning("[pay/notify] 渠道未配置: %s", exc)
        if provider == "alipay":
            return Response(content="failure", media_type="text/plain")
        return JSONResponse(status_code=400, content={"code": "FAIL", "message": str(exc)})

    body = await request.body()
    headers = dict(request.headers)
    try:
        result = await asyncio.to_thread(prov.verify_notify, body, headers)
    except Exception:  # noqa: BLE001
        logger.exception("[pay/notify] 验签异常 provider=%s", provider)
        result = None

    if result is None:
        # 无法验签：要求渠道重试（不标记订单）
        if provider == "alipay":
            return Response(content="failure", media_type="text/plain")
        return JSONResponse(status_code=400, content={"code": "FAIL", "message": "验签失败"})

    if result.paid:
        await asyncio.to_thread(commerce.mark_order_paid, result.order_id, result.transaction_id)
    # 返回渠道约定的成功响应
    if provider == "alipay":
        return Response(content="success", media_type="text/plain")
    return JSONResponse(content={"code": "SUCCESS", "message": "成功"})


@app.get("/pay/{order_id}/status")
async def pay_status(order_id: str, request: Request, user_id: str | None = None) -> dict[str, Any]:
    """查询订单支付状态（客户端轮询兜底，用于回调不可达场景）。"""
    uid = await resolve_uid(request, user_id)
    await _assert_order_owner(order_id, uid)
    st = await asyncio.to_thread(commerce.get_payment_status, order_id)
    if not st:
        raise HTTPException(status_code=404, detail="订单不存在")
    return st


# --------------------------------------------------------------------------- #
# 评价
# --------------------------------------------------------------------------- #


class ReviewRequest(BaseModel):
    order_id: str = Field(..., min_length=1, max_length=64)
    rating: int = Field(..., ge=1, le=5, description="1-5 星")
    content: str = Field("", max_length=500, description="评价内容（选填）")


@app.post("/reviews")
async def post_review(req: ReviewRequest, request: Request) -> dict[str, Any]:
    """订单完成后写评价：仅订单主人 + 已签收订单；同单重复评价即更新。"""
    uid = await resolve_uid(request, None)
    if not uid:
        raise HTTPException(status_code=401, detail="缺少用户身份")
    try:
        rev = await asyncio.to_thread(commerce.create_review, uid, req.order_id, req.rating, req.content)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    return {"review": rev}


@app.get("/reviews")
async def list_reviews_endpoint(plan_id: str = "") -> dict[str, Any]:
    """公开查询方案评价列表（商品详情页展示）。"""
    return {"reviews": await asyncio.to_thread(commerce.list_reviews, plan_id)}


if __name__ == "__main__":
    import uvicorn

    uvicorn.run("api:app", host=settings.api_host, port=settings.api_port, reload=settings.debug, log_level=settings.log_level.lower())
