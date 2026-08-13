"""FastAPI 应用入口。

启动：uvicorn api:app --host 0.0.0.0 --port 8000
接口：
  POST /chat            {user_id, message, session_id?, user_role?, location?}
  GET  /tasks/{task_id} 异步任务（AI 生图）轮询
  POST /chat/reset      {user_id} 清空用户会话与历史
  GET  /health          健康检查
"""
import logging
from typing import Optional

from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel, Field

from agent import Agent
from config import Config, BASE_DIR
from engine.llm import LLMClient
from engine.ui_protocol import ChatResponse
from runtime import init_runtime
from skills import load_skills
from storage.db import Database
from storage.image_gen import build_image_gen
from storage.memory import Memory
from storage.repository import MockRepository
from storage.tasks import TaskManager

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s %(levelname)s [%(name)s] %(message)s",
)
logger = logging.getLogger("api")

app = FastAPI(
    title="花卉选购引导智能体",
    description="微信小程序花卉导购后端：ReAct 智能体 + 会话状态机 + 结构化 UI 协议",
    version="0.1.0",
)

# 开发期放开跨域；生产部署按小程序白名单收紧（小程序场景不依赖 CORS）
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)

# ---------------- 依赖装配（可替换点均在此处） ----------------
_config = Config()
_db = Database(_config.db_path)
_db.init_schema()

# 生图结果（api2img 返回 base64 时）落盘目录的静态托管
_images_dir = _config.image_cache_dir
_images_dir.mkdir(parents=True, exist_ok=True)
app.mount("/images", StaticFiles(directory=str(_images_dir)), name="images")

_repository = MockRepository()  # 真实数据库接入：替换为实现 BaseRepository 的类即可
_memory = Memory(_db)
_image_gen = build_image_gen(_config)
_tasks = TaskManager(_db, image_gen=_image_gen, delay=_config.image_task_delay)
init_runtime(_config, _repository, _memory, _tasks)

load_skills()  # 自动发现并注册 skills/


def _stage_reader(user_id: str) -> str:
    """mock 后端读取当前阶段用（真实后端由模型在 respond 中自报）。"""
    session = _memory.latest_session(user_id)
    return session["stage"] if session else "ANALYZE"


_llm = LLMClient(_config, stage_reader=_stage_reader)
_agent = Agent(_config, _llm, _memory, _repository)


# ---------------- 请求模型 ----------------
class ChatRequest(BaseModel):
    user_id: str = Field(min_length=1, description="用户标识（微信 openid 接入后使用 openid）")
    message: str = Field(min_length=1, description="用户消息")
    session_id: Optional[str] = Field(default=None, description="会话 ID（留空自动创建/续用）")
    user_role: str = Field(default="user", description="预留：user/merchant/admin，本期仅实现 user")
    location: Optional[str] = Field(default=None, description="用户位置描述（用于店铺距离推荐）")


class ResetRequest(BaseModel):
    user_id: str


# ---------------- 接口 ----------------
@app.post("/chat", response_model=ChatResponse, summary="智能体对话")
def chat(req: ChatRequest) -> ChatResponse:
    """接收用户消息，返回结构化 UI 响应（reply + ui + data + tool_calls）。"""
    logger.info("[/chat] user=%s role=%s stage 请求开始", req.user_id, req.user_role)
    try:
        return _agent.chat(
            user_id=req.user_id,
            message=req.message,
            session_id=req.session_id,
            user_role=req.user_role,
            location=req.location or "",
        )
    except Exception as exc:  # 兜底：任何未预期异常都以统一结构返回
        logger.exception("[/chat] 未预期异常 user=%s", req.user_id)
        raise HTTPException(status_code=500, detail=f"服务器内部错误: {exc}")


@app.get("/tasks/{task_id}", summary="异步任务轮询（AI 生图）")
def get_task(task_id: str) -> dict:
    task = _tasks.get_task(task_id)
    if task is None:
        raise HTTPException(status_code=404, detail="任务不存在")
    return task


@app.post("/chat/reset", summary="清空用户会话（测试用）")
def reset(req: ResetRequest) -> dict:
    _memory.clear_history(req.user_id)
    logger.info("已重置用户 %s 的会话与历史", req.user_id)
    return {"ok": True, "user_id": req.user_id}


@app.get("/health", summary="健康检查")
def health() -> dict:
    return {"status": "ok", "llm_backend": _config.llm_backend,
            "image_provider": _config.image_provider,
            "skills": sorted(__import__("tools").TOOL_REGISTRY.keys())}


if __name__ == "__main__":
    import uvicorn

    uvicorn.run("api:app", host="0.0.0.0", port=8000, reload=True)