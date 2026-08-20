"""api2img（第三方中转商）生图 provider 的单元测试。

全部 Mock/离线，不调用真实中转商、不烧额度。验证：
1. config.image_enabled 对 api2img 的启用判定（需同时配置 base_url + key）。
2. base64 落盘助手能正确写文件并返回 /generated/ 本地 URL。
3. _image_client_submit_api2img 解析 data[].b64_json 并落盘，请求发往 /v1/images/generations。
"""

from __future__ import annotations

import base64
from unittest.mock import MagicMock

import pytest
from backend.config import settings
from backend.storage import tasks
from backend.storage.db import init_db


def setup_module(module) -> None:
    # 初始化临时 DB（conftest 已设 DB_PATH 到临时文件），保证独立运行时表结构就绪
    init_db()


def test_image_enabled_api2img_requires_key_and_base(monkeypatch: pytest.MonkeyPatch) -> None:
    """api2img 必须在同时配置 base_url 与 key 时才视为启用。"""
    monkeypatch.setattr(settings, "image_provider", "api2img")
    monkeypatch.setattr(settings, "image_api_key", "")
    monkeypatch.setattr(settings, "api2img_base_url", "")
    monkeypatch.setattr(settings, "api2img_api_key", "")
    assert settings.image_enabled is False

    monkeypatch.setattr(settings, "api2img_base_url", "https://cc-vibe.com")
    monkeypatch.setattr(settings, "api2img_api_key", "sk-test")
    assert settings.image_enabled is True


def test_save_base64_image_writes_file(tmp_path: pytest.TempPathFactory, monkeypatch: pytest.MonkeyPatch) -> None:
    """中转商 base64 能正确落盘并返回 /generated/ 本地 URL。"""
    monkeypatch.setattr(settings, "generated_dir", str(tmp_path))
    raw = b"\x89PNG\r\n\x1a\n fake-png-bytes"
    url = tasks._save_base64_image(base64.b64encode(raw).decode(), "abc123", "png")
    assert url == "/generated/abc123.png"
    assert (tmp_path / "abc123.png").read_bytes() == raw


def test_api2img_submit_parses_b64_and_saves(tmp_path: pytest.TempPathFactory, monkeypatch: pytest.MonkeyPatch) -> None:
    """_image_client_submit_api2img 解析 data[].b64_json 并落盘返回 URL。"""
    monkeypatch.setattr(settings, "generated_dir", str(tmp_path))
    monkeypatch.setattr(settings, "api2img_base_url", "https://cc-vibe.com")
    monkeypatch.setattr(settings, "api2img_api_key", "sk-test")
    monkeypatch.setattr(settings, "api2img_model", "gpt-image-2")
    monkeypatch.setattr(settings, "api2img_size", "1024x1024")
    monkeypatch.setattr(settings, "api2img_quality", "medium")
    monkeypatch.setattr(settings, "api2img_output_format", "png")

    payload = {"data": [{"b64_json": base64.b64encode(b"IMG").decode()}]}
    fake_resp = MagicMock()
    fake_resp.raise_for_status.return_value = None
    fake_resp.json.return_value = payload
    fake_httpx = MagicMock()
    fake_httpx.post.return_value = fake_resp
    monkeypatch.setattr(tasks, "httpx", fake_httpx)

    url = tasks._image_client_submit_api2img("a bouquet", "tid_1")
    assert url == "/generated/tid_1.png"
    assert (tmp_path / "tid_1.png").read_bytes() == b"IMG"

    called = fake_httpx.post.call_args
    assert called.args[0].endswith("/v1/images/generations")
    assert called.kwargs["headers"]["Authorization"] == "Bearer sk-test"
    sent_body = called.kwargs["json"]
    assert sent_body["model"] == "gpt-image-2"
    assert sent_body["size"] == "1024x1024"


def test_detect_image_ext_by_magic() -> None:
    """魔数识别：png / jpeg / webp 与不可识别内容。"""
    assert tasks._detect_image_ext(b"\x89PNG\r\n\x1a\n" + b"x") == "png"
    assert tasks._detect_image_ext(b"\xff\xd8\xff\xe0JFIF") == "jpg"
    assert tasks._detect_image_ext(b"RIFF\x10\x00\x00\x00WEBPVP8 ") == "webp"
    assert tasks._detect_image_ext(b"not-an-image") is None
    assert tasks._detect_image_ext(b"RIFF\x00\x00\x00\x00XXXX") is None


def test_download_image_to_local_magic_wins_over_content_type(
    tmp_path: pytest.TempPathFactory, monkeypatch: pytest.MonkeyPatch
) -> None:
    """上游 content-type 声称 png 但内容实为 JPEG 时，按魔数落盘为 .jpg。"""
    monkeypatch.setattr(settings, "generated_dir", str(tmp_path))
    jpeg_bytes = b"\xff\xd8\xff\xe0" + b"\x00\x10JFIF fake-jpeg" + b"\x00" * 20

    fake_resp = MagicMock()
    fake_resp.headers = {"content-type": "image/png"}
    fake_resp.content = jpeg_bytes
    fake_resp.raise_for_status.return_value = None
    monkeypatch.setattr(tasks, "_is_safe_image_url", lambda url: True)
    monkeypatch.setattr(tasks, "_safe_get", lambda url: fake_resp)

    url = tasks._download_image_to_local("https://img.example.com/x", "tid_jpg")
    assert url == "/generated/tid_jpg.jpg"
    assert (tmp_path / "tid_jpg.jpg").read_bytes() == jpeg_bytes


def test_download_image_to_local_rejects_non_image(
    tmp_path: pytest.TempPathFactory, monkeypatch: pytest.MonkeyPatch
) -> None:
    """内容既非受支持图片、content-type 也无法兜底时拒绝落盘。"""
    monkeypatch.setattr(settings, "generated_dir", str(tmp_path))

    fake_resp = MagicMock()
    fake_resp.headers = {"content-type": "text/html"}
    fake_resp.content = b"<html>not an image</html>"
    fake_resp.raise_for_status.return_value = None
    monkeypatch.setattr(tasks, "_is_safe_image_url", lambda url: True)
    monkeypatch.setattr(tasks, "_safe_get", lambda url: fake_resp)

    with pytest.raises(RuntimeError, match="不是受支持的图片格式"):
        tasks._download_image_to_local("https://img.example.com/x", "tid_bad")


def test_create_image_task_api2img_sync_done(tmp_path: pytest.TempPathFactory, monkeypatch: pytest.MonkeyPatch) -> None:
    """create_image_task 在 api2img 下同步出图并直接置为 done，返回本地 URL。"""
    monkeypatch.setattr(settings, "generated_dir", str(tmp_path))
    monkeypatch.setattr(settings, "image_provider", "api2img")
    monkeypatch.setattr(settings, "api2img_base_url", "https://cc-vibe.com")
    monkeypatch.setattr(settings, "api2img_api_key", "sk-test")
    monkeypatch.setattr(settings, "api2img_model", "gpt-image-2")
    monkeypatch.setattr(settings, "api2img_size", "1024x1024")
    monkeypatch.setattr(settings, "api2img_quality", "medium")
    monkeypatch.setattr(settings, "api2img_output_format", "png")

    payload = {"data": [{"b64_json": base64.b64encode(b"IMG").decode()}]}
    fake_resp = MagicMock()
    fake_resp.raise_for_status.return_value = None
    fake_resp.json.return_value = payload
    fake_httpx = MagicMock()
    fake_httpx.post.return_value = fake_resp
    monkeypatch.setattr(tasks, "httpx", fake_httpx)

    tid = tasks.create_image_task("a bouquet for mother")
    row = tasks.get_image_task(tid)
    assert row["status"] == "done"
    assert row["result_url"].startswith("/generated/")

    fname = row["result_url"].split("/")[-1]
    assert (tmp_path / fname).read_bytes() == b"IMG"
