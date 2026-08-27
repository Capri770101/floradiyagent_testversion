"""tests/test_taskq.py —— P3 异步任务队列测试（队列关闭时走同步 fallback，无需 Redis）。"""
from __future__ import annotations

from backend.config import Settings
from backend.storage import tasks as tasks_mod
from backend.tasks import queue as taskq


def test_queue_disabled_by_default(monkeypatch) -> None:
    """task_queue_enabled 默认 False → 队列不可用，调用方走同步 fallback。"""
    monkeypatch.setattr(taskq, 'settings', Settings(task_queue_enabled=False))
    assert taskq.queue_enabled() is False

def test_generate_image_mock_returns_placeholder(monkeypatch) -> None:
    """mock provider 下 _generate_image 直接产出本地占位图 URL（done）。"""
    monkeypatch.setattr(tasks_mod, 'settings', Settings(image_provider='mock', image_enabled=False))
    status, url = tasks_mod._generate_image('t1', '一束花')
    assert status == 'done'
    assert url.startswith('/generated/')
