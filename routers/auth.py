"""routers/auth.py —— 认证（微信/手机号/账号登录）（api.py 拆分，2026-08 重构）。"""
from __future__ import annotations

import asyncio
import logging
from typing import Any

import httpx
from fastapi import APIRouter, HTTPException, Request

import security
from config import settings
from routers.common import (  # noqa: F401  # 共享单例/辅助（按需使用）
    METRICS,
    LoginRequest,
    PhoneCodeRequest,
    PhoneLoginRequest,
    RegisterRequest,
    WxBindRequest,
    WxLoginRequest,
    _assert_order_owner,
    _check_rate,
    _client_ip,
    _limiter,
    agent,
    catalog_store,
    repo,
    resolve_uid,
)
from security import get_current_user, wx_code2session

router = APIRouter(tags=["auth"])
logger = logging.getLogger("api")


def _reject_admin(uid: str) -> None:
    """C 端登录接口拒绝管理员角色：管理员只能走管理后台 /auth/admin-login。"""
    if security.get_user_role(uid) == "admin":
        raise HTTPException(status_code=403, detail="管理员账号请使用管理后台登录")

@router.post("/auth/wx-login")
async def wx_login(req: WxLoginRequest, request: Request) -> dict[str, Any]:
    """微信小程序登录：用临时 code 换取 openid 并签发 JWT。"""
    _check_rate(f"auth:{_client_ip(request)}", settings.rate_limit_auth_per_minute)
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
    # 自动建档：openid 无对应 users 行时创建（id=openid），保证 /auth/me 与业务表可用
    uid, token, is_new = security.wx_login_user(openid, info.get("nickname"))
    _reject_admin(uid)
    profile = security.get_user_profile(uid) or {}
    return {
        "token": token,
        "user_id": uid,
        "openid": openid,
        "unionid": info.get("unionid"),
        "nickname": profile.get("nickname") or "微信用户",
        "is_new": is_new,
        "expires_in": settings.jwt_expire_minutes * 60,
        "token_type": "Bearer",
    }



@router.post("/auth/phone-code")
async def phone_code(req: PhoneCodeRequest) -> dict[str, Any]:
    """手机号验证码：dev 模式不真实发送（固定验证码见 .env SMS_DEV_CODE，默认 123456）。

    限流：每手机号每分钟 N 次（防短信轰炸）。
    """
    _check_rate(f"phone_code:{req.phone}", settings.rate_limit_phone_per_minute)
    code = security.issue_phone_code(req.phone)
    logger.info("[phone-code] phone=%s dev_mode=%s", req.phone, settings.sms_provider == "dev")
    return {
        "ok": True,
        "dev_code": code if settings.sms_provider == "dev" else None,
        "ttl_seconds": settings.phone_code_ttl_seconds,
    }



@router.post("/auth/phone-login")
async def phone_login(req: PhoneLoginRequest) -> dict[str, Any]:
    """手机号验证码登录/注册：验证码通过后自动登录（无账号则一键注册）。

    限流：每手机号每分钟 N 次（防暴力撞 6 位验证码）。
    """
    _check_rate(f"phone_login:{req.phone}", settings.rate_limit_phone_login_per_minute)
    if not security.verify_phone_code(req.phone, req.code):
        raise HTTPException(status_code=401, detail="验证码错误或已过期")
    try:
        uid, token, is_new = security.phone_login_user(req.phone)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    _reject_admin(uid)
    profile = security.get_user_profile(uid) or {}
    return {
        "token": token,
        "user_id": uid,
        "openid": uid,
        "nickname": profile.get("nickname") or req.phone,
        "phone": req.phone,
        "is_new": is_new,
        "expires_in": settings.jwt_expire_minutes * 60,
        "token_type": "Bearer",
    }



@router.post("/auth/wx-bind")
async def wx_bind(req: WxBindRequest, request: Request) -> dict[str, Any]:
    """微信绑定：把当前登录账号与微信 openid 绑定（同一微信后续可直接微信登录）。

    调用时机：已登录用户在微信内打开页面 → wx.login() 拿 code → 本接口。
    """
    uid = await get_current_user(request)
    if not uid:
        raise HTTPException(status_code=401, detail="未登录或令牌无效")
    if not settings.auth_configured:
        raise HTTPException(
            status_code=503,
            detail="微信绑定未配置：请在 .env 设置 WECHAT_APPID / WECHAT_SECRET",
        )
    try:
        info = await asyncio.to_thread(wx_code2session, req.code)
    except httpx.HTTPError as exc:
        logger.error("[wx-bind] code2session 网络错误: %s", exc)
        raise HTTPException(status_code=502, detail="微信接口调用失败") from exc
    if info.get("errcode") not in (0, None):
        raise HTTPException(status_code=400, detail=f"微信绑定失败: {info.get('errmsg')}")
    openid = info.get("openid")
    if not openid:
        raise HTTPException(status_code=400, detail="微信未返回 openid")
    try:
        security.bind_wechat(uid, openid)
    except ValueError as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc
    return {"ok": True, "openid": openid}



@router.post("/auth/register")
async def register(req: RegisterRequest, request: Request) -> dict[str, Any]:
    """账号注册（非微信场景）：创建 users 行并签发 JWT。

    用户名已存在返回 409；密码过短返回 422（pydantic）或 400（业务校验）。
    """
    _check_rate(f"auth:{_client_ip(request)}", settings.rate_limit_auth_per_minute)
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



@router.post("/auth/login")
async def login(req: LoginRequest, request: Request) -> dict[str, Any]:
    """C 端账号登录：校验凭据并签发 JWT；失败返回 401。

    管理员角色拒绝登录 C 端（403）——管理员请走管理后台 /auth/admin-login。
    """
    _check_rate(f"auth:{_client_ip(request)}", settings.rate_limit_auth_per_minute)
    token = security.login_user(req.username, req.password)
    if not token:
        raise HTTPException(status_code=401, detail="用户名或密码错误")
    uid = security.verify_token(token)
    _reject_admin(uid)
    profile = security.get_user_profile(uid) or {}
    return {
        "token": token,
        "user_id": uid,
        "openid": uid,
        "nickname": profile.get("nickname", req.username),
        "expires_in": settings.jwt_expire_minutes * 60,
        "token_type": "Bearer",
    }



@router.post("/auth/admin-login")
async def admin_login(req: LoginRequest, request: Request) -> dict[str, Any]:
    """管理后台登录：校验凭据并要求 role=admin，否则 403（C 端用户无法登录后台）。"""
    _check_rate(f"auth:{_client_ip(request)}", settings.rate_limit_auth_per_minute)
    token = security.login_user(req.username, req.password)
    if not token:
        raise HTTPException(status_code=401, detail="用户名或密码错误")
    uid = security.verify_token(token)
    if security.get_user_role(uid) != "admin":
        raise HTTPException(status_code=403, detail="该账号不是管理员，无法进入后台")
    profile = security.get_user_profile(uid) or {}
    return {
        "token": token,
        "user_id": uid,
        "openid": uid,
        "nickname": profile.get("nickname", req.username),
        "expires_in": settings.jwt_expire_minutes * 60,
        "token_type": "Bearer",
    }



@router.get("/auth/me")
async def auth_me(request: Request) -> dict[str, Any]:
    """获取当前登录用户资料（需 Bearer 令牌）。

    未登录/令牌无效时返回 200 + user=null（而非 401），
    让前端把「未登录」视为正常状态，避免每次挂载刷出 401 控制台噪音。
    """
    uid = await get_current_user(request)
    if not uid:
        return {"user": None}
    profile = security.get_user_profile(uid)
    if not profile:
        return {"user": None}
    return {"user": profile}


