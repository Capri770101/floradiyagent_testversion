"""storage/payment.py —— 支付网关抽象层（微信支付 v3 / 支付宝 / 沙箱）。

设计要点：
- 统一接口 ``PaymentProvider``：
    * ``create_payment(order, method, extra) -> PaymentIntent``：发起统一下单，返回前端
      拉起支付所需的参数（微信为 ``wx.requestPayment`` 参数；支付宝为跳转 URL）。
    * ``verify_notify(body, headers) -> NotifyResult | None``：校验第三方回调签名并解密，
      成功返回订单号+交易号；无法验签返回 None（调用方据此要求渠道重试）。
- 凭据**全部来自 config（环境变量）**，本文件不出现任何密钥字面值。
- 默认 ``provider=sandbox``：无需任何凭据即可端到端跑通（dev/验证用）；沙箱模拟
  「下单即支付成功」，直接把订单标记已付，返回前端跳转用的 pay_params。
- 真实渠道（wechat/alipay）在**凭据未完整配置时明确抛 ``PaymentConfigError``**，绝不明默工作。
- 调用方（commerce.pay_order）只依赖抽象，不关心具体渠道；以后接银联/花呗等只需新增
  Provider 并在 ``PROVIDERS`` 注册，不动业务代码。

安全红线：
- 私钥/PEM 既可填内容也可填文件路径，但**绝不**落日志。
- 微信回调用平台证书验签 + APIv3 密钥 AES-GCM 解密，杜绝伪造回调篡改订单状态。
- 真实网关下单后订单保持 ``pending``，只有回调验签通过才标记已付（状态机不被直接信任）。
"""
from __future__ import annotations

import abc
import base64
import hashlib
import hmac
import json
import logging
import secrets
import time
import uuid
from collections.abc import Mapping
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import httpx

from backend.config import settings

logger = logging.getLogger('payment')

class PaymentError(RuntimeError):
    """支付流程通用异常。"""

class PaymentConfigError(PaymentError):
    """支付渠道凭据未配置或配置不完整（致命，调用方应转为 4xx/5xx）。"""

class PaymentGatewayError(PaymentError):
    """调用第三方支付网关失败（网络/返回非预期）。"""

@dataclass
class PaymentIntent:
    """一次支付下单的结果，供前端发起支付。

    Attributes:
        order_id: 本系统订单号（= out_trade_no）。
        method: 支付渠道（wechat/alipay/sandbox）。
        amount: 订单金额（元）。
        paid: 是否已在本次下单中支付成功（沙箱=True；真实网关=False，待回调）。
        pay_params: 前端拉起支付所需参数（微信=wx.requestPayment 入参；支付宝=跳转 URL）。
        page_path: 支付完成后的前端跳转页（小程序内页路径）。
        transaction_id: 第三方交易号；沙箱为模拟值，真实网关在回调回填。
    """
    order_id: str
    method: str
    amount: float
    paid: bool
    pay_params: dict[str, Any]
    page_path: str
    transaction_id: str | None = None

    def to_dict(self) -> dict[str, Any]:
        """序列化为 API 响应体。"""
        return {'order_id': self.order_id, 'method': self.method, 'amount': self.amount, 'paid': self.paid, 'pay_params': self.pay_params, 'page_path': self.page_path, 'transaction_id': self.transaction_id}

@dataclass
class NotifyResult:
    """回调验签通过后的解析结果。

    Attributes:
        order_id: 本系统订单号。
        transaction_id: 第三方交易号。
        paid: 该笔交易是否已支付成功（trade_state==SUCCESS）。
        raw: 解密后的原始回调解包（便于审计）。
    """
    order_id: str
    transaction_id: str
    paid: bool = True
    raw: dict[str, Any] | None = None

class BaseProvider(abc.ABC):
    """支付渠道抽象基类。"""
    name: str = ''

    @abc.abstractmethod
    def create_payment(self, order: dict[str, Any], method: str, extra: dict[str, Any] | None=None) -> PaymentIntent:
        """发起统一下单，返回前端拉起支付所需参数。"""

    @abc.abstractmethod
    def verify_notify(self, body: bytes, headers: Mapping[str, str]) -> NotifyResult | None:
        """校验并解密支付回调；验签失败/无法识别返回 None。"""

def _load_pem(value: str) -> str:
    """把配置里的 PEM 值归一化为 PEM 文本。

    支持三种填写方式：
    ① 直接贴 PEM 内容（含 ``-----BEGIN``，可单行用 ``\\n`` 代替换行）；
    ② 填文件路径（如 /app/data/alipay_private_key.pem）。
    路径解析失败或值过短则原样返回（交给底层 load_pem_* 报错，错误信息足够定位）。
    """
    if not value:
        return value
    # .env 中无法写多行，常用 ``\n`` 字面量代替换行，这里还原
    value = value.replace('\\n', '\n')
    if '-----BEGIN' in value:
        return value
    if len(value) < 400 and ('/' in value or '\\' in value or value.endswith('.pem')):
        try:
            return Path(value).read_text(encoding='utf-8')
        except OSError:
            return value
    return value

def _decrypt_aesgcm(key: str, resource: dict[str, Any]) -> str:
    """微信支付 v3 回调报文 AES-256-GCM 解密。

    key 即 APIv3 密钥（32 字节 ASCII）；nonce 12 字节；associated_data 可为空。
    """
    from cryptography.hazmat.primitives.ciphers.aead import AESGCM
    nonce = resource['nonce'].encode('utf-8')
    ciphertext = base64.b64decode(resource['ciphertext'])
    aad = (resource.get('associated_data') or '').encode('utf-8')
    plaintext = AESGCM(key.encode('utf-8')).decrypt(nonce, ciphertext, aad)
    return plaintext.decode('utf-8')

class SandboxProvider(BaseProvider):
    """演示渠道：无需任何凭据，下单即模拟支付成功。

    仅用于 dev/验证期端到端跑通支付流程；**绝不上报任何第三方**，也不会真的扣款。
    """
    name = 'sandbox'

    def create_payment(self, order: dict[str, Any], method: str, extra: dict[str, Any] | None=None) -> PaymentIntent:
        txn = 'SANDBOX_' + uuid.uuid4().hex[:16]
        return PaymentIntent(order_id=order['order_id'], method=method, amount=float(order.get('total_price') or 0), paid=True, pay_params={'sandbox': True, 'transaction_id': txn, 'method': method, 'tip': '沙箱支付：未接真实网关，仅用于端到端流程验证，不会产生真实扣款'}, page_path=settings.pay_page_path, transaction_id=txn)

    def verify_notify(self, body: bytes, headers: Mapping[str, str]) -> NotifyResult | None:
        return None

class WeChatPayProvider(BaseProvider):
    """微信支付 v3 JSAPI 渠道（小程序）。

    真实链路：统一下单 -> 拿 prepay_id -> 二次签名生成 ``wx.requestPayment`` 参数 ->
    用户支付 -> 微信回调 ``notify_url`` -> 验签 + AES-GCM 解密 -> 标记订单已付。
    """
    name = 'wechat'
    API_BASE = 'https://api.mch.weixin.qq.com'

    def _require_creds(self) -> dict[str, str]:
        """汇总并校验必需凭据；缺失即抛 ``PaymentConfigError``。"""
        mchid = settings.wechatpay_mch_id
        appid = settings.wechatpay_appid or settings.wechat_appid
        api_v3_key = settings.wechatpay_api_v3_key
        serial = settings.wechatpay_serial_no
        private_key = _load_pem(settings.wechatpay_private_key)
        public_cert = _load_pem(settings.wechatpay_public_cert)
        if not (mchid and appid and api_v3_key and serial and private_key):
            raise PaymentConfigError('微信支付未完整配置：需要 WXPAY_MCH_ID / WXPAY_APPID(或 WECHAT_APPID) / WXPAY_API_V3_KEY / WXPAY_SERIAL_NO / WXPAY_PRIVATE_KEY')
        return {'mchid': mchid, 'appid': appid, 'api_v3_key': api_v3_key, 'serial': serial, 'private_key': private_key, 'public_cert': public_cert}

    def _rsa_sign(self, message: str, private_key_pem: str) -> str:
        """RSA-SHA256 签名并 base64。微信 v3 所有签名统一用 PKCS#1 v1.5 + SHA256。"""
        from cryptography.hazmat.primitives import hashes, serialization
        from cryptography.hazmat.primitives.asymmetric import padding
        private_key = serialization.load_pem_private_key(private_key_pem.encode('utf-8'), password=None)
        signature = private_key.sign(message.encode('utf-8'), padding.PKCS1v15(), hashes.SHA256())
        return base64.b64encode(signature).decode('ascii')

    def _auth_header(self, method: str, url_path: str, body: str, creds: dict[str, str]) -> str:
        """构造微信 v3 请求头 ``Authorization: WECHATPAY2-SHA256-RSA2048 ...``。"""
        timestamp = str(int(time.time()))
        nonce = secrets.token_hex(16)
        message = f'{method}\n{url_path}\n{timestamp}\n{nonce}\n{body}\n'
        signature = self._rsa_sign(message, creds['private_key'])
        return f'''WECHATPAY2-SHA256-RSA2048 mchid="{creds['mchid']}",nonce_str="{nonce}",signature="{signature}",timestamp="{timestamp}",serial_no="{creds['serial']}"'''

    def create_payment(self, order: dict[str, Any], method: str, extra: dict[str, Any] | None=None) -> PaymentIntent:
        creds = self._require_creds()
        extra = extra or {}
        openid = extra.get('openid')
        if not openid:
            raise PaymentConfigError('微信 JSAPI 支付需要下单用户 openid（extra.openid）')
        amount_fen = int(round(float(order.get('total_price') or 0) * 100))
        if amount_fen <= 0:
            raise PaymentError('订单金额非法（需 > 0）')
        payload = {'appid': creds['appid'], 'mchid': creds['mchid'], 'description': extra.get('description', f"花艺方案 {order['order_id']}"), 'out_trade_no': order['order_id'], 'notify_url': settings.wechatpay_notify_url or '', 'amount': {'total': amount_fen, 'currency': 'CNY'}, 'payer': {'openid': openid}}
        body_str = json.dumps(payload, ensure_ascii=False, separators=(',', ':'))
        url_path = '/v3/pay/transactions/jsapi'
        auth = self._auth_header('POST', url_path, body_str, creds)
        headers = {'Authorization': auth, 'Content-Type': 'application/json', 'Accept': 'application/json', 'User-Agent': 'flora-agent/1.0'}
        try:
            resp = httpx.post(self.API_BASE + url_path, content=body_str, headers=headers, timeout=10)
        except httpx.HTTPError as exc:
            raise PaymentGatewayError(f'微信支付下单网络错误: {exc}') from exc
        if resp.status_code != 200:
            raise PaymentGatewayError(f'微信支付下单失败 {resp.status_code}: {resp.text[:200]}')
        prepay_id = resp.json().get('prepay_id')
        if not prepay_id:
            raise PaymentGatewayError(f'微信支付未返回 prepay_id: {resp.text[:200]}')
        ts = str(int(time.time()))
        nonce = secrets.token_hex(16)
        pkg = f'prepay_id={prepay_id}'
        sign_msg = f"{creds['appid']}\n{ts}\n{nonce}\n{pkg}\n"
        pay_sign = self._rsa_sign(sign_msg, creds['private_key'])
        pay_params = {'appId': creds['appid'], 'timeStamp': ts, 'nonceStr': nonce, 'package': pkg, 'signType': 'RSA', 'paySign': pay_sign}
        return PaymentIntent(order_id=order['order_id'], method='wechat', amount=amount_fen / 100, paid=False, pay_params=pay_params, page_path=settings.pay_page_path)

    def verify_notify(self, body: bytes, headers: Mapping[str, str]) -> NotifyResult | None:
        sig = headers.get('Wechatpay-Signature') or headers.get('wechatpay-signature')
        ts = headers.get('Wechatpay-Timestamp') or headers.get('wechatpay-timestamp')
        nonce = headers.get('Wechatpay-Nonce') or headers.get('wechatpay-nonce')
        if not (sig and ts and nonce):
            logger.warning('[wechat notify] 缺签名头，拒绝')
            return None
        creds = self._require_creds()
        if creds.get('public_cert'):
            from cryptography.hazmat.primitives import hashes, serialization
            from cryptography.hazmat.primitives.asymmetric import padding
            try:
                cert = serialization.load_pem_public_key(creds['public_cert'].encode('utf-8'))
                cert.verify(signature=base64.b64decode(sig), data=f"{ts}\n{nonce}\n{body.decode('utf-8')}\n".encode(), padding=padding.PKCS1v15(), algorithm=hashes.SHA256())
            except Exception:
                logger.warning('[wechat notify] 验签失败')
                return None
        else:
            logger.warning('[wechat notify] 未配置 WXPAY_PLATFORM_CERT，跳过验签（生产务必配置）')
        try:
            resource = json.loads(body.decode('utf-8'))['resource']
            plaintext = _decrypt_aesgcm(creds['api_v3_key'], resource)
            data = json.loads(plaintext)
        except Exception:
            logger.exception('[wechat notify] 解密失败')
            return None
        return NotifyResult(order_id=data['out_trade_no'], transaction_id=data.get('transaction_id', ''), paid=data.get('trade_state') == 'SUCCESS', raw=data)

class AlipayProvider(BaseProvider):
    """支付宝手机网站支付渠道（H5/小程序 WebView）。

    真实链路：构造带 RSA2 签名的跳转 URL -> 前端 302 跳支付宝 -> 用户支付 ->
    支付宝回调 ``notify_url`` -> 用支付宝公钥验签 -> 标记订单已付。
    """
    name = 'alipay'

    def _require_creds(self) -> dict[str, str]:
        app_id = settings.alipay_app_id
        private_key = self._wrap_key(_load_pem(settings.alipay_private_key), 'private')
        public_key = self._wrap_key(_load_pem(settings.alipay_public_key), 'public')
        # 拉起支付只需 app_id + 应用私钥（用于签名）；支付宝公钥仅回调验签时需要。
        if not (app_id and private_key):
            raise PaymentConfigError('支付宝未完整配置：需要 ALIPAY_APP_ID / ALIPAY_PRIVATE_KEY')
        return {'app_id': app_id, 'private_key': private_key, 'public_key': public_key}

    @staticmethod
    def _wrap_key(raw: str, kind: str) -> str:
        """支付宝平台导出的密钥可能是裸 base64（无 PEM 头），这里自动包裹为 PEM。

        - 私钥：裸 base64 -> PKCS#8（``-----BEGIN PRIVATE KEY-----``）。
        - 公钥：裸 base64 -> SPKI（``-----BEGIN PUBLIC KEY-----``）。
        已是 PEM（含 ``-----BEGIN``）则原样返回。
        """
        if not raw:
            return raw
        if '-----BEGIN' in raw:
            return raw
        if kind == 'private':
            return f"-----BEGIN PRIVATE KEY-----\n{raw}\n-----END PRIVATE KEY-----"
        return f"-----BEGIN PUBLIC KEY-----\n{raw}\n-----END PUBLIC KEY-----"

    def _rsa2_sign(self, raw: str, private_key_pem: str) -> str:
        """支付宝 RSA2 签名（SHA256withRSA，PKCS#1 v1.5）。"""
        from cryptography.hazmat.primitives import hashes, serialization
        from cryptography.hazmat.primitives.asymmetric import padding
        private_key = serialization.load_pem_private_key(private_key_pem.encode('utf-8'), password=None)
        signature = private_key.sign(raw.encode('utf-8'), padding.PKCS1v15(), hashes.SHA256())
        return base64.b64encode(signature).decode('ascii')

    def _sorted_sign_str(self, params: dict[str, Any]) -> str:
        """支付宝待签字符串：按 key 字典序、过滤空值与 sign，拼 ``k=v&k=v``。"""
        items = sorted(((k, v) for k, v in params.items() if k != 'sign' and k != 'sign_type' and (v != '') and (v is not None)))
        return '&'.join((f'{k}={v}' for k, v in items))

    def create_payment(self, order: dict[str, Any], method: str, extra: dict[str, Any] | None=None) -> PaymentIntent:
        from urllib.parse import urlencode
        creds = self._require_creds()
        extra = extra or {}
        amount = f"{float(order.get('total_price') or 0):.2f}"
        biz_dict = {'out_trade_no': order['order_id'], 'total_amount': amount, 'subject': extra.get('description', f"花艺方案 {order['order_id']}"), 'product_code': 'QUICK_WAP_WAY'}
        if settings.public_base_url:
            biz_dict['return_url'] = f"{settings.public_base_url.rstrip('/')}/orders/{order['order_id']}"
        biz = json.dumps(biz_dict, ensure_ascii=False)
        common = {'app_id': creds['app_id'], 'method': 'alipay.trade.wap.pay', 'charset': 'utf-8', 'sign_type': 'RSA2', 'timestamp': time.strftime('%Y-%m-%d %H:%M:%S'), 'version': '1.0', 'notify_url': settings.alipay_notify_url or '', 'biz_content': biz}
        common['sign'] = self._rsa2_sign(self._sorted_sign_str(common), creds['private_key'])
        pay_url = settings.alipay_gateway + '?' + urlencode(common)
        return PaymentIntent(order_id=order['order_id'], method='alipay', amount=float(amount), paid=False, pay_params={'pay_url': pay_url, 'redirect': True}, page_path=settings.pay_page_path)

    def verify_notify(self, body: bytes, headers: Mapping[str, str]) -> NotifyResult | None:
        from urllib.parse import parse_qsl
        params = dict(parse_qsl(body.decode('utf-8')))
        sign = params.get('sign')
        if not sign:
            return None
        creds = self._require_creds()
        if not creds['public_key']:
            logger.warning('[alipay notify] 未配置支付宝公钥，验签跳过（请配置 ALIPAY_PUBLIC_KEY）')
            return None
        raw = self._sorted_sign_str(params)
        from cryptography.hazmat.primitives import hashes, serialization
        from cryptography.hazmat.primitives.asymmetric import padding
        try:
            pub = serialization.load_pem_public_key(creds['public_key'].encode('utf-8'))
            pub.verify(base64.b64decode(sign), raw.encode('utf-8'), padding.PKCS1v15(), hashes.SHA256())
        except Exception:
            logger.warning('[alipay notify] 验签失败')
            return None
        return NotifyResult(order_id=params.get('out_trade_no', ''), transaction_id=params.get('trade_no', ''), paid=params.get('trade_status') == 'TRADE_SUCCESS', raw=dict(params))

class WeChatPayV2Provider(BaseProvider):
    """微信支付 v2 H5 支付渠道（MWEB）。

    适用于 H5 网页支付场景，用户在手机浏览器中完成支付。
    使用 XML 格式 + HMAC-SHA256 签名。
    """
    name = 'wechat_h5'
    API_BASE = 'https://api.mch.weixin.qq.com'

    def _require_creds(self) -> dict[str, str]:
        mchid = settings.wechatpay_v2_mch_id
        api_key = settings.wechatpay_v2_api_key
        if not (mchid and api_key):
            raise PaymentConfigError('微信支付 v2 未完整配置：需要 WXPAY_V2_MCH_ID / WXPAY_V2_API_KEY')
        return {'mchid': mchid, 'api_key': api_key}

    def _xml_sign(self, params: dict[str, str], api_key: str) -> str:
        """HMAC-SHA256 签名。"""
        items = sorted((k, v) for k, v in params.items() if v and k != 'sign')
        raw = '&'.join(f'{k}={v}' for k, v in items) + f'&key={api_key}'
        return hmac.new(api_key.encode('utf-8'), raw.encode('utf-8'), hashlib.sha256).hexdigest().upper()

    def _dict_to_xml(self, data: dict[str, str]) -> str:
        """字典转 XML。"""
        parts = ['<xml>']
        for k, v in data.items():
            parts.append(f'<{k}><![CDATA[{v}]]></{k}>')
        parts.append('</xml>')
        return ''.join(parts)

    def _xml_to_dict(self, xml_str: str) -> dict[str, str]:
        """XML 转字典（简单解析）。"""
        import re
        result = {}
        for match in re.finditer(r'<(\w+)><!\[CDATA\[(.*?)\]\]></\1>', xml_str):
            result[match.group(1)] = match.group(2)
        for match in re.finditer(r'<(\w+)>([^<]+)</\1>', xml_str):
            result[match.group(1)] = match.group(2)
        return result

    def create_payment(self, order: dict[str, Any], method: str, extra: dict[str, Any] | None=None) -> PaymentIntent:
        creds = self._require_creds()
        extra = extra or {}
        amount_fen = int(round(float(order.get('total_price') or 0) * 100))
        if amount_fen <= 0:
            raise PaymentError('订单金额非法（需 > 0）')

        spbill_create_ip = extra.get('spbill_create_ip', '127.0.0.1')

        # 本系统统一使用扫码支付(NATIVE)：商户号只需开通「扫码支付」产品即可，
        # 不依赖 H5支付(MWEB) 产品权限；appid 为微信要求必填项（取自 WECHAT_APPID）。
        trade_type = 'NATIVE'

        params = {
            'appid': settings.wechat_appid or '',
            'mch_id': creds['mchid'],
            'nonce_str': secrets.token_hex(16),
            'sign_type': 'HMAC-SHA256',
            'body': extra.get('description', f"花艺方案 {order['order_id']}"),
            'out_trade_no': order['order_id'],
            'total_fee': str(amount_fen),
            'spbill_create_ip': spbill_create_ip,
            'notify_url': settings.wechatpay_v2_notify_url or '',
            'trade_type': trade_type,
        }
        if settings.wechat_appid:
            params['appid'] = settings.wechat_appid
        params['sign'] = self._xml_sign(params, creds['api_key'])

        xml_body = self._dict_to_xml(params)
        try:
            resp = httpx.post(
                self.API_BASE + '/pay/unifiedorder',
                content=xml_body.encode('utf-8'),
                headers={'Content-Type': 'application/xml'},
                timeout=10
            )
        except httpx.HTTPError as exc:
            raise PaymentGatewayError(f'微信支付 v2 下单网络错误: {exc}') from exc

        resp_data = self._xml_to_dict(resp.text)
        if resp_data.get('return_code') != 'SUCCESS' or resp_data.get('result_code') != 'SUCCESS':
            err_msg = resp_data.get('err_code_des') or resp_data.get('return_msg') or '未知错误'
            raise PaymentGatewayError(f'微信支付 v2 下单失败: {err_msg}')

        if trade_type == 'NATIVE':
            code_url = resp_data.get('code_url')
            if not code_url:
                raise PaymentGatewayError(f'微信支付 v2 未返回 code_url: {resp.text[:200]}')
            return PaymentIntent(
                order_id=order['order_id'],
                method='wechat_native',
                amount=amount_fen / 100,
                paid=False,
                pay_params={'code_url': code_url, 'qr': True},
                page_path=settings.pay_page_path
            )
        else:
            mweb_url = resp_data.get('mweb_url')
            if not mweb_url:
                raise PaymentGatewayError(f'微信支付 v2 未返回 mweb_url: {resp.text[:200]}')
            return PaymentIntent(
                order_id=order['order_id'],
                method='wechat_h5',
                amount=amount_fen / 100,
                paid=False,
                pay_params={'mweb_url': mweb_url, 'redirect': True},
                page_path=settings.pay_page_path
            )

    def verify_notify(self, body: bytes, headers: Mapping[str, str]) -> NotifyResult | None:
        """微信 v2 支付回调验签。"""
        try:
            xml_str = body.decode('utf-8')
            data = self._xml_to_dict(xml_str)
        except Exception:
            logger.warning('[wechat_h5 notify] XML 解析失败')
            return None

        if data.get('return_code') != 'SUCCESS':
            return None

        creds = self._require_creds()
        sign = data.get('sign')
        if not sign:
            return None

        expected_sign = self._xml_sign(data, creds['api_key'])
        if sign != expected_sign:
            logger.warning('[wechat_h5 notify] 验签失败')
            return None

        return NotifyResult(
            order_id=data.get('out_trade_no', ''),
            transaction_id=data.get('transaction_id', ''),
            paid=data.get('result_code') == 'SUCCESS',
            raw=data
        )

PROVIDERS: dict[str, type[BaseProvider]] = {
    'sandbox': SandboxProvider,
    'wechat': WeChatPayProvider,
    'wechat_h5': WeChatPayV2Provider,
    'alipay': AlipayProvider,
}

# 前端 method 名 -> 内部渠道名 别名映射（解耦前端 UI 与后端渠道）
_METHOD_ALIASES: dict[str, str] = {
    'wechat': 'wechat_h5',
    'wechat_native': 'wechat_h5',
    'wechat_h5': 'wechat_h5',
    'alipay': 'alipay',
    'ali': 'alipay',
}


def get_provider(name: str | None=None) -> BaseProvider:
    """按名称取支付渠道实例；默认取 ``settings.payment_provider``（缺省 sandbox）。

    支持前端 method 别名（如 ``wechat_native`` -> ``wechat_h5``），便于同一后端同时
    提供多种真实支付渠道（微信扫码 + 支付宝）。

    Raises:
        PaymentConfigError: 渠道名未知。
    """
    name = (name or settings.payment_provider or 'sandbox').lower()
    name = _METHOD_ALIASES.get(name, name)
    cls = PROVIDERS.get(name)
    if not cls:
        raise PaymentConfigError(f"未知支付渠道: {name}（可选：{', '.join(PROVIDERS)}）")
    return cls()
