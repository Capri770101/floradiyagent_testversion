"""config.py —— 全部配置集中管理。

设计原则：
- 密钥优先从环境变量 / .env 读取，代码里不出现密钥字面值。
- 所有可调项都有默认值兜底，保证「零配置也能跑起来」（LLM 走 Mock，生图走 mock，数据走 Mock）。
- 其他模块统一通过 `from config import settings, setup_logging` 使用，避免散落硬编码。
- 「真实小程序接入」所需的全部字段都集中在本文件，替换 .env 中对应值即可上线，
  详见 INTEGRATION.md。

.env 解析由 pydantic-settings 完成；未提供时使用下面的默认值。
"""

from __future__ import annotations

from functools import lru_cache
from pathlib import Path

from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict

#: 服务根目录（config.py 所在目录）
BASE_DIR = Path(__file__).resolve().parent


class Settings(BaseSettings):
    """全局配置。字段名即环境变量名（不区分大小写）。"""

    model_config = SettingsConfigDict(
        env_file=str(BASE_DIR / ".env"),
        env_file_encoding="utf-8",
        extra="ignore",
        case_sensitive=False,
    )

    # ---- 应用基础 ----
    app_name: str = "flora-agent-service"
    log_level: str = "INFO"
    api_host: str = "0.0.0.0"
    api_port: int = 8000
    cors_origins: list[str] = Field(default_factory=list)
    cors_allow_credentials: bool = False  # 本项目鉴权用 Bearer Token（非 cookie），默认关闭；若确需 cookie 凭证，请将 CORS_ORIGINS 设为具体前端域名再置 True。
    debug: bool = False  # 仅开发用：开启 uvicorn --reload

    # ---- LLM（OpenAI 兼容接口）----
    llm_base_url: str = "https://api.openai.com/v1"
    llm_api_key: str = ""  # 留空 → 走内置 Mock 引擎
    llm_model: str = "gpt-4o-mini"
    llm_temperature: float = 0.3
    llm_max_tokens: int = 1500
    llm_timeout: float = 30.0
    llm_max_retries: int = 2

    # ---- 图像生成（provider 可切换：mock | dashscope | api2img | zhipu）----
    image_provider: str = "mock"  # "mock" | "dashscope" | "api2img" | "zhipu"
    # 通义万相 / DashScope
    image_api_key: str = ""
    image_base_url: str = (
        "https://dashscope.aliyuncs.com/api/v1/services/aigc/text2image/image-synthesis"
    )
    image_model: str = "wanx-v1"
    # 第三方中转商（api2img / cc-vibe 等 OpenAI 兼容生图网关）
    # 来自 https://github.com/MrVoler/api2img-skill 背后的中转商，成本约 ¥0.3/张，比万相(¥0.08)贵，仅作备选。
    api2img_base_url: str = ""  # 例：https://cc-vibe.com（代码会自动补 /v1）
    api2img_api_key: str = ""
    api2img_model: str = "gpt-image-2"
    api2img_size: str = "1024x1024"
    api2img_quality: str = "medium"
    api2img_output_format: str = "png"
    # 智谱 AI 文生图（CogView，cogview-3-flash 免费），OpenAI 兼容 /images/generations
    # 注意：智谱路径是 {base}/images/generations（不含 /v1），与 api2img 网关不同
    zhipu_base_url: str = "https://open.bigmodel.cn/api/paas/v4"
    zhipu_api_key: str = ""
    zhipu_model: str = "cogview-3-flash"
    zhipu_size: str = "1024x1024"
    # 中转商返回 base64，需落盘后由本服务托管 URL（维持 result_url 契约）
    generated_dir: str = str(BASE_DIR / "data" / "generated")

    # ---- 微信小程序登录 & JWT 鉴权 ----
    # 这三项填好即代表「接入真实小程序」：WECHAT_APPID/WECHAT_SECRET 在小程序后台获取，
    # JWT_SECRET 自己生成随机长串。AUTH_REQUIRED=true 时 /chat 强制校验 Bearer 令牌。
    wechat_appid: str = ""
    wechat_secret: str = ""
    wechat_code2session_url: str = "https://api.weixin.qq.com/sns/jscode2session"
    jwt_secret: str = ""  # 留空 → 进程内随机（仅本地联调，生产务必自设）
    jwt_expire_minutes: int = 60 * 24 * 7  # JWT 有效期（默认 7 天）
    auth_required: bool = False  # True=强制鉴权；False=dev 模式（/chat 仍可用 user_id 直连）

    # ---- 数据源（mock | remote）----
    # mock=内置示例数据（零依赖跑通）；remote=对接真实小程序后端（配置 REMOTE_API_BASE 即可）。
    # 后端需实现 INTEGRATION.md 中约定的端点，返回与 Mock 同形状的 JSON。
    data_source: str = "mock"  # "mock" | "remote"
    remote_api_base: str = ""  # 真实后端基址，如 https://your-backend.com/api
    remote_timeout: float = 5.0
    remote_plans_path: str = "/plans"          # GET ?keyword=
    remote_plan_detail_path: str = "/plans/{id}"  # GET 单方案
    remote_shops_path: str = "/shops"          # GET ?plan_id=&lat=&lng=
    remote_shop_detail_path: str = "/shops/{id}"  # GET 单店铺

    # ---- 支付跳转页（小程序内页路径，随真实小程序调整）----
    pay_page_path: str = "/pages/order/confirm"

    # ---- 存储 ----
    db_path: str = str(BASE_DIR / "data" / "agent_service.db")

    # ---- 智能体参数 ----
    max_iterations: int = 8          # ReAct 单轮最大迭代，超出则中止说明
    history_limit: int = 20         # 短期记忆每次载入最近 N 条
    request_timeout: float = 60.0    # 单请求全程超时兜底

    # ---- 知识库向量检索（RAG）----
    # 检索由 knowledge/store.py 实现：TF-IDF 向量空间 + 字符 n-gram 切词（纯 Python，零依赖、可离线）。
    # 混合策略：关键词命中保底 ∪ 向量语义召回（仅多 token/长自然语句触发），接口 query_knowledge 不变。
    rag_enabled: bool = True           # False=整体回退旧关键词行为，可一键回滚
    rag_top_k: int = 8                 # 单域语义召回上限（域条目少则实际全返回）
    rag_keyword_boost: float = 0.35    # 关键词命中在混合分中的加成（保证精确项排前面）
    rag_min_score: float = 0.03        # 仅向量命中（无关键词）纳入的最低余弦阈值

    @property
    def llm_enabled(self) -> bool:
        """是否启用真实 LLM：仅当配置了 api_key 时。否则 call_llm 走 Mock。"""
        return bool(self.llm_api_key)

    @property
    def image_enabled(self) -> bool:
        """是否启用真实生图：provider 非 mock，且对应 provider 的 key/base 已配置。

        - dashscope：需要 image_api_key
        - api2img：需要 api2img_api_key 且 api2img_base_url
        - zhipu：需要 zhipu_api_key 且 zhipu_base_url
        """
        if self.image_provider == "mock":
            return False
        if self.image_provider == "dashscope":
            return bool(self.image_api_key)
        if self.image_provider == "api2img":
            return bool(self.api2img_api_key) and bool(self.api2img_base_url)
        if self.image_provider == "zhipu":
            return bool(self.zhipu_api_key) and bool(self.zhipu_base_url)
        return False

    @property
    def auth_configured(self) -> bool:
        """微信登录所需的 appid/secret 是否齐备。"""
        return bool(self.wechat_appid) and bool(self.wechat_secret)

    @property
    def data_remote_configured(self) -> bool:
        """remote 数据源的基址是否配置。"""
        return self.data_source == "remote" and bool(self.remote_api_base)


@lru_cache
def get_settings() -> Settings:
    """进程级单例，避免重复解析 .env。"""
    return Settings()


#: 全局配置实例，其他模块直接 import 这个。
settings = get_settings()


def setup_logging() -> None:
    """初始化 root logger。

    注意：日志里绝不打印 api_key / image_api_key 等敏感字段，只记录输入摘要与工具序列。
    """
    import logging

    logging.basicConfig(
        level=getattr(logging, settings.log_level.upper(), logging.INFO),
        format="%(asctime)s | %(levelname)-5s | %(name)-14s | %(message)s",
        datefmt="%Y-%m-%d %H:%M:%S",
    )
