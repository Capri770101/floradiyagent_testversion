"""routers/report.py —— 内容举报（阶段5 内容审核体系：举报巡查）。

- POST /reports              C 端用户举报（plan|shop|review），需登录（resolve_uid）。
- GET  /reports              管理后台查询（status 过滤 + 分页 + 目标摘要），_require_admin。
- POST /reports/{id}/handle  管理后台处理（passed|rejected|banned；banned/passed 联动下架目标）。
"""

from __future__ import annotations

import asyncio
import logging
from typing import Any

from backend.routers.common import _require_admin, resolve_uid
from backend.storage import report as report_store
from fastapi import APIRouter, HTTPException, Request
from pydantic import BaseModel, Field

router = APIRouter(tags=["report"])
logger = logging.getLogger("api")


class ReportCreateRequest(BaseModel):
    target_type: str = Field(..., description="plan|shop|review")
    target_id: str = Field(..., min_length=1, max_length=64)
    reason: str = Field(..., min_length=1, max_length=50, description="举报原因（简短分类）")
    content: str = Field(default="", max_length=500, description="补充说明")


class ReportHandleRequest(BaseModel):
    status: str = Field(..., description="passed|rejected|banned")


@router.post("/reports")
async def create_report_endpoint(req: ReportCreateRequest, request: Request) -> dict[str, Any]:
    """提交举报（需登录；pending 进入管理后台待处理队列）。"""
    uid = await resolve_uid(request, None)
    if not uid:
        raise HTTPException(status_code=401, detail="请先登录后再举报")
    if req.target_type not in (report_store.T_PLAN, report_store.T_SHOP, report_store.T_REVIEW):
        raise HTTPException(status_code=400, detail="target_type 仅支持 plan|shop|review")
    item = await asyncio.to_thread(
        report_store.create_report,
        uid, req.target_type, req.target_id.strip(), req.reason.strip(), req.content.strip(),
    )
    return {"report": item}


@router.get("/reports")
async def list_reports_endpoint(
    request: Request, status: str = "", limit: int = 50, offset: int = 0
) -> dict[str, Any]:
    """管理后台举报列表（新→旧；status 过滤 + 分页）。"""
    await _require_admin(request)
    return await asyncio.to_thread(report_store.list_reports, status.strip(), limit, offset)


@router.post("/reports/{report_id}/handle")
async def handle_report_endpoint(
    report_id: str, req: ReportHandleRequest, request: Request
) -> dict[str, Any]:
    """管理后台处理举报；banned/passed 联动下架目标（商品/店铺/评价）。"""
    admin_uid = await _require_admin(request)
    if req.status not in report_store.HANDLEABLE:
        raise HTTPException(status_code=400, detail="status 仅支持 passed|rejected|banned")
    try:
        item = await asyncio.to_thread(
            report_store.handle_report, report_id, req.status, admin_uid
        )
    except ValueError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    return {"report": item}
