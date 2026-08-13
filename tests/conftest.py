"""pytest 公共配置：在任何项目模块导入前设定临时 DB + 强制 Mock 模式。"""

import os
import sys
import tempfile

# 用系统临时目录下的独立 DB，避免污染开发库
_TMP_DB = os.path.join(tempfile.gettempdir(), "flora_test_agent.db")
# 每次 pytest 进程启动时清空上一轮残留（会话/阶段会跨运行累积，导致状态机断言失真）
if os.path.exists(_TMP_DB):
    os.remove(_TMP_DB)
os.environ["DB_PATH"] = _TMP_DB
os.environ["LLM_API_KEY"] = ""        # 强制走内置 Mock 引擎
os.environ["IMAGE_PROVIDER"] = "mock"  # 生图用占位图

# 项目根目录加入 path，保证 import agent / api / tools 等可用
ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if ROOT not in sys.path:
    sys.path.insert(0, ROOT)
