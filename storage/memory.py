"""记忆管理：

- 短期记忆：按 user_id 持久化的会话消息历史（SQLite，重启不丢）；
- 会话状态：SessionStage 的持久化；
- 长期记忆：memories 表存用户偏好 KV，对话开始读入，模型经 save_memory 写入；
- 订单：orders 表记录，供下单技能与前端查询。
"""
import json
import logging
import uuid
from typing import List, Optional

from storage.db import Database
from engine.state import SessionStage

logger = logging.getLogger(__name__)


class Memory:
    def __init__(self, db: Database) -> None:
        self.db = db

    # ---------- 短期记忆：消息历史 ----------
    def append_message(self, user_id: str, role: str, content: str) -> None:
        self.db.execute(
            "INSERT INTO messages (user_id, role, content) VALUES (?, ?, ?)",
            (user_id, role, content),
        )

    def get_history(self, user_id: str, limit: int = 20) -> List[dict]:
        """返回 OpenAI 消息格式的历史列表（JSON 反序列化）。"""
        rows = self.db.query(
            "SELECT content FROM messages WHERE user_id = ? ORDER BY id",
            (user_id,),
        )
        history: List[dict] = []
        for r in rows[-limit:]:
            try:
                history.append(json.loads(r["content"]))
            except (json.JSONDecodeError, TypeError):
                logger.warning("历史消息反序列化失败，跳过: %s", r["content"][:80])
        return history

    def clear_history(self, user_id: str) -> None:
        self.db.execute("DELETE FROM messages WHERE user_id = ?", (user_id,))
        self.db.execute("DELETE FROM sessions WHERE user_id = ?", (user_id,))

    # ---------- 会话状态 ----------
    def new_session(self, user_id: str) -> dict:
        session_id = uuid.uuid4().hex[:12]
        self.db.execute(
            "INSERT OR REPLACE INTO sessions (user_id, session_id, stage) VALUES (?, ?, ?)",
            (user_id, session_id, SessionStage.ANALYZE.value),
        )
        return {"session_id": session_id, "stage": SessionStage.ANALYZE.value}

    def load_session(self, user_id: str, session_id: str) -> Optional[dict]:
        return self.db.query_one(
            "SELECT session_id, stage FROM sessions WHERE user_id = ? AND session_id = ?",
            (user_id, session_id),
        )

    def latest_session(self, user_id: str) -> Optional[dict]:
        return self.db.query_one(
            "SELECT session_id, stage FROM sessions WHERE user_id = ? "
            "ORDER BY updated_at DESC, session_id DESC LIMIT 1",
            (user_id,),
        )

    def save_stage(self, user_id: str, session_id: str, stage: SessionStage) -> None:
        self.db.execute(
            "INSERT OR REPLACE INTO sessions (user_id, session_id, stage, updated_at) "
            "VALUES (?, ?, ?, datetime('now', 'localtime'))",
            (user_id, session_id, stage.value),
        )

    # ---------- 会话内标记（生图确认等关卡控制） ----------
    def set_session_flag(self, user_id: str, session_id: str, key: str, value: str) -> None:
        self.db.execute(
            "INSERT OR REPLACE INTO session_flags (user_id, session_id, key, value, updated_at) "
            "VALUES (?, ?, ?, ?, datetime('now', 'localtime'))",
            (user_id, session_id, key, value),
        )

    def get_session_flag(self, user_id: str, session_id: str, key: str) -> str:
        row = self.db.query_one(
            "SELECT value FROM session_flags WHERE user_id = ? AND session_id = ? AND key = ?",
            (user_id, session_id, key),
        )
        return row["value"] if row else ""

    def clear_session_flags(self, user_id: str, session_id: str, prefix: str = "") -> None:
        if prefix:
            self.db.execute(
                "DELETE FROM session_flags WHERE user_id = ? AND session_id = ? AND key LIKE ?",
                (user_id, session_id, f"{prefix}%"),
            )
        else:
            self.db.execute(
                "DELETE FROM session_flags WHERE user_id = ? AND session_id = ?",
                (user_id, session_id),
            )

    # ---------- 长期记忆：用户偏好 ----------
    def get_memories(self, user_id: str) -> dict:
        rows = self.db.query("SELECT key, value FROM memories WHERE user_id = ?", (user_id,))
        return {r["key"]: r["value"] for r in rows}

    def save_memory(self, user_id: str, key: str, value: str) -> None:
        self.db.execute(
            "INSERT OR REPLACE INTO memories (user_id, key, value, updated_at) "
            "VALUES (?, ?, ?, datetime('now', 'localtime'))",
            (user_id, key, value),
        )
        logger.info("记忆写入 user=%s key=%s", user_id, key)

    # ---------- 订单 ----------
    def create_order(self, user_id: str, plan_type: str, plan_name: str,
                     price: float, quantity: int, shop_id: str) -> dict:
        order_id = f"O{uuid.uuid4().hex[:10].upper()}"
        total = round(price * quantity, 2)
        self.db.execute(
            "INSERT INTO orders (order_id, user_id, plan_type, plan_name, price,"
            " quantity, total_price, shop_id) VALUES (?, ?, ?, ?, ?, ?, ?, ?)",
            (order_id, user_id, plan_type, plan_name, price, quantity, total, shop_id),
        )
        return {
            "order_id": order_id,
            "user_id": user_id,
            "plan_type": plan_type,
            "plan_name": plan_name,
            "price": price,
            "quantity": quantity,
            "total_price": total,
            "shop_id": shop_id,
            "status": "pending",
        }

    def get_order(self, order_id: str) -> Optional[dict]:
        return self.db.query_one("SELECT * FROM orders WHERE order_id = ?", (order_id,))