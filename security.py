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

import hashlib
import logging
import secrets
import time
import uuid
from datetime import UTC, datetime
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
    auth = request.headers.get("Authorization", "")
    token = auth[len("Bearer "):].strip() if auth.startswith("Bearer ") else None
    if token:
        # 鉴权模式或 dev 模式，只要带有效令牌就以令牌身份为准（dev 下仍可被校验）
        try:
            return verify_token(token)
        except Exception as exc:  # noqa: BLE001
            if settings.auth_required:
                raise HTTPException(status_code=401, detail="令牌无效或已过期") from exc
            return None
    # 无令牌
    if settings.auth_required:
        raise HTTPException(status_code=401, detail="缺少 Authorization Bearer 令牌")
    return None


def resolve_strict(request: Request) -> str:
    """严格身份解析：必须携带有效 JWT，否则 401。

    用于管理/商家等需要「真实身份」的端点——不随 AUTH_REQUIRED 开关放行，
    杜绝匿名/占位身份写入或读取管理数据。
    """
    auth = request.headers.get("Authorization", "")
    token = auth[len("Bearer "):].strip() if auth.startswith("Bearer ") else None
    if not token:
        raise HTTPException(status_code=401, detail="需要登录")
    try:
        return verify_token(token)
    except Exception as exc:  # noqa: BLE001
        raise HTTPException(status_code=401, detail="令牌无效或已过期") from exc


def get_user_role(user_id: str) -> str:
    """读取用户角色（默认 user）。"""
    from storage.db import get_conn

    conn = get_conn()
    row = conn.execute("SELECT role FROM users WHERE id = ?", (user_id,)).fetchone()
    return str(row["role"]) if row and row["role"] else "user"


def set_user_role(user_id: str, role: str) -> bool:
    """设置用户角色（user | merchant | admin）；用户不存在返回 False。"""
    from storage.db import get_conn

    if role not in ("user", "merchant", "admin"):
        raise ValueError(f"非法角色: {role}")
    conn = get_conn()
    cur = conn.execute("UPDATE users SET role=? WHERE id=?", (role, user_id))
    conn.commit()
    return cur.rowcount > 0


# --------------------------------------------------------------------------- #
# 账号密码体系（非微信场景：H5 本地注册/登录，用于验证期与自有小程序账号）
# 密码使用 pbkdf2_hmac(SHA256) + 随机 salt 存储，不依赖任何第三方库；明文永不落库。
# --------------------------------------------------------------------------- #


def _hash_password(password: str) -> str:
    """pbkdf2 哈希密码，返回 `pbkdf2$<salt_hex>$<dk_hex>` 格式的可存储串。"""
    salt = secrets.token_hex(16)
    dk = hashlib.pbkdf2_hmac("sha256", password.encode("utf-8"), bytes.fromhex(salt), 100_000)
    return f"pbkdf2${salt}${dk.hex()}"


def _verify_password(password: str, stored: str) -> bool:
    """校验明文密码与存储串是否匹配（恒定时间比较，防时序攻击）。"""
    try:
        algo, salt, expected = stored.split("$")
    except ValueError:
        return False
    if algo != "pbkdf2":
        return False
    dk = hashlib.pbkdf2_hmac("sha256", password.encode("utf-8"), bytes.fromhex(salt), 100_000)
    return secrets.compare_digest(dk.hex(), expected)


def register_user(username: str, password: str, nickname: str | None = None) -> tuple[str, str]:
    """注册账号：创建 users 行并签发 JWT。

    Args:
        username: 登录名（唯一）。
        password: 明文密码（仅在此次调用内哈希，不落库）。
        nickname: 展示昵称（可选，默认同 username）。

    Returns:
        (user_id, token)。

    Raises:
        ValueError: 用户名/密码为空或用户名已存在。
    """
    from storage.db import get_conn, transaction

    username = (username or "").strip()
    if not username or not password:
        raise ValueError("用户名和密码不能为空")
    if len(password) < 6:
        raise ValueError("密码至少 6 位")
    conn = get_conn()
    if conn.execute("SELECT id FROM users WHERE username = ?", (username,)).fetchone():
        raise ValueError("用户名已存在")
    uid = "u_" + uuid.uuid4().hex[:12]
    now = datetime.now(UTC).isoformat(timespec="seconds")
    # 明文密码只在本次调用内哈希，绝不落库（防拖库爆明文）
    pw_hash = _hash_password(password)
    with transaction() as c:
        c.execute(
            "INSERT INTO users(id, openid, username, nickname, password_hash, created_at, updated_at) "
            "VALUES (?,?,?,?,?,?,?)",
            (uid, uid, username, nickname or username, pw_hash, now, now),
        )
    return uid, create_token(uid)


def login_user(username: str, password: str) -> str | None:
    """账号登录：校验凭据并签发 JWT；失败返回 None。

    Args:
        username: 登录名。
        password: 明文密码。

    Returns:
        JWT 字符串，或 None（用户名不存在 / 密码错误 / 未设密码）。
    """
    from storage.db import get_conn

    conn = get_conn()
    row = conn.execute(
        "SELECT id, password_hash FROM users WHERE username = ?", (username.strip(),)
    ).fetchone()
    if not row or not row["password_hash"]:
        return None
    if not _verify_password(password, row["password_hash"]):
        return None
    return create_token(row["id"])


def get_user_profile(user_id: str) -> dict[str, Any] | None:
    """读取用户资料（不含敏感字段，含角色）。"""
    from storage.db import get_conn

    conn = get_conn()
    row = conn.execute(
        "SELECT id, username, nickname, avatar, phone, role, created_at FROM users WHERE id = ?",
        (user_id,),
    ).fetchone()
    return dict(row) if row else None


# --------------------------------------------------------------------------- #
# 手机号注册/登录（验证码）+ 微信绑定
# --------------------------------------------------------------------------- #

#: 验证码内存存储：phone -> (code, expires_at)。单进程够用；多实例部署应换 Redis/DB。
_PHONE_CODES: dict[str, tuple[str, float]] = {}


def issue_phone_code(phone: str) -> str:
    """为手机号生成验证码（幂等：5 分钟内重复获取沿用旧码，防止短信轰炸）。

    sms_provider=dev：固定返回 settings.sms_dev_code（不真实发送）；
    sms_provider=real：TODO 在此接入真实短信通道（接口不变）。
    """
    from config import settings

    now = time.time()
    old = _PHONE_CODES.get(phone)
    if old and old[1] > now:
        return old[0]
    code = (
        settings.sms_dev_code
        if settings.sms_provider == "dev"
        else f"{secrets.randbelow(1000000):06d}"
    )
    _PHONE_CODES[phone] = (code, now + settings.phone_code_ttl_seconds)
    return code


def verify_phone_code(phone: str, code: str) -> bool:
    """校验手机号验证码（校验通过即销毁，防止重放）。"""
    from config import settings

    item = _PHONE_CODES.get(phone)
    if not item:
        return False
    stored, expires = item
    if time.time() > expires:
        _PHONE_CODES.pop(phone, None)
        return False
    if not secrets.compare_digest(stored, code):
        return False
    _PHONE_CODES.pop(phone, None)
    return True


def phone_login_user(phone: str) -> tuple[str, str, bool]:
    """手机号验证码登录/注册：按 phone 定位用户，无账号则自动创建。

    Returns:
        (user_id, token, is_new)。
    """
    from storage.db import get_conn, transaction

    phone = (phone or "").strip()
    if not phone:
        raise ValueError("手机号不能为空")
    conn = get_conn()
    row = conn.execute(
        "SELECT id FROM users WHERE phone = ? OR username = ? ORDER BY created_at LIMIT 1",
        (phone, phone),
    ).fetchone()
    if row:
        return row["id"], create_token(row["id"]), False

    uid = "u_" + uuid.uuid4().hex[:12]
    now = datetime.now(UTC).isoformat(timespec="seconds")
    nickname = "用户" + phone[-4:]
    with transaction() as c:
        c.execute(
            "INSERT INTO users(id, openid, username, nickname, phone, created_at, updated_at) "
            "VALUES (?,?,?,?,?,?,?)",
            (uid, uid, phone, nickname, phone, now, now),
        )
    return uid, create_token(uid), True


def bind_wechat(user_id: str, openid: str) -> bool:
    """把微信 openid 绑定到当前账号（users.openid 列）。

    Raises:
        ValueError: openid 已被其他账号绑定。
    """
    from storage.db import get_conn, transaction

    conn = get_conn()
    if not conn.execute("SELECT id FROM users WHERE id = ?", (user_id,)).fetchone():
        raise ValueError("用户不存在")
    owned = conn.execute("SELECT id FROM users WHERE openid = ? AND id != ?", (openid, user_id)).fetchone()
    if owned:
        raise ValueError("该微信已绑定其他账号")
    with transaction() as c:
        c.execute("UPDATE users SET openid = ?, updated_at = ? WHERE id = ?",
                  (openid, datetime.now(UTC).isoformat(timespec="seconds"), user_id))
        # 清理孤儿行：此前以微信 openid 直接建档（id=openid 且无账号凭据）的临时用户
        c.execute(
            "DELETE FROM users WHERE id = ? AND username IS NULL AND phone IS NULL AND id != ?",
            (openid, user_id),
        )
    return True


def wx_login_user(openid: str, nickname: str | None = None) -> tuple[str, str, bool]:
    """微信 openid 登录：无账号自动建档（id=openid），保证 /auth/me 与业务表可用。

    Returns:
        (user_id, token, is_new)。
    """
    from storage.db import get_conn, transaction

    conn = get_conn()
    row = conn.execute("SELECT id FROM users WHERE openid = ?", (openid,)).fetchone()
    if row:
        return row["id"], create_token(row["id"]), False
    now = datetime.now(UTC).isoformat(timespec="seconds")
    with transaction() as c:
        c.execute(
            "INSERT INTO users(id, openid, nickname, created_at, updated_at) VALUES (?,?,?,?,?)",
            (openid, openid, (nickname or "微信用户")[:30], now, now),
        )
    return openid, create_token(openid), True
