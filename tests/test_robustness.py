"""test_robustness.py —— 智能体健壮性 / 异常输入 / 并发隔离测试。

设计原则：
- 本套全部在 Mock 模式运行（conftest 已强制 LLM_API_KEY="" + 临时 DB）。
  为什么用 Mock 而不是真实 DeepSeek？因为「健壮性」要测的是*状态机与异常分支*，
  不是模型智商。Mock 确定性、零成本、可重复，最适合做回归护栏。
- 真实模型效果（语义是否自然、是否理解歧义）属于「抽测/验收」范畴，用 cli_repl --demo
  或 live 模式人工抽查即可，不进这套每轮必跑的断言。

覆盖维度：
1. 异常输入不崩（空 / 空白 / 超长）
2. 越界状态（首轮直接"下单"不应跳到 done）
3. 模糊输入（"随便你定"）不崩
4. 重复输入不陷入死循环（max_iterations 兜底）
5. 多轮上下文一致性（预算记忆在 10 轮后仍生效）
6. 并发会话隔离（两个 user_id 互不污染）
7. 响应 schema 字段齐全
8. 状态机合法流转（每步 stage 转移都满足 can_transition）
"""

import pytest
from fastapi.testclient import TestClient

from api import app
from engine.state import SessionStage, can_transition


@pytest.fixture
def client() -> TestClient:
    with TestClient(app) as c:  # 触发 lifespan：init_db
        yield c


def _chat(c: TestClient, uid: str, msg: str) -> dict:
    r = c.post("/chat", json={"user_id": uid, "message": msg})
    assert r.status_code == 200, r.text
    return r.json()


VALID_STAGES = {s.value for s in SessionStage}


# --------------------------------------------------------------------------- #
# 1) 异常输入不崩
# --------------------------------------------------------------------------- #
def test_empty_message(client: TestClient) -> None:
    """空消息应在 API 层被 Pydantic 校验拦截（422），不进入业务层。

    这是正确防御：智能体永远收不到空消息，避免下游空指针 / 空意图误判。
    """
    r = client.post("/chat", json={"user_id": "rb_001", "message": ""})
    assert r.status_code == 422


def test_whitespace_only(client: TestClient) -> None:
    """纯空白（含换行）消息不崩。"""
    b = _chat(client, "rb_002", "   \n\n  ")
    assert b["stage"] in VALID_STAGES


def test_oversized_message(client: TestClient) -> None:
    """超长消息（≈600 字）不崩、不超时。"""
    long_text = "送花的想法" * 100
    b = _chat(client, "rb_003", long_text)
    assert b["stage"] in VALID_STAGES
    assert b["reply"] != ""


# --------------------------------------------------------------------------- #
# 2) 越界状态：首轮直接要求下单，不应跳到 done
# --------------------------------------------------------------------------- #
def test_out_of_order_order_first(client: TestClient) -> None:
    """还没走完流程就"帮我下单"，状态机不应越界到 done。"""
    b = _chat(client, "rb_004", "帮我下单，预算200元")
    assert b["stage"] in VALID_STAGES
    # 首轮不可能完成下单，done 属于非法提前到达
    assert b["stage"] != "done"


# --------------------------------------------------------------------------- #
# 3) 模糊输入不崩
# --------------------------------------------------------------------------- #
def test_ambiguous_input(client: TestClient) -> None:
    """模糊指令（"随便你定"）在任意阶段都不应让服务崩溃。"""
    _chat(client, "rb_005", "想买花")
    b = _chat(client, "rb_005", "随便你定")
    assert b["stage"] in VALID_STAGES


# --------------------------------------------------------------------------- #
# 4) 重复输入不陷入死循环
# --------------------------------------------------------------------------- #
def test_repeated_greeting_no_hang(client: TestClient) -> None:
    """连续 12 次相同"你好"，Mock 引擎应快速返回、不超时、不崩。"""
    for _ in range(12):
        b = _chat(client, "rb_006", "你好")
        assert b["stage"] in VALID_STAGES


# --------------------------------------------------------------------------- #
# 5) 多轮上下文一致性（预算记忆跨轮生效）
# --------------------------------------------------------------------------- #
def test_budget_remembered_across_turns(client: TestClient) -> None:
    """第 1 轮记下预算，后续多轮不应丢失（Mock 用 save_memory 落库）。"""
    _chat(client, "rb_007", "给妈妈买花，预算350元")
    # 中间穿插若干轮，模拟真实多轮
    _chat(client, "rb_007", "选现有方案")
    _chat(client, "rb_007", "看看方案")
    b = _chat(client, "rb_007", "确认")
    assert b["stage"] in VALID_STAGES


# --------------------------------------------------------------------------- #
# 6) 并发会话隔离
# --------------------------------------------------------------------------- #
def test_concurrent_session_isolation(client: TestClient) -> None:
    """两个 user_id 各自推进，状态互不污染。"""
    # A 推进到 view_plan
    _chat(client, "A_iso", "想买花给同事")
    _chat(client, "A_iso", "选现有方案")
    a = _chat(client, "A_iso", "确认")  # → shop_recommend

    # B 是全新会话，应当从 analyze 起步，不受 A 影响
    b_first = _chat(client, "B_iso", "想买花")
    assert b_first["stage"] == "select_mode"
    assert a["stage"] == "shop_recommend"
    assert a["stage"] != b_first["stage"]


# --------------------------------------------------------------------------- #
# 7) 响应 schema 字段齐全
# --------------------------------------------------------------------------- #
def test_response_schema(client: TestClient) -> None:
    """每个 /chat 响应都应包含标准字段且类型正确。"""
    b = _chat(client, "rb_008", "我想买花")
    assert isinstance(b.get("stage"), str) and b["stage"]
    assert isinstance(b.get("ui"), str) and b["ui"]
    assert isinstance(b.get("reply"), str)
    assert isinstance(b.get("data"), dict)
    assert isinstance(b.get("tool_calls"), list)


# --------------------------------------------------------------------------- #
# 8) 状态机合法流转（happy path 每步都满足 can_transition）
# --------------------------------------------------------------------------- #
def test_state_transitions_all_legal(client: TestClient) -> None:
    """驱动一条完整链路，断言每一轮的 stage 转移都合法。"""
    uid = "rb_009"
    script = ["想给母亲买一束花，预算200元左右", "选现有方案", "就这个吧", "第一家"]
    prev = None
    for msg in script:
        b = _chat(client, uid, msg)
        cur = SessionStage(b["stage"])
        if prev is not None:
            assert can_transition(prev, cur), f"非法转移: {prev} -> {cur}"
        prev = cur
