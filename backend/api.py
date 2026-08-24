"""api.py —— FastAPI 应用装配层。

2026-08 重构：63 条路由按领域拆分到 routers/（auth/chat/catalog/commerce/
merchant/admin），本文件仅保留：应用创建、CORS、中间件、异常处理、lifespan、
根路径重定向，并挂载全部路由。

设计要点：
- SQLite 是同步库，所有 DB 访问走 asyncio.to_thread，避免阻塞事件循环。
- 单请求全程超时兜底（asyncio.wait_for）。
- 统一错误返回 {"code", "message"}，密钥不泄露。
- 共享单例/限流器/身份解析/序列化辅助在 routers/common.py。
"""

from __future__ import annotations

import logging
import uuid
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from pathlib import Path
from typing import Any

from agent.tools import get_tool_specs
from fastapi import FastAPI, HTTPException, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse, RedirectResponse
from fastapi.staticfiles import StaticFiles

from backend.config import settings, setup_logging
from backend.routers import (
    admin,
    auth,
    catalog,
    chat,
    chats,
    commerce,
    merchant,
    notify,
    recommend,
    report,
)
from backend.routers.common import (  # noqa: F401  # api._limiter 供测试引用
    METRICS,
    _limiter,
    agent,
    repo,
)
from backend.security import wx_code2session  # noqa: F401  # 测试 mock 点（api.wx_code2session）
from backend.storage.db import init_db

setup_logging()
logger = logging.getLogger("api")


# --------------------------------------------------------------------------- #
# 生命周期 & 中间件
# --------------------------------------------------------------------------- #


@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncIterator[None]:
    init_db()
    # 确保 api2img 中转商 base64 落盘目录存在
    Path(settings.generated_dir).mkdir(parents=True, exist_ok=True)
    # 生产环境 fail-fast 断言：缺 JWT_SECRET 或未强制鉴权一律拒绝启动（IMPROVEMENT_PROPOSAL P1）
    if settings.app_env == "prod":
        missing = []
        if not settings.jwt_secret:
            missing.append("JWT_SECRET")
        if not settings.auth_required:
            missing.append("AUTH_REQUIRED=true")
        if missing:
            raise RuntimeError(
                "生产环境（APP_ENV=prod）启动校验失败，缺少: ", ", ".join(missing)
                + "。请先在 misc/.env 配置后再启动。"
            )
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


#: 本服务为纯 API（H5 为独立前端，由 Vite 构建后单独部署，不在此挂载）。
#: 根路径重定向到交互式 API 文档，便于直接调试 /chat 等端点。
@app.get("/")
async def index() -> RedirectResponse:
    """根路径重定向到 API 文档。"""
    return RedirectResponse("/docs")


@app.middleware("http")
async def request_logging(request: Request, call_next: Any) -> Any:
    request_id = uuid.uuid4().hex[:12]
    request.state.request_id = request_id
    started = __import__("time").perf_counter()
    try:
        response = await call_next(request)
    except Exception:
        logger.exception("[%s] 未捕获异常", request_id)
        raise
    elapsed = (__import__("time").perf_counter() - started) * 1000
    response.headers["X-Request-ID"] = request_id
    logger.info("[%s] %s %s -> %d (%.0fms)", request_id, request.method, request.url.path, response.status_code, elapsed)
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
# 路由挂载（各领域见 routers/）
# --------------------------------------------------------------------------- #

app.include_router(auth.router)
app.include_router(chat.router)
app.include_router(chats.router)
app.include_router(catalog.router)
app.include_router(commerce.router)
app.include_router(merchant.router)
app.include_router(admin.router)
app.include_router(notify.router)
app.include_router(report.router)
app.include_router(recommend.router)

# 商家上传图片静态托管（/uploads/m*.jpg → data/uploads/）
Path(settings.upload_dir).mkdir(parents=True, exist_ok=True)
app.mount("/uploads", StaticFiles(directory=settings.upload_dir), name="uploads")

# 生成图静态托管（/generated/plan_*.png → data/generated/）
Path(settings.generated_dir).mkdir(parents=True, exist_ok=True)
app.mount("/generated", StaticFiles(directory=settings.generated_dir), name="generated")


if __name__ == "__main__":
    import uvicorn

    uvicorn.run("backend.api:app", host=settings.api_host, port=settings.api_port, reload=settings.debug, log_level=settings.log_level.lower())
