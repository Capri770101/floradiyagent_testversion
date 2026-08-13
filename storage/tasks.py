"""异步任务管理：当前用于 AI 生图（生图是慢操作，客户端通过 /tasks/{id} 轮询）。

生图实现按 image_provider 切换：
- mock  : 延迟数秒后返回占位 URL，保证本地全链路可测；
- tongyi: 通义万相预留接入点（storage/image_gen.py），密钥在 config/.env 配置。
"""
import logging
import threading
import uuid
from typing import Callable, Optional

from storage.db import Database

logger = logging.getLogger(__name__)


class TaskManager:
    def __init__(self, db: Database, image_gen: Callable[[str], str], delay: float = 4.0) -> None:
        self.db = db
        self.image_gen = image_gen
        self.delay = delay

    def submit_image_task(self, user_id: str, plan_text: str) -> str:
        """提交生图任务，立即返回 task_id，异步线程模拟完成。"""
        task_id = uuid.uuid4().hex
        self.db.execute(
            "INSERT INTO tasks (task_id, user_id, kind, plan_text, status) "
            "VALUES (?, ?, 'image', ?, 'pending')",
            (task_id, user_id, plan_text),
        )
        timer = threading.Timer(self.delay, self._finish, args=(task_id, plan_text))
        timer.daemon = True
        timer.start()
        logger.info("生图任务已提交 task_id=%s", task_id)
        return task_id

    def _finish(self, task_id: str, plan_text: str) -> None:
        try:
            url = self.image_gen(plan_text)
            self.db.execute(
                "UPDATE tasks SET status='done', result_url=?, "
                "updated_at=datetime('now','localtime') WHERE task_id=?",
                (url, task_id),
            )
        except Exception as exc:  # 生图失败也落库，前端可展示错误
            logger.exception("生图任务执行失败 task_id=%s", task_id)
            self.db.execute(
                "UPDATE tasks SET status='error', error=?, "
                "updated_at=datetime('now','localtime') WHERE task_id=?",
                (str(exc), task_id),
            )

    def get_task(self, task_id: str) -> Optional[dict]:
        return self.db.query_one("SELECT * FROM tasks WHERE task_id = ?", (task_id,))