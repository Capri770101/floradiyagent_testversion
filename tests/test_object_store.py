"""tests/test_object_store.py —— P0 对象存储抽象测试（LocalStore 无需外部依赖即可跑）。"""
from __future__ import annotations

from pathlib import Path

from backend.config import Settings
from backend.storage import object_store as os_mod
from backend.storage.object_store import LocalStore, build_object_store


def _reset() -> None:
    os_mod._store = None

def test_local_store_put_get_delete(tmp_path: Path, monkeypatch) -> None:
    """LocalStore 写入后可读回，删除后不可读；文件落在 generated_dir 下。"""
    monkeypatch.setattr(os_mod, 'settings', Settings(generated_dir=str(tmp_path), upload_dir=str(tmp_path)))
    store = LocalStore()
    url = store.put('plan_X.png', b'fake-bytes', namespace='generated')
    assert url == '/generated/plan_X.png'
    assert (tmp_path / 'plan_X.png').exists()
    assert store.get('plan_X.png', namespace='generated') == b'fake-bytes'
    store.delete('plan_X.png', namespace='generated')
    assert store.get('plan_X.png', namespace='generated') is None

def test_local_store_nested_key(tmp_path: Path, monkeypatch) -> None:
    """含子目录的 key 应拼到 upload_dir 下（与改造前行为一致）。"""
    monkeypatch.setattr(os_mod, 'settings', Settings(generated_dir=str(tmp_path), upload_dir=str(tmp_path)))
    store = LocalStore()
    store.put('S001/cover.jpg', b'img', namespace='uploads')
    assert (tmp_path / 'S001' / 'cover.jpg').exists()
    assert store.url('S001/cover.jpg', namespace='uploads') == '/uploads/S001/cover.jpg'

def test_build_object_store_default_local(monkeypatch) -> None:
    """storage_backend 留空或 local 时装配 LocalStore。"""
    _reset()
    settings = Settings(storage_backend='local')
    monkeypatch.setattr(os_mod, 'settings', settings)
    try:
        assert isinstance(build_object_store(), LocalStore)
    finally:
        _reset()
