"""全局配置：所有可调参数集中于此，密钥优先从环境变量（.env）读取，不在代码中硬编码。"""
import os
from pathlib import Path

from dotenv import load_dotenv

BASE_DIR = Path(__file__).resolve().parent
load_dotenv(BASE_DIR / ".env")


class Config:
    # ---------- 大模型（OpenAI 兼容接口） ----------
    # auto: 配置了 api_key 走真实模型，否则回退 mock（便于无密钥本地测试全链路）
    llm_backend: str = os.getenv("LLM_BACKEND", "auto")  # auto | openai | mock
    llm_api_key: str = os.getenv("LLM_API_KEY") or os.getenv("OPENAI_API_KEY", "")
    llm_base_url: str = os.getenv("LLM_BASE_URL", os.getenv("OPENAI_BASE_URL", "https://api.openai.com/v1"))
    # DeepSeek 示例：LLM_BASE_URL=https://api.deepseek.com/v1, LLM_MODEL=deepseek-chat
    # 通义千问兼容端点示例：https://dashscope.aliyuncs.com/compatible-mode/v1
    llm_model: str = os.getenv("LLM_MODEL", os.getenv("OPENAI_MODEL", "gpt-4o-mini"))
    llm_temperature: float = float(os.getenv("LLM_TEMPERATURE", "0.7"))
    llm_max_tokens: int = int(os.getenv("LLM_MAX_TOKENS", "1024"))
    llm_timeout: float = float(os.getenv("LLM_TIMEOUT", "60"))
    llm_max_retries: int = int(os.getenv("LLM_MAX_RETRIES", "2"))

    # ---------- AI 生图（供应商可切换） ----------
    image_provider: str = os.getenv("IMAGE_PROVIDER", "zhipu")  # zhipu | api2img | dashscope | mock
    image_api_key: str = os.getenv("IMAGE_API_KEY") or os.getenv("TONGYI_API_KEY", "")
    image_model: str = os.getenv("IMAGE_MODEL", os.getenv("TONGYI_IMAGE_MODEL", "wanx-v1"))
    # mock 生图模拟耗时（秒），真实生图通常需要数十秒
    image_task_delay: float = float(os.getenv("IMAGE_TASK_DELAY", "4"))
    # 真实生图任务创建/轮询的超时与间隔
    image_task_timeout: float = float(os.getenv("IMAGE_TASK_TIMEOUT", "120"))
    image_poll_interval: float = float(os.getenv("IMAGE_POLL_INTERVAL", "3"))

    # ---------- AI 生图：api2img（OpenAI 兼容中转商，低成本测试） ----------
    # 形如 https://api.xxx.com/v1（中转商提供，参考 github.com/MrVoler/api2img-skill）
    image_openai_base_url: str = os.getenv("IMAGE_OPENAI_BASE_URL", "")
    image_openai_api_key: str = os.getenv("IMAGE_OPENAI_API_KEY", "")
    image_openai_model: str = os.getenv("IMAGE_OPENAI_MODEL", "flux-1.1-pro")
    image_size: str = os.getenv("IMAGE_SIZE", "1024x1024")
    # 中转商可能返回 url 或 base64：base64 时本地落盘，以该地址对外提供访问
    image_result_base: str = os.getenv("IMAGE_RESULT_BASE", "http://127.0.0.1:8000")
    image_cache_dir: Path = BASE_DIR / "data" / "images"

    # ---------- AI 生图：智谱 CogView（cogview-3-flash 免费） ----------
    # 智谱开放平台: https://open.bigmodel.cn，API key 形如 "xxxx.xxxx"
    image_zhipu_base_url: str = os.getenv(
        "IMAGE_ZHIPU_BASE_URL", "https://open.bigmodel.cn/api/paas/v4")
    image_zhipu_api_key: str = os.getenv("IMAGE_ZHIPU_API_KEY", "")
    image_zhipu_model: str = os.getenv("IMAGE_ZHIPU_MODEL", "cogview-3-flash")
    # 免费模型共享额度易 429，重试次数与基础等待秒数
    image_zhipu_max_retries: int = int(os.getenv("IMAGE_ZHIPU_MAX_RETRIES", "5"))
    image_zhipu_retry_base: float = float(os.getenv("IMAGE_ZHIPU_RETRY_BASE", "15"))

    # ---------- 数据层 ----------
    db_path: Path = BASE_DIR / "data" / "agent.db"
    repository: str = os.getenv("REPOSITORY", "mock")  # mock（真实数据库接入预留位）

    # ---------- 智能体 ----------
    max_iterations: int = int(os.getenv("MAX_ITERATIONS", "8"))  # ReAct 循环上限
    history_limit: int = int(os.getenv("HISTORY_LIMIT", "20"))  # 每轮载入的历史条数
    system_persona: str = "你是一位专业、热情、耐心的花卉选购导购助手，通过微信小程序为用户服务。"