"""生图确认关卡测试：generate_effect_image 必须经用户确认且仅在 IMAGE_GEN 阶段可调用。"""
import pytest

from agent import Agent, is_affirmative
from config import Config
from engine.llm import LLMResult
from engine.state import SessionStage
from runtime import init_runtime
from storage.db import Database
from storage.memory import Memory
from storage.repository import MockRepository
from storage.tasks import TaskManager
from tools import execute_tool


def _env(tmp_path):
    cfg = Config()
    cfg.image_task_delay = 0
    db = Database(tmp_path / "t.db")
    db.init_schema()
    memory = Memory(db)
    tasks = TaskManager(db, image_gen=lambda text: "https://mock/x.png", delay=0)
    init_runtime(cfg, MockRepository(), memory, tasks)
    return memory


def _new_session(memory: Memory, stage: SessionStage, user: str = "u1") -> dict:
    session = memory.new_session(user)
    memory.save_stage(user, session["session_id"], stage)
    return session


# ---------- 意图识别 ----------

def test_intent_affirmative():
    assert is_affirmative("好的，生成吧")
    assert is_affirmative("可以")
    assert is_affirmative("帮我生成效果图")
    assert is_affirmative("确认生成")
    assert not is_affirmative("不用了")
    assert not is_affirmative("不需要，跳过")
    assert not is_affirmative("算了")
    assert not is_affirmative("")


# ---------- 工具守卫 ----------

def test_rejected_outside_image_gen_stage(tmp_path):
    memory = _env(tmp_path)
    _new_session(memory, SessionStage.PLAN_CONFIRM)
    result = execute_tool("generate_effect_image", {"plan_text": "花束"})
    assert "不可直接生成效果图" in result


def test_requires_user_confirmation(tmp_path):
    memory = _env(tmp_path)
    session = _new_session(memory, SessionStage.IMAGE_GEN)
    result = execute_tool("generate_effect_image", {"plan_text": "花束"})
    assert "明确同意" in result
    assert memory.get_session_flag("u1", session["session_id"], "image_confirmed") == ""


def test_confirmed_then_submit_only_once(tmp_path):
    memory = _env(tmp_path)
    session = _new_session(memory, SessionStage.IMAGE_GEN)
    memory.set_session_flag("u1", session["session_id"], "image_confirmed", "1")

    first = execute_tool("generate_effect_image", {"plan_text": "康乃馨花束"})
    assert '"task_id"' in first and '"status": "pending"' in first

    second = execute_tool("generate_effect_image", {"plan_text": "再来一张"})
    assert "本轮确认已提交过" in second


def test_confirm_flag_cleared_on_new_entry(tmp_path):
    """每次进入 IMAGE_GEN 清除标记：重新生成必须再次确认。"""
    memory = _env(tmp_path)
    session = _new_session(memory, SessionStage.IMAGE_GEN)
    memory.set_session_flag("u1", session["session_id"], "image_confirmed", "1")
    memory.set_session_flag("u1", session["session_id"], "image_submitted", "1")

    agent = Agent(Config(), None, memory, MockRepository())
    agent._finalize(SessionStage.PLAN_CONFIRM, session["session_id"], "u1",
                    "再次确认", "text", {}, SessionStage.IMAGE_GEN.value, [])
    assert memory.get_session_flag("u1", session["session_id"], "image_confirmed") == ""
    assert memory.get_session_flag("u1", session["session_id"], "image_submitted") == ""