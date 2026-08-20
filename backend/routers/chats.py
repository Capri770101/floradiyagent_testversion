"""routers/chats.py —— 顾客侧商家会话端点（商家中心「联系商家」闭环的顾客端）。

权限模型：会话挂在「店铺+顾客」维度；读取/发送消息须验证会话归属
（dev 模式 token 缺失时跳过，兼容匿名 uid 手测）。
"""

from __future__ import annotations

import asyncio
from typing import Any

from backend.routers.common import resolve_uid
from backend.storage import chats as chat_store
from fastapi import APIRouter, HTTPException, Request
from pydantic import BaseModel, Field

router = APIRouter(tags=["chats"])


class ChatSendRequest(BaseModel):
    content: str = Field(..., min_length=1, max_length=1000, description="消息内容")


class ChatReplyRequest(BaseModel):
    reply: str = Field(..., min_length=1, max_length=500, description="商家回复内容")


def _own_chat_or_403(chat: dict[str, Any] | None, uid: str | None) -> None:
    """会话归属校验：令牌身份存在时，会话必须属于该顾客，否则 403。"""
    if not chat:
        raise HTTPException(status_code=404, detail="会话不存在")
    if uid and chat.get("user_id") != uid:
        raise HTTPException(status_code=403, detail="无权访问该会话")


@router.get("/chats")
async def user_chat_list(request: Request) -> dict[str, Any]:
    """顾客侧会话列表（个人中心消息中心展示用）。

    返回当前用户与各商家的历史会话，附店铺名、最后消息摘要、最后时间与顾客侧未读数。
    """
    uid = await resolve_uid(request)
    if not uid:
        raise HTTPException(status_code=401, detail="缺少用户身份")
    chats = await asyncio.to_thread(chat_store.list_user_chats, uid)
    return {"chats": chats}


@router.get("/chats/shop/{shop_id}")
async def user_chat_with_shop(shop_id: str, request: Request) -> dict[str, Any]:
    """顾客与某店铺的会话（不存在则创建）。返回会话 + 最近消息 + 店铺名。"""
    uid = await resolve_uid(request)
    if not uid:
        raise HTTPException(status_code=401, detail="缺少用户身份")
    shop_name = await asyncio.to_thread(chat_store.get_shop_name, shop_id)
    chat = await asyncio.to_thread(chat_store.get_or_create_chat, shop_id, uid)
    messages = await asyncio.to_thread(chat_store.list_messages, chat["id"], chat_store.SENDER_USER)
    return {"chat": chat, "messages": messages, "shop_name": shop_name}


@router.get("/chats/{chat_id}/messages")
async def user_chat_messages(chat_id: str, request: Request) -> dict[str, Any]:
    """顾客读取会话消息（读取即清零顾客侧未读）。"""
    uid = await resolve_uid(request)
    chat = await asyncio.to_thread(chat_store.get_chat, chat_id)
    _own_chat_or_403(chat, uid)
    messages = await asyncio.to_thread(chat_store.list_messages, chat_id, chat_store.SENDER_USER)
    return {"chat": chat, "messages": messages}


@router.post("/chats/{chat_id}/messages")
async def user_send_message(chat_id: str, req: ChatSendRequest, request: Request) -> dict[str, Any]:
    """顾客发送消息（商家未读 +1）。"""
    uid = await resolve_uid(request)
    chat = await asyncio.to_thread(chat_store.get_chat, chat_id)
    _own_chat_or_403(chat, uid)
    message = await asyncio.to_thread(
        chat_store.send_message, chat_id, chat_store.SENDER_USER, req.content.strip()
    )
    return {"message": message}
