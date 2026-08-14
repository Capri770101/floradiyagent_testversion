"""security.py —— 微信小程序登录鉴权 + JWT 签发/校验。

集成方式（替换真实小程序数据即可上线，字段见 config.py 与各 remote_*_path 端点约定）：
1. 在 .env 设置 WECHAT_APPID / WECHAT_SECRET（小程序后台获取）。
2. 设置 JWT_SECRET（自己生成的随机长串）。
3. 设置 AUTH_REQUIRED=true 开启强制鉴权。
4. 小程序端：wx.login() 拿 code → POST /auth/wx-login → 拿到 JWT →
   后续 /chat 在请求头携带 `Authorization: Bearer <jwt>`。

开发/测试阶段：AUTH_REQUIRED 默认 false，/chat 仍可用 user_id 直接调（兼容 /docs 手测）。
"""

from __future__ import annotations

import logging
import time
import uuid
from typing import Any

import httpx
import jwt
from fastapi import HTTPException, Request

from config import settings

logger = logging.getLogger("security")

#: 进程内 dev 兜底密钥：仅在未配置 JWT_SECRET 时随机生成，仅用于本地联调，切勿用于生产。
_DEV_SECRET = uuid.uuid4().hex + uuid.uuid4().hex


def _jwt_secret() -> str:
    """返回用于签名的密钥：配置了 JWT_SECRET 用配置值，否则用进程内随机兜底。"""
    return settings.jwt_secret or _DEV_SECRET


def wx_code2session(code: str) -> dict[str, Any]:
    """调用微信 code2session 用临时 code 换取 openid / session_key。

    Args:
        code: 小程序 wx.login() 返回的一次性登录凭证。

    Returns:
        微信返回的 dict，成功时含 openid / session_key / unionid；失败含 errcode / errmsg。

    Raises:
        httpx.HTTPError: 网络层错误（由调用方转成 502）。
    """
    resp = httpx.get(
        settings.wechat_code2session_url,
        params={
            "appid": settings.wechat_appid,
            "secret": settings.wechat_secret,
            "js_code": code,
            "grant_type": "authorization_code",
        },
        timeout=settings.remote_timeout,
    )
    resp.raise_for_status()
    return resp.json()


def create_token(openid: str, unionid: str | None = None) -> str:
    """为指定 openid 签发 HS256 JWT。

    Args:
        openid: 微信用户唯一标识。
        unionid: 跨应用统一标识（可选）。

    Returns:
        编码后的 JWT 字符串。
    """
    payload = {
        "openid": openid,
        "unionid": unionid,
        "iat": int(time.time()),
        "exp": int(time.time()) + settings.jwt_expire_minutes * 60,
    }
    return jwt.encode(payload, _jwt_secret(), algorithm="HS256")


def verify_token(token: str) -> str:
    """校验 JWT 并返回 openid。

    Args:
        token: 客户端携带的 JWT。

    Returns:
        openid 字符串。

    Raises:
        jwt.PyJWTError: 令牌无效/过期/签名错误。
    """
    data = jwt.decode(token, _jwt_secret(), algorithms=["HS256"])
    return str(data["openid"])


async def get_current_user(request: Request) -> str | None:
    """FastAPI 依赖：解析当前请求身份。

    - AUTH_REQUIRED=false（dev）：直接返回 None，身份由请求体 user_id 提供（兼容 /docs 手测）。
    - AUTH_REQUIRED=true：必须携带 `Authorization: Bearer <jwt>`，否则 401。

    Returns:
        openid 字符串，或 None（dev 模式）。
    """
    if not settings.auth_required:
        return None
    auth = request.headers.get("Authorization", "")
    if not auth.startswith("Bearer "):
        raise HTTPException(status_code=401, detail="缺少 Authorization Bearer 令牌")
    token = auth[len("Bearer "):].strip()
    try:
        return verify_token(token)
    except Exception as exc:  # noqa: BLE001  —— 统一成 401，不泄露具体错误
        raise HTTPException(status_code=401, detail="令牌无效或已过期") from exc
