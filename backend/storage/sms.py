"""storage/sms.py —— 短信验证码下发（阿里云 Dysmsapi，dev 模式不真实发送）。

设计要点：
- 统一入口 ``send_sms(phone, code) -> bool``：
  * ``sms_provider == 'dev'`` 或未配置真实密钥 → 不真实发送（dev 用固定/随机码跑通全链路）。
  * ``sms_provider == 'aliyun'`` 且密钥齐 → 调用阿里云 SendSms 真实下发；失败抛 ``SmsError``。
- 凭据全部来自 config（环境变量），本文件不含任何密钥字面值。
- 阿里云 RPC 签名用 HMAC-SHA1（AccessKeySecret& 为 key），无第三方 SDK 依赖（仅 httpx）。
- 以后接腾讯云短信只需在 ``PROVIDERS`` 注册新发送器，调用方不变。
"""
from __future__ import annotations

import base64
import hashlib
import hmac
import logging
import time
import uuid
from typing import Any
from urllib.parse import quote, urlencode

import httpx

from backend.config import settings

logger = logging.getLogger('sms')


class SmsError(RuntimeError):
    """短信下发失败（网络/网关/配置不完整）。"""


def _aliyun_configured() -> bool:
    return bool(
        settings.sms_access_key_id
        and settings.sms_access_key_secret
        and settings.sms_sign_name
        and settings.sms_template_code
    )


def _percent_encode(s: str) -> str:
    """阿里云规范 percent-encode：保留 -_.~，其余统一编码。"""
    return quote(str(s), safe='-_.~')


def _aliyun_signature(params: dict[str, str], secret: str) -> str:
    """按阿里云 RPC 规范构造 HMAC-SHA1 签名。"""
    sorted_items = sorted(params.items())
    canonical = '&'.join(f'{_percent_encode(k)}={_percent_encode(v)}' for k, v in sorted_items)
    string_to_sign = f'GET&{_percent_encode("/")}&{_percent_encode(canonical)}'
    digest = hmac.new((secret + '&').encode('utf-8'), string_to_sign.encode('utf-8'), hashlib.sha1).digest()
    return base64.b64encode(digest).decode('ascii')


def _send_aliyun(phone: str, code: str) -> bool:
    """调用阿里云 Dysmsapi SendSms 下发验证码。失败抛 SmsError。"""
    if not _aliyun_configured():
        raise SmsError('阿里云短信未完整配置：需要 SMS_ACCESS_KEY_ID / SMS_ACCESS_KEY_SECRET / SMS_SIGN_NAME / SMS_TEMPLATE_CODE')
    params: dict[str, str] = {
        'AccessKeyId': settings.sms_access_key_id,
        'Action': 'SendSms',
        'Format': 'JSON',
        'PhoneNumbers': phone,
        'RegionId': settings.sms_region,
        'SignName': settings.sms_sign_name,
        'SignatureMethod': 'HMAC-SHA1',
        'SignatureNonce': uuid.uuid4().hex,
        'SignatureVersion': '1.0',
        'TemplateCode': settings.sms_template_code,
        'TemplateParam': f'{{"code":"{code}"}}',
        'Timestamp': time.strftime('%Y-%m-%dT%H:%M:%SZ', time.gmtime()),
        'Version': '2017-05-25',
    }
    params['Signature'] = _aliyun_signature(params, settings.sms_access_key_secret)
    try:
        resp = httpx.get(settings.sms_endpoint, params=params, timeout=10)
    except httpx.HTTPError as exc:
        raise SmsError(f'阿里云短信网络错误: {exc}') from exc
    try:
        data = resp.json()
    except Exception:
        raise SmsError(f'阿里云短信返回非 JSON: {resp.status_code} {resp.text[:200]}') from None
    if data.get('Code') != 'OK':
        raise SmsError(f'阿里云短信下发失败: {data.get("Code")} {data.get("Message")}')
    logger.info('[sms] 已下发验证码 phone=%s', phone)
    return True


def send_sms(phone: str, code: str) -> bool:
    """下发短信验证码。

    Returns:
        True 表示「已处理」（dev 模式视为成功；aliyun 模式为真实发送成功）。
    Raises:
        SmsError: aliyun 模式且配置不完整 / 网关调用失败。
    """
    if settings.sms_provider == 'dev' or not _aliyun_configured():
        if settings.sms_provider == 'dev':
            logger.info('[sms] dev 模式，跳过真实发送 phone=%s', phone)
            return True
        # 非 dev 但密钥未配齐：视为配置错误，交由调用方转 5xx
        return _send_aliyun(phone, code)
    return _send_aliyun(phone, code)


async def send_sms_async(phone: str, code: str) -> bool:
    """异步包装（I/O 放到线程，避免阻塞事件循环）。"""
    import asyncio
    return await asyncio.to_thread(send_sms, phone, code)
