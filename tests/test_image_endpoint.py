"""生图触发端点 POST /image/generate 测试（mock provider，离线不触网）。

验证：
1. 正常提交返回 task_id 与 poll 链接；
2. 空 prompt 被 pydantic 校验拦截（422）；
3. 鉴权模式下无令牌 → 401，带有效令牌 → 200。
"""
from __future__ import annotations

import backend.api as api
import backend.security as security
import pytest
from backend.config import settings
from fastapi.testclient import TestClient


@pytest.fixture
def client() -> TestClient:
    with TestClient(api.app) as c:
        yield c

def test_generate_returns_task_id(client: TestClient) -> None:
    """mock 模式下提交 prompt 立即返回 task_id 与轮询链接。"""
    r = client.post('/image/generate', json={'prompt': '一束粉色玫瑰的治愈系手捧花'})
    assert r.status_code == 200
    body = r.json()
    assert 'task_id' in body and body['task_id']
    assert body['poll'].endswith(body['task_id'])
    poll = client.get(body['poll'])
    assert poll.status_code == 200
    assert poll.json()['status'] == 'done'

def test_generate_rejects_empty_prompt(client: TestClient) -> None:
    """空 prompt 被请求模型校验拦截。"""
    r = client.post('/image/generate', json={'prompt': ''})
    assert r.status_code == 422

def test_generate_requires_auth_when_enabled(client: TestClient, monkeypatch: pytest.MonkeyPatch) -> None:
    """AUTH_REQUIRED=true 时：无令牌 → 401，带有效令牌 → 200。"""
    monkeypatch.setattr(settings, 'auth_required', True)
    try:
        no_auth = client.post('/image/generate', json={'prompt': 'test'})
        assert no_auth.status_code == 401
        token = security.create_token('oIMGUser')
        ok = client.post('/image/generate', json={'prompt': 'test'}, headers={'Authorization': f'Bearer {token}'})
        assert ok.status_code == 200
        assert ok.json()['task_id']
    finally:
        monkeypatch.setattr(settings, 'auth_required', False)
