"""routers/notify.py —— 站内消息通知中心端点（NEW_FEATURES 模块一，任务书 §2.3）。

- 用户侧：消息列表（类型/已读过滤 + 分页）/ 未读总数 / 标记已读。
- 管理侧：运营发平台公告（POST /admin/notifications，写全部用户或指定群体）。
- 数据按接收者隔离——只能读取/标记自己的通知，杜绝越权窥探他人消息。
"""
from __future__ import annotations

import logging
from typing import Any

from backend.routers.common import _require_admin, resolve_uid
from backend.storage import notify as notify_store
from fastapi import APIRouter, HTTPException, Request
from pydantic import BaseModel, Field

router = APIRouter(tags=['notify'])
logger = logging.getLogger('api')

@router.get('/notifications')
async def list_notifications_endpoint(request: Request, type: str='', is_read: int | None=None, limit: int=50, offset: int=0) -> dict[str, Any]:
    """我的消息列表（新→旧；type/is_read 过滤 + 分页）。"""
    uid = await resolve_uid(request, None)
    if not uid:
        raise HTTPException(status_code=401, detail='缺少用户身份')
    if is_read is not None and is_read not in (0, 1):
        raise HTTPException(status_code=400, detail='is_read 仅支持 0/1')
    items = await notify_store.list_notifications(uid, type.strip(), is_read, max(1, min(limit, 200)), max(0, offset))
    return {'notifications': items}

@router.get('/notifications/unread-count')
async def unread_count_endpoint(request: Request) -> dict[str, Any]:
    """我的未读通知数（TabBar 红点轮询）。"""
    uid = await resolve_uid(request, None)
    if not uid:
        raise HTTPException(status_code=401, detail='缺少用户身份')
    return {'unread': await notify_store.count_unread(uid)}

@router.get('/notifications/{notification_id}')
async def notification_detail_endpoint(notification_id: str, request: Request) -> dict[str, Any]:
    """单条通知详情（仅本人可见）。"""
    uid = await resolve_uid(request, None)
    if not uid:
        raise HTTPException(status_code=401, detail='缺少用户身份')
    item = await notify_store.get_notification(notification_id, uid)
    if not item:
        raise HTTPException(status_code=404, detail='通知不存在或不属于当前用户')
    return {'notification': item}

class MarkReadRequest(BaseModel):
    """标记已读请求体：ids 批量；all=true 全部。"""
    ids: list[str] = Field(default_factory=list, max_length=200)
    all: bool = Field(False, description='true=全部标记已读')

@router.post('/notifications/mark-read')
async def mark_read_endpoint(req: MarkReadRequest, request: Request) -> dict[str, Any]:
    """标记已读（ids 批量或 all 全部，仅本人通知）。"""
    uid = await resolve_uid(request, None)
    if not uid:
        raise HTTPException(status_code=401, detail='缺少用户身份')
    n = await notify_store.mark_read(uid, req.ids, req.all)
    return {'ok': True, 'updated': n}

class AnnouncementWriteRequest(BaseModel):
    """运营发平台公告/系统消息请求体。"""
    title: str = Field(..., min_length=1, max_length=60)
    body: str = Field('', max_length=300)
    ntype: str = Field(notify_store.T_ANNOUNCE, description='announcement|system')
    user_ids: list[str] | None = Field(None, description='指定群体（缺省发全部用户）')

@router.post('/admin/notifications')
async def admin_send_notification(req: AnnouncementWriteRequest, request: Request) -> dict[str, Any]:
    """运营发平台公告/系统消息（写全部用户或指定群体），返回投放条数。"""
    await _require_admin(request)
    if req.ntype not in (notify_store.T_ANNOUNCE, notify_store.T_SYSTEM):
        raise HTTPException(status_code=400, detail='ntype 仅支持 announcement|system')
    n = await notify_store.broadcast(req.title, req.body, req.ntype, '', '', req.user_ids)
    return {'ok': True, 'sent': n}
