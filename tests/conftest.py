"""pytest 公共配置：临时 DB + 默认离线（纯逻辑单测零成本）。

双轨模式（去 Mock 后）：
- 默认 `pytest`：纯逻辑单测（不调 LLM），强制 LLM_API_KEY 为空避免误烧真实额度；
  带 @pytest.mark.live 的端到端测试在此模式自动 skip。
- `pytest -m live`：真实 DeepSeek 端到端抽测；此时保留 .env 中的 LLM_API_KEY。
  （代表性子集：`pytest -m "live and smoke"`。）
生图统一 IMAGE_PROVIDER=mock（占位图不烧额度），与「去 Mock 测试大脑」不冲突：
生图 provider 保留作线上降级，测试里需要可控生图时临时切 mock 即可。
"""

import os
import sys
import tempfile

# 是否显式要求 live（pytest -m live / -m "live and smoke"）
# 注意：不能用「子串匹配 live」，否则 `-m "not live and not smoke"` 会被误判为 live，
# 导致纯逻辑模式仍保留真实 LLM_API_KEY、调用真实 DeepSeek 而产生脆性失败。
# 正确判定：表达式里出现「live」且未被 `not` 否定，才算显式开启 live。
_M_IDX = sys.argv.index("-m") if "-m" in sys.argv else -1
_M_MARKER = sys.argv[_M_IDX + 1] if (_M_IDX >= 0 and _M_IDX + 1 < len(sys.argv)) else ""
_LIVE = bool(_M_MARKER) and "live" in _M_MARKER and "not live" not in _M_MARKER

# 用系统临时目录下的独立 DB，避免污染开发库
_TMP_DB = os.path.join(tempfile.gettempdir(), "flora_test_agent.db")
# 每次 pytest 进程启动时清空上一轮残留（会话/阶段会跨运行累积，导致状态机断言失真）
if os.path.exists(_TMP_DB):
    os.remove(_TMP_DB)
os.environ["DB_PATH"] = _TMP_DB
os.environ["IMAGE_PROVIDER"] = "mock"  # 生图统一占位，不烧额度
if not _LIVE:
    os.environ["LLM_API_KEY"] = ""  # 默认纯逻辑模式，隔离真实密钥

# 项目根目录加入 path，保证 import agent / api / tools 等可用
ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if ROOT not in sys.path:
    sys.path.insert(0, ROOT)

import pytest  # noqa: E402

from config import settings  # noqa: E402


@pytest.fixture(autouse=True)
def _live_requires_key(request: pytest.FixtureRequest) -> None:
    """live 测试需要真实 LLM：默认模式（key 被覆盖为空）下自动 skip。

    提示：`pytest -m live` 跑真实 DeepSeek 抽测；`pytest -m "live and smoke"` 跑代表性子集。
    """
    if "live" in request.keywords and not settings.llm_enabled:
        pytest.skip("live 测试需要 LLM_API_KEY（运行: pytest -m live）")


@pytest.fixture(autouse=True)
def _reset_rate_limiter(request: pytest.FixtureRequest) -> None:
    """每测试前清空限流计数：整个进程共享一个 TestClient IP 与内存滑动窗口，
    跨测试累积注册/登录会触发 429，污染无关用例（与 tests/test_rate_limit.py 同法）。"""
    if "rate_limit" in request.keywords:
        return  # 限流专项测试自管计数
    import api

    api._limiter._hits.clear()
