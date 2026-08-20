"""routers/chat.py —— 智能体对话 / 生图任务 / 多会话（api.py 拆分，2026-08 重构）。"""
from __future__ import annotations

import asyncio
import logging
import re
from pathlib import Path
from typing import Any

from agent.agent import is_allowed
from backend.config import settings
from backend.routers.common import (  # noqa: F401  # 共享单例/辅助（按需使用）
    METRICS,
    ChatRequest,
    CreateConvRequest,
    ImageGenRequest,
    RenameConvRequest,
    ResetRequest,
    _assert_order_owner,
    _check_rate,
    _client_ip,
    _limiter,
    agent,
    catalog_store,
    repo,
    resolve_uid,
)
from backend.security import get_current_user
from backend.storage import memory as mem_store
from backend.storage import tasks
from fastapi import APIRouter, HTTPException, Request
from fastapi.responses import FileResponse

router = APIRouter(tags=["chat"])
logger = logging.getLogger("api")

@router.post("/chat")
async def chat(req: ChatRequest, request: Request) -> Any:
    """与智能体对话，跑完 ReAct + 状态机后返回结构化 UI 响应。

    限流：每 IP 每分钟 N 次（付费 LLM 接口，防刷单）。
    """
    _check_rate(f"chat:{_client_ip(request)}", settings.rate_limit_chat_per_minute)
    request_id = getattr(request.state, "request_id", "-")
    # 身份解析：鉴权模式以 JWT openid 为准（忽略请求体 user_id，防冒用）；dev 模式回退 body user_id。
    user_id = await resolve_uid(request, req.user_id)
    logger.info("[%s] chat user=%s role=%s msg=%s", request_id, user_id, req.user_role, req.message[:80])

    if not is_allowed(req.user_role, "chat"):
        raise HTTPException(status_code=403, detail=f"角色 {req.user_role} 无权执行 chat")

    # 会话归属校验：若前端带了会话 ID，确认其属于该用户；否则为其新建一个会话
    sid = req.session_id
    if sid:
        conv = await asyncio.to_thread(mem_store.get_conversation, sid)
        if not conv or conv.get("user_id") != user_id:
            sid = None
    if not sid:
        sid = await asyncio.to_thread(
            mem_store.create_conversation, user_id, title=req.message[:20]
        )

    try:
        result = await asyncio.wait_for(
            agent.arun(user_id, req.message, sid, req.user_role, req.location),
            timeout=settings.request_timeout,
        )
    except TimeoutError:
        logger.error("[%s] 处理超时 >%.0fs", request_id, settings.request_timeout)
        raise HTTPException(
            status_code=504,
            detail=f"处理超时（>{settings.request_timeout:.0f}s），请简化问题后重试",
        ) from None
    except PermissionError as exc:
        raise HTTPException(status_code=403, detail=str(exc)) from exc
    except Exception as exc:  # noqa: BLE001
        logger.exception("[%s] 智能体执行失败", request_id)
        raise HTTPException(status_code=500, detail=f"智能体执行失败: {type(exc).__name__}") from exc

    # 更新会话列表预览（取用户本轮消息摘要），便于前端「类 ChatGPT」会话列表展示
    final_sid = result.session_id
    await asyncio.to_thread(mem_store.update_conversation_preview, final_sid, req.message[:60])
    return result.model_dump()



@router.get("/tasks/{task_id}")
async def get_task(task_id: str, request: Request) -> dict[str, Any]:
    """轮询生图任务结果（同步 DB 在线程池执行）。

    鉴权模式下强制校验 Bearer 令牌（dev 模式放行），防止越权轮询他人生图任务。
    """
    await get_current_user(request)
    return await asyncio.to_thread(tasks.get_image_task, task_id)



@router.post("/image/generate")
async def generate_image(req: ImageGenRequest, request: Request) -> dict[str, Any]:
    """提交生图任务（前端 DIY 详情页「生成效果图」直连入口）。

    鉴权模式下强制校验 Bearer 令牌（dev 模式放行）。立即返回 task_id，
    客户端轮询 GET /tasks/{task_id} 获取最终图片 URL。

    说明：真实 provider 的提交可能是网络调用，故放在 asyncio.to_thread 中执行，
    避免阻塞事件循环；mock 模式则直接落本地占位图并立即 done。
    """
    await get_current_user(request)
    _check_rate(f"image:{_client_ip(request)}", settings.rate_limit_image_per_minute)
    task_id = await asyncio.to_thread(tasks.create_image_task, req.prompt)
    return {"task_id": task_id, "status": "submitted", "poll": f"/tasks/{task_id}"}



@router.get("/generated/{filename}")
async def serve_generated(filename: str) -> FileResponse:
    """托管 api2img 中转商生成的本地图片（base64 落盘产物）。

    仅允许安全文件名，且路径必须严格落在 generated_dir 内，杜绝目录穿越。
    """
    if not re.fullmatch(r"[A-Za-z0-9_.\-]+", filename):
        raise HTTPException(status_code=400, detail="非法文件名")
    root = Path(settings.generated_dir).resolve()
    path = (root / filename).resolve()
    if path.parent != root or not path.is_file():
        raise HTTPException(status_code=404, detail="图片不存在")
    return FileResponse(path)



@router.post("/chat/reset")
async def reset(req: ResetRequest, request: Request) -> dict[str, Any]:
    """清空短期记忆（会话与消息），便于测试。

    - conversation_id 给定：仅清该会话（会话级重置）。
    - 否则：清该用户最近的一个会话。
    鉴权模式下身份以 JWT openid 为准，忽略请求体 user_id，防止越权清他人会话；
    dev 模式沿用请求体 user_id（兼容本地手测）。
    """
    if not is_allowed(req.user_role, "reset"):
        raise HTTPException(status_code=403, detail=f"角色 {req.user_role} 无权执行 reset")
    openid = await get_current_user(request)
    user_id = openid or req.user_id
    ok = await asyncio.to_thread(mem_store.reset_session, user_id, req.conversation_id)
    return {"user_id": user_id, "reset": ok}



@router.get("/conversations")
async def list_conversations(request: Request, user_id: str | None = None) -> dict[str, Any]:
    """列出某用户的全部会话（按最近活跃倒序）。"""
    uid = await resolve_uid(request, user_id)
    if not uid:
        raise HTTPException(status_code=401, detail="缺少用户身份")
    convs = await asyncio.to_thread(mem_store.list_conversations, uid)
    return {"conversations": convs}



@router.post("/conversations")
async def create_conversation(req: CreateConvRequest, request: Request) -> dict[str, Any]:
    """新建会话，返回会话 ID。"""
    uid = await resolve_uid(request, req.user_id)
    if not uid:
        raise HTTPException(status_code=401, detail="缺少用户身份")
    cid = await asyncio.to_thread(mem_store.create_conversation, uid, req.title or "新对话")
    return {"conversation_id": cid, "id": cid}



@router.get("/conversations/{conv_id}/messages")
async def get_conversation_messages(conv_id: str, request: Request, user_id: str | None = None) -> dict[str, Any]:
    """获取会话内消息（user/assistant，含 ui/data），供前端历史回放。

    归属校验：鉴权模式下会话须属于当前令牌用户，防止越权读取他人对话历史。
    """
    uid = await resolve_uid(request, user_id)
    if uid:
        conv = await asyncio.to_thread(mem_store.get_conversation, conv_id)
        if not conv or conv.get("user_id") != uid:
            raise HTTPException(status_code=404, detail="会话不存在")
    msgs = await asyncio.to_thread(mem_store.load_display_messages, conv_id)
    return {"messages": msgs}



@router.patch("/conversations/{conv_id}")
async def rename_conversation(conv_id: str, req: RenameConvRequest, request: Request) -> dict[str, Any]:
    """重命名会话标题。"""
    uid = await resolve_uid(request, req.user_id)
    if uid:
        conv = await asyncio.to_thread(mem_store.get_conversation, conv_id)
        if not conv or conv.get("user_id") != uid:
            raise HTTPException(status_code=404, detail="会话不存在")
    ok = await asyncio.to_thread(mem_store.rename_conversation, conv_id, req.title)
    if not ok:
        raise HTTPException(status_code=404, detail="会话不存在")
    return {"ok": True}



@router.delete("/conversations/{conv_id}")
async def delete_conversation(conv_id: str, request: Request, user_id: str | None = None) -> dict[str, Any]:
    """删除会话（级联清消息与控制标记）。"""
    uid = await resolve_uid(request, user_id)
    if uid:
        conv = await asyncio.to_thread(mem_store.get_conversation, conv_id)
        if not conv or conv.get("user_id") != uid:
            raise HTTPException(status_code=404, detail="会话不存在")
    ok = await asyncio.to_thread(mem_store.delete_conversation, conv_id)
    if not ok:
        raise HTTPException(status_code=404, detail="会话不存在")
    return {"ok": True}


