"""backend/observability.py —— P7 可观测性：进程内指标采集 + Prometheus 文本渲染。

设计要点：
- 单进程内存实现（零依赖，dev/单 worker 直接可用）；多 worker 部署时指标按进程
  独立，由 Prometheus 按 job 聚合即可。
- 关键字段：QPS、P95 耗时、错误率、LLM token/成本、生图成功率、限流命中。
- ``render_metrics()`` 输出 Prometheus 文本格式，供 ``GET /metrics`` 暴露。
- 另提供结构化日志辅助（trace_id / user_id），middleware 侧使用。
"""
from __future__ import annotations

import threading
import time
from collections import deque
from typing import Any

_lock = threading.Lock()
_started = time.time()
_metrics: dict[str, float] = {
    'http_requests_total': 0.0,
    'http_requests_2xx': 0.0,
    'http_requests_4xx': 0.0,
    'http_requests_5xx': 0.0,
    'llm_requests_total': 0.0,
    'llm_requests_error': 0.0,
    'llm_prompt_tokens': 0.0,
    'llm_completion_tokens': 0.0,
    'image_requests_total': 0.0,
    'image_success': 0.0,
    'rate_limited_total': 0.0,
}
_latency: deque[float] = deque(maxlen=2000)
_qps: deque[float] = deque()


def record_request(status: int, elapsed_ms: float) -> None:
    """记录一次 HTTP 请求（状态码 + 耗时毫秒）。"""
    now = time.time()
    with _lock:
        _metrics['http_requests_total'] += 1
        if 200 <= status < 300:
            _metrics['http_requests_2xx'] += 1
        elif 400 <= status < 500:
            _metrics['http_requests_4xx'] += 1
        else:
            _metrics['http_requests_5xx'] += 1
        _latency.append(elapsed_ms)
        _qps.append(now)


def record_llm(prompt_tokens: int = 0, completion_tokens: int = 0, error: bool = False) -> None:
    """记录一次 LLM 调用（token 数 / 是否失败）。"""
    with _lock:
        _metrics['llm_requests_total'] += 1
        if error:
            _metrics['llm_requests_error'] += 1
        _metrics['llm_prompt_tokens'] += max(0, int(prompt_tokens or 0))
        _metrics['llm_completion_tokens'] += max(0, int(completion_tokens or 0))


def record_image(success: bool) -> None:
    """记录一次生图结果（成功 / 失败）。"""
    with _lock:
        _metrics['image_requests_total'] += 1
        if success:
            _metrics['image_success'] += 1


def record_rate_limited() -> None:
    """记录一次限流命中（返回 429）。"""
    with _lock:
        _metrics['rate_limited_total'] += 1


def _p95() -> float:
    if not _latency:
        return 0.0
    vals = sorted(_latency)
    idx = max(0, min(len(vals) - 1, int(len(vals) * 0.95)))
    return round(vals[idx], 2)


def _qps_now() -> float:
    """最近 60 秒内每秒请求数（QPS）。"""
    now = time.time()
    with _lock:
        while _qps and now - _qps[0] > 60:
            _qps.popleft()
        return round(len(_qps) / 60.0, 3)


def _llm_cost_rmb() -> float:
    """按 token 估算 LLM 成本（仅统计口径，单价取近似值，见告警文档）。"""
    p = _metrics['llm_prompt_tokens']
    c = _metrics['llm_completion_tokens']
    return round(p * 1e-6 + c * 2e-6, 6)


def _uptime_seconds() -> float:
    return round(time.time() - _started, 2)


def snapshot() -> dict[str, Any]:
    """返回当前指标快照（JSON 友好），供调试 / 日志使用。"""
    with _lock:
        snap = {k: v for k, v in _metrics.items()}
    snap['http_p95_ms'] = _p95()
    snap['http_qps'] = _qps_now()
    snap['llm_cost_rmb'] = _llm_cost_rmb()
    snap['uptime_seconds'] = _uptime_seconds()
    return snap


def render_metrics() -> str:
    """渲染 Prometheus 文本格式（text/plain; version=0.0.4）。"""
    s = snapshot()
    lines: list[str] = []
    lines.append('# HELP http_requests_total HTTP 请求总数')
    lines.append('# TYPE http_requests_total counter')
    lines.append(f'http_requests_total {int(s["http_requests_total"])}')
    lines.append('# TYPE http_requests_2xx counter')
    lines.append(f'http_requests_2xx {int(s["http_requests_2xx"])}')
    lines.append('# TYPE http_requests_4xx counter')
    lines.append(f'http_requests_4xx {int(s["http_requests_4xx"])}')
    lines.append('# TYPE http_requests_5xx counter')
    lines.append(f'http_requests_5xx {int(s["http_requests_5xx"])}')
    lines.append('# TYPE http_request_duration_ms gauge')
    lines.append(f'http_request_duration_ms{{quantile="p95"}} {s["http_p95_ms"]}')
    lines.append('# TYPE http_qps gauge')
    lines.append(f'http_qps {s["http_qps"]}')
    lines.append('# TYPE llm_requests_total counter')
    lines.append(f'llm_requests_total {int(s["llm_requests_total"])}')
    lines.append('# TYPE llm_requests_error counter')
    lines.append(f'llm_requests_error {int(s["llm_requests_error"])}')
    lines.append('# TYPE llm_prompt_tokens_total counter')
    lines.append(f'llm_prompt_tokens_total {int(s["llm_prompt_tokens"])}')
    lines.append('# TYPE llm_completion_tokens_total counter')
    lines.append(f'llm_completion_tokens_total {int(s["llm_completion_tokens"])}')
    lines.append('# TYPE llm_cost_rmb_total gauge')
    lines.append(f'llm_cost_rmb_total {s["llm_cost_rmb"]}')
    lines.append('# TYPE image_requests_total counter')
    lines.append(f'image_requests_total {int(s["image_requests_total"])}')
    lines.append('# TYPE image_success_total counter')
    lines.append(f'image_success_total {int(s["image_success"])}')
    lines.append('# TYPE rate_limited_total counter')
    lines.append(f'rate_limited_total {int(s["rate_limited_total"])}')
    lines.append('# TYPE uptime_seconds gauge')
    lines.append(f'uptime_seconds {s["uptime_seconds"]}')
    return '\n'.join(lines) + '\n'
