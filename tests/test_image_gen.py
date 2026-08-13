"""生图 provider 的测试（httpx MockTransport 注入）：api2img / 智谱 CogView。"""
import base64

import httpx
import pytest

from config import Config
from storage.image_gen import _openai_compatible_generate, _zhipu_generate

PNG_B64 = base64.b64encode(b"\x89PNG\r\n\x1a\n" + b"0" * 128).decode()


def _cfg(tmp_path) -> Config:
    c = Config()
    c.image_cache_dir = tmp_path / "images"
    c.image_openai_base_url = "https://relay.example.com/v1"
    c.image_openai_api_key = "relay-key"
    c.image_openai_model = "flux-1.1-pro"
    c.image_result_base = "http://127.0.0.1:8000"
    return c


def _zcfg(tmp_path) -> Config:
    c = Config()
    c.image_zhipu_api_key = "abc.def"
    c.image_zhipu_model = "cogview-3-flash"
    c.image_zhipu_base_url = "https://open.bigmodel.cn/api/paas/v4"
    c.image_zhipu_max_retries = 3
    c.image_zhipu_retry_base = 0  # 测试不真等
    return c


def test_url_result(tmp_path):
    """中转商直接返回 url：原样传递。"""
    def handler(request: httpx.Request) -> httpx.Response:
        assert request.url.path == "/v1/images/generations"
        assert request.headers["Authorization"] == "Bearer relay-key"
        payload = request.read().decode()
        assert '"prompt"' in payload and '"flux-1.1-pro"' in payload
        return httpx.Response(200, json={"data": [{"url": "https://cdn.relay/img.png"}]})

    with httpx.Client(transport=httpx.MockTransport(handler)) as http:
        url = _openai_compatible_generate(_cfg(tmp_path), "一束粉色康乃馨", http=http)
    assert url == "https://cdn.relay/img.png"


def test_b64_result_saved_locally(tmp_path):
    """中转商返回 b64_json：落盘到缓存目录并返回可访问地址。"""
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(200, json={"data": [{"b64_json": PNG_B64}]})

    with httpx.Client(transport=httpx.MockTransport(handler)) as http:
        url = _openai_compatible_generate(_cfg(tmp_path), "花束", http=http)
    assert url.startswith("http://127.0.0.1:8000/images/agent_img_")
    files = list((tmp_path / "images").glob("*.png"))
    assert len(files) == 1
    assert files[0].read_bytes().startswith(b"\x89PNG")


def test_empty_result_raises(tmp_path):
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(200, json={"data": []})

    with httpx.Client(transport=httpx.MockTransport(handler)) as http:
        with pytest.raises(RuntimeError, match="无返回数据"):
            _openai_compatible_generate(_cfg(tmp_path), "花束", http=http)


def test_missing_config_raises():
    c = Config()
    c.image_openai_base_url = ""
    c.image_openai_api_key = ""
    with pytest.raises(RuntimeError, match="未配置 IMAGE_OPENAI"):
        _openai_compatible_generate(c, "花束")


# ---------- 智谱 CogView-3-Flash ----------

def test_zhipu_url_result(tmp_path):
    """智谱正常返回：直链透传。"""
    def handler(request: httpx.Request) -> httpx.Response:
        assert request.url.path == "/api/paas/v4/images/generations"
        assert request.headers["Authorization"] == "Bearer abc.def"
        payload = request.read().decode()
        assert '"cogview-3-flash"' in payload and '"prompt"' in payload
        return httpx.Response(200, json={"data": [{"url": "https://maas.ufileos.com/x.png"}]})

    with httpx.Client(transport=httpx.MockTransport(handler)) as http:
        url = _zhipu_generate(_zcfg(tmp_path), "橘色小猫", http=http)
    assert url == "https://maas.ufileos.com/x.png"


def test_zhipu_429_then_success(tmp_path):
    """免费额度 429 两次后成功：走退避重试。"""
    calls = {"n": 0}

    def handler(request: httpx.Request) -> httpx.Response:
        calls["n"] += 1
        if calls["n"] <= 2:
            return httpx.Response(429, json={"error": {"code": "1302", "message": "限流"}})
        return httpx.Response(200, json={"data": [{"url": "https://maas.ufileos.com/y.png"}]})

    with httpx.Client(transport=httpx.MockTransport(handler)) as http:
        url = _zhipu_generate(_zcfg(tmp_path), "小猫", http=http)
    assert url == "https://maas.ufileos.com/y.png"
    assert calls["n"] == 3


def test_zhipu_all_429_raises(tmp_path):
    """429 次数用尽：抛异常。"""
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(429, json={"error": {"code": "1302"}})

    with httpx.Client(transport=httpx.MockTransport(handler)) as http:
        with pytest.raises(RuntimeError, match="限流"):
            _zhipu_generate(_zcfg(tmp_path), "小猫", http=http)


def test_zhipu_missing_key_raises():
    c = Config()
    c.image_zhipu_api_key = ""
    with pytest.raises(RuntimeError, match="未配置 IMAGE_ZHIPU_API_KEY"):
        _zhipu_generate(c, "小猫")