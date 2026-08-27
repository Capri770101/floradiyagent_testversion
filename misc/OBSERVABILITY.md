# P7 可观测性说明（OBSERVABILITY.md）

本文档描述 `/metrics` 指标口径、结构化日志字段与告警阈值建议。
实现位置：`backend/observability.py`（进程内采集），`GET /metrics` 暴露 Prometheus 文本格式。

## 1. 指标清单

| 指标名 | 类型 | 含义 |
|---|---|---|
| `http_requests_total` | counter | HTTP 请求总数 |
| `http_requests_2xx / 4xx / 5xx` | counter | 按状态码类分组的请求数（5xx 即错误率分母/分子） |
| `http_request_duration_ms{quantile="p95"}` | gauge | 近 2000 次请求的 P95 耗时（毫秒） |
| `http_qps` | gauge | 最近 60 秒平均每秒请求数 |
| `llm_requests_total` | counter | LLM 调用总次数 |
| `llm_requests_error` | counter | LLM 调用失败次数（provider 全部不可用） |
| `llm_prompt_tokens_total` | counter | 累计 prompt token 数 |
| `llm_completion_tokens_total` | counter | 累计 completion token 数 |
| `llm_cost_rmb_total` | gauge | 估算 LLM 成本（元；单价见 §3） |
| `image_requests_total` | counter | 生图任务总次数（落终态时计） |
| `image_success_total` | counter | 生图成功次数（`done`） |
| `rate_limited_total` | counter | 限流命中（返回 429）累计 |
| `uptime_seconds` | gauge | 进程运行时长（秒） |

快速查看：`curl http://127.0.0.1:8080/metrics`

## 2. 结构化日志字段

日志格式沿用 `%(asctime)s | %(levelname)s | %(name)s | %(message)s`，请求日志含：

- `request_id`（= trace_id，`X-Request-ID` 响应头）：`[a-f0-9]{12}`，每请求唯一，跨模块串联用。
- 方法与路径、状态码、耗时（ms）。

示例：
```
[3f1c9a2b4d5e] GET /api/catalog/plans -> 200 (23ms)
```

建议：生产若接日志平台，可把 `backend/config.py:setup_logging()` 的 format 改为 JSON 行
（`{"ts":..., "level":..., "name":..., "msg":...}`），或由采集端按 `|` 分隔解析。

## 3. LLM 成本估算口径

当前仅按 token 累计估算（`llm_cost_rmb_total`）：
- prompt：`¥1e-6 / token`
- completion：`¥2e-6 / token`

此为 DeepSeek 类模型近似单价，接入其他模型请按实际 `llm_providers` 单价调整
（`backend/observability.py:_llm_cost_rmb`）。

## 4. 告警阈值建议

| 告警项 | 指标 | 建议阈值 | 说明 |
|---|---|---|---|
| 5xx 错误率 | `rate(http_requests_5xx[5m]) / rate(http_requests_total[5m])` | > 1% 持续 5 分钟 | 业务异常率高需介入 |
| P95 耗时 | `http_request_duration_ms{quantile="p95"}` | > 1500ms 持续 5 分钟 | 响应慢，排查 DB/LLM 链路 |
| LLM 错误率 | `rate(llm_requests_error[5m]) / rate(llm_requests_total[5m])` | > 10% 持续 5 分钟 | 可能 provider 故障 / 熔断 |
| LLM 成本 | `increase(llm_cost_rmb_total[1h])` | > 预算阈值（按运营设置） | 成本异常爬升 |
| 生图成功率 | `rate(image_success_total[5m]) / rate(image_requests_total[5m])` | < 90% 持续 5 分钟 | 生图 provider 异常 |
| 限流命中 | `rate(rate_limited_total[5m])` | > 阈值（如 100/min） | 疑似攻击 / 配置过严 |
| worker / 进程存活 | `uptime_seconds` | 探测间隔内无变化 | 进程假死 / 崩溃 |
| Redis 连通 | 见 `RedisRateLimiter` 降级告警日志 | 降级即告警 | P4 Fail-Closed 语义 |

> 说明：以上为进程内单机口径；多 worker 部署时由 Prometheus 按 job 聚合后再计算阈值。
> Redis 连通性告警当前以日志 `ratelimit` 的降级 warning 形式暴露，未单列指标（如需可扩展）。