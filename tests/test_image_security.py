"""生图下载 SSRF 防护测试（全部离线，不触网、不烧额度）。

验证 storage.tasks._is_safe_image_url：
- 仅允许白名单 host（官方 dashscope / 智谱 + 已配置 provider base 派生）；
- 协议仅 http/https；
- 解析 IP 为私网 / 回环 / 链路本地 / 保留 / 组播时拒绝；
- 自定义 host 在无法解析时 fail-closed 拒绝，官方默认 host 在离线时放行。
"""

from __future__ import annotations

import socket

import pytest

from config import settings
from storage import tasks


def test_official_host_allowed_offline() -> None:
    """官方默认白名单 host（无网络时解析失败但受信任）应放行。"""
    assert tasks._is_safe_image_url("https://dashscope.aliyuncs.com/x/y.png") is True
    assert tasks._is_safe_image_url("https://open.bigmodel.cn/img/abc.jpg") is True
    assert tasks._is_safe_image_url("http://bigmodel.cn/a.png") is True


def test_non_http_scheme_rejected() -> None:
    """非 http/https 协议一律拒绝。"""
    assert tasks._is_safe_image_url("ftp://dashscope.aliyuncs.com/x.png") is False
    assert tasks._is_safe_image_url("file:///etc/passwd") is False
    assert tasks._is_safe_image_url("gopher://169.254.169.254/") is False


def test_unknown_host_rejected() -> None:
    """白名单外的 host 直接拒绝（含内网元数据地址、localhost）。"""
    assert tasks._is_safe_image_url("https://evil.example.com/x.png") is False
    assert tasks._is_safe_image_url("http://169.254.169.254/latest/meta-data/") is False
    assert tasks._is_safe_image_url("http://localhost:9000/x.png") is False
    assert tasks._is_safe_image_url("http://127.0.0.1/x.png") is False
    assert tasks._is_safe_image_url("http://[::1]/x.png") is False


def test_missing_host_rejected() -> None:
    """无法解析出 host 的地址拒绝。"""
    assert tasks._is_safe_image_url("not-a-url") is False
    assert tasks._is_safe_image_url("") is False


def test_custom_host_private_ip_rejected(monkeypatch: pytest.MonkeyPatch) -> None:
    """自定义白名单 host 解析到私网 IP → 拒绝（防 SSRF 打到内网）。"""
    # 自定义中转 host 通过已配置 provider base 派生（真实场景：api2img 自定义中继地址），
    # 归入 image_download_hosts（白名单校验通过）但不在官方默认列表（离线不自动信任）。
    monkeypatch.setattr(settings, "api2img_base_url", "https://img.test-cdn.com")

    def fake_private(host: str, port: int, *args, **kwargs):
        return [(socket.AF_INET, socket.SOCK_STREAM, 6, "", ("10.0.0.5", port or 443))]

    monkeypatch.setattr(socket, "getaddrinfo", fake_private)
    assert tasks._is_safe_image_url("https://img.test-cdn.com/x.png") is False


def test_custom_host_loopback_rejected(monkeypatch: pytest.MonkeyPatch) -> None:
    """自定义白名单 host 解析到回环地址 → 拒绝。"""
    # 自定义中转 host 通过已配置 provider base 派生（真实场景：api2img 自定义中继地址），
    # 归入 image_download_hosts（白名单校验通过）但不在官方默认列表（离线不自动信任）。
    monkeypatch.setattr(settings, "api2img_base_url", "https://img.test-cdn.com")

    def fake_loopback(host: str, port: int, *args, **kwargs):
        return [(socket.AF_INET, socket.SOCK_STREAM, 6, "", ("127.0.0.1", port or 443))]

    monkeypatch.setattr(socket, "getaddrinfo", fake_loopback)
    assert tasks._is_safe_image_url("https://img.test-cdn.com/x.png") is False


def test_custom_host_public_ip_allowed(monkeypatch: pytest.MonkeyPatch) -> None:
    """自定义白名单 host 解析到公网 IP → 放行。"""
    # 自定义中转 host 通过已配置 provider base 派生（真实场景：api2img 自定义中继地址），
    # 归入 image_download_hosts（白名单校验通过）但不在官方默认列表（离线不自动信任）。
    monkeypatch.setattr(settings, "api2img_base_url", "https://img.test-cdn.com")

    def fake_public(host: str, port: int, *args, **kwargs):
        return [(socket.AF_INET, socket.SOCK_STREAM, 6, "", ("8.8.8.8", port or 443))]

    monkeypatch.setattr(socket, "getaddrinfo", fake_public)
    assert tasks._is_safe_image_url("https://img.test-cdn.com/x.png") is True


def test_custom_host_unresolvable_fail_closed(monkeypatch: pytest.MonkeyPatch) -> None:
    """自定义白名单 host 解析失败 → fail-closed 拒绝（官方默认 host 才离线放行）。"""
    # 自定义中转 host 通过已配置 provider base 派生（真实场景：api2img 自定义中继地址），
    # 归入 image_download_hosts（白名单校验通过）但不在官方默认列表（离线不自动信任）。
    monkeypatch.setattr(settings, "api2img_base_url", "https://img.test-cdn.com")

    def fake_fail(host: str, port: int, *args, **kwargs):
        raise socket.gaierror("no address")

    monkeypatch.setattr(socket, "getaddrinfo", fake_fail)
    assert tasks._is_safe_image_url("https://img.test-cdn.com/x.png") is False
