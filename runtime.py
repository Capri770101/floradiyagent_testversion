"""全局运行时上下文：在 api 启动时注入依赖（仓库/记忆/任务等），

供 tools / skills / agent 跨模块访问。使用 contextvars 保证每个请求
携带独立的 user_id / location，避免线程池并发串号。
"""
import contextvars
from typing import TYPE_CHECKING, Any, Optional

if TYPE_CHECKING:
    from config import Config
    from storage.memory import Memory
    from storage.repository import BaseRepository
    from storage.tasks import TaskManager


class Runtime:
    """启动时填充的单例上下文。"""

    config: Optional["Config"] = None
    repository: Optional["BaseRepository"] = None
    memory: Optional["Memory"] = None
    tasks: Optional["TaskManager"] = None

    # 请求级上下文（contextvars，天然线程隔离）
    user_id: contextvars.ContextVar[str] = contextvars.ContextVar("user_id", default="")
    user_role: contextvars.ContextVar[str] = contextvars.ContextVar("user_role", default="user")
    location: contextvars.ContextVar[str] = contextvars.ContextVar("location", default="")
    session_id: contextvars.ContextVar[str] = contextvars.ContextVar("session_id", default="")


def init_runtime(config, repository, memory, tasks) -> None:
    Runtime.config = config
    Runtime.repository = repository
    Runtime.memory = memory
    Runtime.tasks = tasks


def get_runtime() -> Runtime:
    return Runtime