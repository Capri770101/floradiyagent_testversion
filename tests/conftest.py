"""测试环境准备：保证从项目根目录导入模块，并对 api 生效 mock 配置。"""
import os
import sys
from pathlib import Path

os.environ.setdefault("LLM_BACKEND", "mock")       # 测试不依赖外部密钥
os.environ.setdefault("IMAGE_PROVIDER", "mock")
os.environ.setdefault("IMAGE_TASK_DELAY", "0.2")   # 生图任务快速完成，便于轮询测试

PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))