"""api.py —— FastAPI 接口层。

接口：
- POST /chat            对话主接口（导购全流程）
- GET  /tasks/{task_id} 生图任务轮询
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
from fastapi.responses import FileResponse, JSONResponse, RedirectResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel, Field

from agent import ReActAgent, is_allowed
from config import settings, setup_logging
from security import create_token, get_current_user, wx_code2session
from storage import memory as mem_store
from storage import tasks
from storage.db import init_db
from tools import get_tool_specs

setup_logging()
logger = logging.getLogger("api")

agent = ReActAgent()

#: 轻量运行时指标（进程内，重启清零；生产可换 Prometheus  exporter）
METRICS: dict[str, Any] = {"requests_total": 0, "requests_by_path": {}, "status_codes": {}}


# --------------------------------------------------------------------------- #
# 请求模型
# --------------------------------------------------------------------------- #


class ChatRequest(BaseModel):
    user_id: str = Field(..., min_length=1, max_length=64, description="用户唯一标识（正式环境为微信 openid）")
    message: str = Field(..., min_length=1, max_length=4000, description="用户消息")
    session_id: str | None = Field(None, description="可选，不传则服务端生成")
    user_role: str = Field("user", description="user | merchant | admin（本期仅 user）")
    location: dict[str, float] | None = Field(None, description="可选，{lat, lng} 用于距离计算")


class ResetRequest(BaseModel):
    user_id: str = Field(..., min_length=1, max_length=64)
    user_role: str = "user"


class WxLoginRequest(BaseModel):
    code: str = Field(..., min_length=1, max_length=128, description="wx.login() 返回的一次性登录凭证 code")


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


#: H5 前端（ChatResponse 的可视化 Renderer）。纯静态文件，与 /chat 同源，
#: 避免跨域；生产可改为独立 CDN/对象存储，只要 CORS_ORIGINS 配好即可。
_H5_DIR = Path(__file__).resolve().parent / "h5"
if _H5_DIR.exists():
    app.mount("/h5", StaticFiles(directory=str(_H5_DIR), html=True), name="h5")

    @app.get("/")
    async def index() -> RedirectResponse:
        """根路径重定向到 H5 入口。"""
        return RedirectResponse("/h5/")


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


@app.post("/chat")
async def chat(req: ChatRequest, request: Request) -> Any:
    """与智能体对话，跑完 ReAct + 状态机后返回结构化 UI 响应。"""
    request_id = getattr(request.state, "request_id", "-")
    # 身份解析：开启强制鉴权时取 JWT 中的 openid；否则沿用请求体 user_id（dev 模式）。
    openid = await get_current_user(request)
    user_id = openid or req.user_id
    logger.info("[%s] chat user=%s role=%s msg=%s", request_id, user_id, req.user_role, req.message[:80])

    if not is_allowed(req.user_role, "chat"):
        raise HTTPException(status_code=403, detail=f"角色 {req.user_role} 无权执行 chat")

    try:
        result = await asyncio.wait_for(
            agent.arun(user_id, req.message, req.session_id, req.user_role, req.location),
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

    return result.model_dump()


@app.get("/tasks/{task_id}")
async def get_task(task_id: str, request: Request) -> dict[str, Any]:
    """轮询生图任务结果（同步 DB 在线程池执行）。

    鉴权模式下强制校验 Bearer 令牌（dev 模式放行），防止越权轮询他人生图任务。
    """
    await get_current_user(request)
    return await asyncio.to_thread(tasks.get_image_task, task_id)


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
    """清空指定用户的短期记忆（会话与消息），便于测试。

    鉴权模式下身份以 JWT openid 为准，忽略请求体 user_id，防止越权清他人会话；
    dev 模式沿用请求体 user_id（兼容本地手测）。
    """
    if not is_allowed(req.user_role, "reset"):
        raise HTTPException(status_code=403, detail=f"角色 {req.user_role} 无权执行 reset")
    openid = await get_current_user(request)
    user_id = openid or req.user_id
    ok = await asyncio.to_thread(mem_store.reset_session, user_id)
    return {"user_id": user_id, "reset": ok}


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


if __name__ == "__main__":
    import uvicorn

    uvicorn.run("api:app", host=settings.api_host, port=settings.api_port, reload=settings.debug, log_level=settings.log_level.lower())
