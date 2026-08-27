"""config.py —— 全部配置集中管理。

设计原则：
- 密钥优先从环境变量 / .env 读取，代码里不出现密钥字面值。
- 除 LLM 密钥外所有可调项都有默认值兜底（生图走 mock、数据走 Mock 即可零配置启动）；LLM 已移除 Mock 引擎，必须配置真实 LLM_API_KEY 才能跑通设计链路。
- 其他模块统一通过 `from backend.config import settings, setup_logging` 使用，避免散落硬编码。
- 「真实小程序接入」所需的全部字段都集中在本文件，替换 .env 中对应值即可上线，
  微信 / JWT / 远程数据源字段均已集中于本文件，按 .env 填充即可上线。

.env 解析由 pydantic-settings 完成；未提供时使用下面的默认值。
"""

from __future__ import annotations

from functools import lru_cache
from pathlib import Path

from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict

#: 服务根目录（backend/config.py 的上两级 = 项目根）
BASE_DIR = Path(__file__).resolve().parent.parent


class Settings(BaseSettings):
    """全局配置。字段名即环境变量名（不区分大小写）。"""

    model_config = SettingsConfigDict(
        env_file=str(BASE_DIR / "misc" / ".env"),
        env_file_encoding="utf-8",
        extra="ignore",
        case_sensitive=False,
    )

    # ---- 应用基础 ----
    app_name: str = "flora-agent-service"
    app_env: str = "dev"  # dev | staging | prod（prod 触发 fail-fast 启动断言，见 api.py lifespan）
    log_level: str = "INFO"
    api_host: str = "0.0.0.0"
    api_port: int = 8000
    cors_origins: list[str] = Field(default_factory=list)
    cors_allow_credentials: bool = False  # 本项目鉴权用 Bearer Token（非 cookie），默认关闭；若确需 cookie 凭证，请将 CORS_ORIGINS 设为具体前端域名再置 True。
    debug: bool = False  # 仅开发用：开启 uvicorn --reload

    # ---- LLM（OpenAI 兼容接口）----
    llm_base_url: str = "https://api.openai.com/v1"
    llm_api_key: str = ""  # 留空 → LLM 降级 mock 模式（agent 返回占位回复）；需真实对话时配置真实密钥
    llm_model: str = "gpt-4o-mini"
    llm_temperature: float = 0.3
    llm_max_tokens: int = 1500
    llm_timeout: float = 30.0
    llm_max_retries: int = 2

    # ---- LLM 可靠性 / 多 provider / 成本（P6）----
    # 多 provider 兜底：JSON 数组 [{"name","base_url","api_key","model"}]；
    # 留空则只用上方单 provider（llm_base_url/key/model）。primary 失败自动切 secondary。
    llm_providers: str = ""
    # 熔断：连续失败达阈值进入 OPEN（快速失败 + 降级），半开探测恢复
    llm_circuit_breaker_enabled: bool = True
    llm_cb_failure_threshold: int = 5
    llm_cb_open_seconds: float = 30.0
    # 重试：指数退避 + 抖动，仅对可重试错误（超时/5xx/限流）生效
    llm_retry_max_attempts: int = 3
    llm_retry_base_delay: float = 0.5
    llm_retry_max_delay: float = 8.0
    # 成本预算（Redis 计数器，best-effort；0 = 不限制）
    llm_cost_enabled: bool = False
    llm_global_daily_token_budget: int = 0
    llm_user_daily_token_budget: int = 0

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
    # 商家端上传图片落盘目录（商品图 / 店铺图），经 /uploads 静态托管
    upload_dir: str = str(BASE_DIR / "data" / "uploads")
    upload_max_bytes: int = 5 * 1024 * 1024  # 单图上限 5MB
    # 生图下载白名单：仅允许从这些域名下载第三方生图服务返回的图片直链（防 SSRF）。
    # 默认覆盖官方 dashscope / 智谱 hosts 及其图片 CDN（智谱出图落在 UCloud ufileos 对象存储，
    # 形如 *.cn-wlcb.ufileos.com）；运行时还会自动并入已配置的 api2img/zhipu base 主机（见 image_download_hosts）。
    # 若切换/接入新的生图中转商且其图片直链域不在下表，请在此补充对应后缀，否则会被 SSRF 闸门拦截并降级为占位图。
    image_download_allowed_hosts: list[str] = Field(
        default_factory=lambda: [
            "aliyuncs.com",
            "dashscope.aliyuncs.com",
            "open.bigmodel.cn",
            "bigmodel.cn",
            "cn-wlcb.ufileos.com",
            "ufileos.com",
        ]
    )

    # ---- 微信小程序登录 & JWT 鉴权 ----
    # 这三项填好即代表「接入真实小程序」：WECHAT_APPID/WECHAT_SECRET 在小程序后台获取，
    # JWT_SECRET 自己生成随机长串。AUTH_REQUIRED=true 时 /chat 强制校验 Bearer 令牌。
    wechat_appid: str = ""
    wechat_secret: str = ""
    wechat_code2session_url: str = "https://api.weixin.qq.com/sns/jscode2session"
    jwt_secret: str = ""  # 留空 → 进程内随机（仅本地联调，生产务必自设）
    jwt_expire_minutes: int = 60 * 24 * 7  # JWT 有效期（默认 7 天）
    auth_required: bool = False  # True=强制鉴权；False=dev 模式（/chat 仍可用 user_id 直连）

    # ---- 手机号注册/登录（短信验证码）----
    # 未接真实短信通道时，dev 模式使用固定验证码（sms_dev_code）即可跑通全链路；
    # 生产接入通道后，把 issue 验证码的实现替换为真实发送即可（接口不变）。
    sms_dev_code: str = "123456"          # dev 固定验证码（sms_provider=dev 时生效）
    sms_provider: str = "dev"             # dev | real（real 需自行实现发送通道）
    phone_code_ttl_seconds: int = 300     # 验证码有效期（秒）

    # ---- 腾讯位置服务（地图选点 / 逆地理编码）----
    # 前端 H5/.env 的 VITE_TENCENT_MAP_KEY 用于地图 SDK 加载（前端可见）；
    # 后端此 key 用于 WebService API（逆地理编码），应配置独立的 key 或同一 key + 域名白名单。
    tencent_map_key: str = ""
    tencent_geocode_url: str = "https://apis.map.qq.com/ws/geocoder/v1/"

    # ---- 订单支付超时（分钟）----
    # created / pending_payment 的订单超过该时长未支付，读取时懒过期自动取消（并返还优惠券）。
    order_pay_timeout_minutes: int = 30

    # ---- 内容审核（阶段5 机审兜底）----
    # dev 默认放行（content_review_enabled=false），不干扰开发联调；
    # prod 开启后，商家上传的商品图/店铺图先过内容安全 API，违规 400 拦截。
    # 真实接入：CONTENT_REVIEW_URL 指向内容安全服务（智谱/阿里云内容安全等），
    # 实现见 backend/review.py 的 _review_remote（当前为占位放行实现）。
    content_review_enabled: bool = False
    content_review_url: str = ""
    content_review_api_key: str = ""
    content_review_timeout: float = 5.0
    # 机审 Fail-Closed：content_review_enabled=True 但真实 API 未接入（CONTENT_REVIEW_URL 空）时，
    # True=拒绝上传并告警（生产推荐，避免占位放行导致内容风险敞口）；
    # False=放行 + warning（dev 默认，不干扰联调）。真实 API 接入后本开关不再触发。
    content_review_fail_closed: bool = False

    # ---- 数据源（mock | remote）----
    # mock=内置示例数据（零依赖跑通）；remote=对接真实小程序后端（配置 REMOTE_API_BASE 即可）。
    # 后端需按 config 中 remote_*_path 约定的端点返回与 MockRepository 同形状的 JSON。
    data_source: str = "mock"  # "mock" | "remote"
    remote_api_base: str = ""  # 真实后端基址，如 https://your-backend.com/api
    remote_timeout: float = 5.0
    remote_plans_path: str = "/plans"          # GET ?keyword=
    remote_plan_detail_path: str = "/plans/{id}"  # GET 单方案
    remote_shops_path: str = "/shops"          # GET ?plan_id=&lat=&lng=
    remote_shop_detail_path: str = "/shops/{id}"  # GET 单店铺

    # ---- 支付跳转页（小程序内页路径，随真实小程序调整）----
    pay_page_path: str = "/pages/order/confirm"

    # ---- 支付网关（sandbox | wechat | alipay）----
    # sandbox=演示（无需凭据，下单即标记支付成功，用于端到端验证，绝不真实扣款）；
    # wechat=微信支付 v3 JSAPI（小程序 wx.requestPayment）；alipay=支付宝手机网站支付。
    # 真实渠道凭据从环境变量注入，本文件不出现任何密钥字面值；缺凭据时 /pay 明确返回 400。
    payment_provider: str = "sandbox"
    # 微信支付 v3
    wechatpay_mch_id: str = ""            # 商户号
    wechatpay_appid: str = ""            # 小程序 appid（可留空，自动复用 WECHAT_APPID）
    wechatpay_api_v3_key: str = ""       # 32 字节 APIv3 密钥（回调 AES-GCM 解密用）
    wechatpay_serial_no: str = ""        # 商户 API 证书序列号
    wechatpay_private_key: str = ""      # 商户私钥 PEM（内容或文件路径）
    wechatpay_public_cert: str = ""      # 微信平台证书 PEM（回调验签用，强烈建议配置）
    wechatpay_notify_url: str = ""       # 支付成功回调地址（如 https://api.xxx.com/pay/notify/wechat）
    # 支付宝
    alipay_app_id: str = ""
    alipay_private_key: str = ""         # 应用私钥 PEM（内容或文件路径）
    alipay_public_key: str = ""          # 支付宝公钥 PEM（回调验签用）
    alipay_notify_url: str = ""          # 支付成功回调地址
    alipay_gateway: str = "https://openapi.alipay.com/gateway.do"

    # ---- 存储 ----
    db_path: str = str(BASE_DIR / "data" / "agent_service.db")
    # P1：PostgreSQL 连接串（异步，asyncpg）。留空 → 沿用 db_path 的本地 SQLite（dev/test 零配置）。
    # 形如：postgresql+asyncpg://user:pass@host:5432/dbname
    database_url: str = ""

    # ---- 异步任务队列（P3：生图 / 通知 / 机审 移出请求路径）----
    # False=关闭，生图等耗时任务在请求内同步执行（现状，零依赖）；
    # True=开启，任务入 Redis 队列由 worker 进程消费（需配置 redis_url）。
    task_queue_enabled: bool = False

    # ---- Redis（P0 基础设施：限流 / 缓存 / 任务队列统一入口）----
    # 留空 = 不启用 Redis，相关能力（限流/缓存）自动降级到本地实现（dev/test 默认）。
    # prod 必须配置，否则启动 fail-fast（见 api.py lifespan 断言）。
    redis_url: str = ""  # 例：redis://127.0.0.1:6379/0 或 rediss://<host>:6379/0
    redis_pool_max_connections: int = 50
    redis_socket_timeout: float = 5.0

    # ---- 对象存储（P0 基础设施：生图 / 上传统一存储后端）----
    # local = 沿用本地磁盘 + /uploads、/generated 静态托管（dev 默认，零配置）。
    # s3 / oss = 对象存储 + CDN，生产推荐（避免多实例磁盘不共享、便于备份）。
    storage_backend: str = "local"          # local | s3 | oss
    storage_bucket: str = ""
    storage_endpoint: str = ""              # S3 兼容 / OSS endpoint（oss 可留空走内网）
    storage_region: str = ""
    storage_cdn_base: str = ""             # 对外访问基址，如 https://cdn.example.com
    storage_access_key: str = ""           # 对象存储 AK（prod 建议经密钥服务注入，勿落 .env 明文）
    storage_secret_key: str = ""

    # ---- 智能体参数 ----
    max_iterations: int = 8          # ReAct 单轮最大迭代，超出则中止说明
    history_limit: int = 20         # 短期记忆每次载入最近 N 条
    request_timeout: float = 180.0   # 单请求全程超时兜底（DIY 定制含多次 LLM 调用，放宽至 3 分钟）

    # ---- 接口限流（内存滑动窗口；防刷 LLM 账单 / 撞验证码）----
    rate_limit_enabled: bool = True  # False=整体关闭（仅限压测/联调）
    rate_limit_chat_per_minute: int = 30      # /chat 每 IP 每分钟（付费 LLM，重点保护）
    rate_limit_image_per_minute: int = 10     # /image/generate 每 IP 每分钟（付费生图，重点保护）
    rate_limit_auth_per_minute: int = 120     # /auth/login|register|wx-login 每 IP 每分钟
    rate_limit_phone_per_minute: int = 3      # /auth/phone-code 每手机号每分钟（防短信轰炸）
    rate_limit_phone_login_per_minute: int = 10  # /auth/phone-login 每手机号每分钟（防撞 6 位码）

    # ---- 知识库向量检索（RAG）----
    # 检索由 knowledge/store.py 实现：TF-IDF 向量空间 + 字符 n-gram 切词（纯 Python，零依赖、可离线）。
    # 混合策略：关键词命中保底 ∪ 向量语义召回（仅多 token/长自然语句触发），接口 query_knowledge 不变。
    rag_enabled: bool = True           # False=整体回退旧关键词行为，可一键回滚
    rag_top_k: int = 8                 # 单域语义召回上限（域条目少则实际全返回）
    rag_keyword_boost: float = 0.35    # 关键词命中在混合分中的加成（保证精确项排前面）
    rag_min_score: float = 0.03        # 仅向量命中（无关键词）纳入的最低余弦阈值

    @property
    def llm_enabled(self) -> bool:
        """是否配置了真实 LLM 密钥。False 时 call_llm 会直接抛 RuntimeError（已弃用 Mock 引擎）。"""
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
    def image_download_hosts(self) -> list[str]:
        """生图下载允许的 host 集合：白名单默认值 + 运行时从已配置 provider base 派生。

        这样即使将来用户自定义了 api2img/zhipu 中转地址，其图片直链 host 也自动纳入管控，
        无需手动维护白名单（仍受 _is_safe_image_url 的 IP 私网校验兜底）。
        """
        from urllib.parse import urlparse

        hosts = list(self.image_download_allowed_hosts)
        for base in (self.api2img_base_url, self.zhipu_base_url, self.image_base_url):
            if not base:
                continue
            host = urlparse(base).hostname
            if host and host not in hosts:
                hosts.append(host)
        return hosts

    @property
    def auth_configured(self) -> bool:
        """微信登录所需的 appid/secret 是否齐备。"""
        return bool(self.wechat_appid) and bool(self.wechat_secret)

    @property
    def data_remote_configured(self) -> bool:
        """remote 数据源的基址是否配置。"""
        return self.data_source == "remote" and bool(self.remote_api_base)

    @property
    def payment_configured(self) -> bool:
        """当前支付渠道是否已配置完整凭据（sandbox 恒为 True）。"""
        if self.payment_provider == "wechat":
            return bool(
                self.wechatpay_mch_id
                and (self.wechatpay_appid or self.wechat_appid)
                and self.wechatpay_api_v3_key
                and self.wechatpay_serial_no
                and self.wechatpay_private_key
            )
        if self.payment_provider == "alipay":
            return bool(self.alipay_app_id and self.alipay_private_key and self.alipay_public_key)
        return True  # sandbox 无需凭据


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
