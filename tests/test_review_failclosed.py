"""tests/test_review_failclosed.py —— P5 机审 Fail-Closed 测试（无需真实内容安全 API）。"""
from __future__ import annotations

import backend.review as review_mod
from backend.config import Settings
from backend.review import ReviewError, review_image


def _set(monkeypatch, **kw) -> None:
    monkeypatch.setattr(review_mod, 'settings', Settings(**kw))

def test_disabled_passes(monkeypatch) -> None:
    """content_review_enabled=False 时直接放行。"""
    _set(monkeypatch, content_review_enabled=False)
    review_image(b'fake')

def test_enabled_but_unconfigured_fail_open(monkeypatch) -> None:
    """启用机审但未接 API 且 fail_closed=False（dev）：放行不报错。"""
    _set(monkeypatch, content_review_enabled=True, content_review_url='', content_review_fail_closed=False)
    review_image(b'fake')

def test_enabled_but_unconfigured_fail_closed(monkeypatch) -> None:
    """启用机审但未接 API 且 fail_closed=True（prod）：拒绝上传。"""
    _set(monkeypatch, content_review_enabled=True, content_review_url='', content_review_fail_closed=True)
    try:
        review_image(b'fake')
        raise AssertionError('应抛出 ReviewError')
    except ReviewError:
        pass

def test_real_api_rejection(monkeypatch) -> None:
    """已接真实 API（URL 非空）且判定违规时拒绝：验证 _review_remote 真实路径。"""
    _set(monkeypatch, content_review_enabled=True, content_review_url='https://api.example.com/review')
    monkeypatch.setattr(review_mod, '_review_remote', lambda data: (False, '含违规内容'))
    try:
        review_image(b'fake')
        raise AssertionError('应抛出 ReviewError')
    except ReviewError as e:
        assert '违规' in str(e)
