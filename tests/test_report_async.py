"""report 存储层异步迁移的单测（P1 模式验证，aiosqlite 即可，无需真实 PG）。

覆盖：create / list（带目标摘要）/ handle（banned 联动下架），证明 storage/report.py 在
db_async 异步层上行为正确，且 ``?`` 占位符经方言改写后能正常执行。
"""
from __future__ import annotations

import asyncio

from backend.config import Settings
from backend.storage import db as db_mod
from backend.storage import db_async as dba
from backend.storage import report as report_store


def _patch(tmp_path, monkeypatch):
    s = Settings(db_path=str(tmp_path / 'report.db'), database_url='')
    monkeypatch.setattr(dba, 'settings', s)
    monkeypatch.setattr(db_mod, 'settings', s)
    try:
        delattr(db_mod._thread_local, 'conn')
    except AttributeError:
        pass
    dba._reset_engine()

def _cleanup(db_mod, monkeypatch):
    dba._reset_engine()
    try:
        delattr(db_mod._thread_local, 'conn')
    except AttributeError:
        pass

def test_report_async_crud(tmp_path, monkeypatch) -> None:
    _patch(tmp_path, monkeypatch)

    async def run():
        await dba.init_db_async()
        rep = await report_store.create_report('u1', 'plan', 'P001', '违规', '详细说明')
        assert rep['status'] == 'pending'
        listed = await report_store.list_reports()
        assert listed['total'] >= 1
        mine = next(x for x in listed['reports'] if x['id'] == rep['id'])
        assert mine['target_title']
        handled = await report_store.handle_report(rep['id'], 'banned', 'admin1')
        assert handled['status'] == 'banned'
        banned = await report_store.list_reports(status='banned')
        assert any(x['id'] == rep['id'] for x in banned['reports'])
    asyncio.run(run())
    _cleanup(db_mod, monkeypatch)
