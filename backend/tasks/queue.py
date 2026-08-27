"""tasks/queue.py —— P3 异步任务队列（Redis 列表 + 同步 redis 客户端）。

设计要点：
- 生图等耗时任务从请求路径移出，create_image_task 仅入队并返回 task_id，由 worker 消费。
- 未启用（task_queue_enabled=False）或 Redis 不可达时，调用方走同步 fallback，行为不变。
- 队列用 Redis list（LPUSH/BRPOP）+ JSON 负载，简单可靠；worker 进程阻塞消费。
- redis 客户端懒加载：未安装 redis 包不影响导入与同步模式。
"""
from __future__ import annotations

import asyncio
import json
import logging

from backend.config import settings

logger = logging.getLogger('taskq')
QUEUE_KEY = 'queue:image_tasks'

def _client():
    """懒加载同步 redis 客户端。"""
    import redis
    return redis.Redis.from_url(settings.redis_url, socket_connect_timeout=settings.redis_socket_timeout, decode_responses=True)

def queue_enabled() -> bool:
    """队列是否可用：开关开启且 Redis 可达才返回 True，否则回退同步。"""
    if not settings.task_queue_enabled or not settings.redis_url:
        return False
    try:
        _client().ping()
        return True
    except Exception:
        logger.warning('[taskq] Redis 不可达，任务队列不可用，回退同步执行')
        return False

def enqueue_image_task(task_id: str) -> None:
    """将生图任务入队。"""
    _client().rpush(QUEUE_KEY, json.dumps({'task_id': task_id}))

def run_worker() -> None:
    """worker 主循环：阻塞消费 image_tasks 队列，逐条生成并更新 DB。

    运行：python -m backend.tasks.worker（需 task_queue_enabled=True 且 Redis 可达）。
    """
    from backend.storage import tasks
    client = _client()
    logger.info('[taskq] worker 启动，监听 %s', QUEUE_KEY)
    while True:
        item = client.brpop(QUEUE_KEY, timeout=5)
        if not item:
            continue
        try:
            task_id = json.loads(item[1])['task_id']
        except (json.JSONDecodeError, KeyError):
            logger.warning('[taskq] 丢弃非法队列条目: %s', item[1])
            continue
        try:
            prompt = asyncio.run(tasks.get_task_prompt(task_id))
            status, url = tasks._generate_image(task_id, prompt)
            asyncio.run(tasks._persist_result(task_id, status, url, prompt))
            logger.info('[taskq] 任务 %s 完成 status=%s', task_id, status)
        except Exception:
            logger.exception('[taskq] 任务 %s 处理失败', task_id)
            try:
                asyncio.run(tasks._persist_result(task_id, 'failed', '', asyncio.run(tasks.get_task_prompt(task_id))))
            except Exception:
                pass
