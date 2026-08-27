"""tasks/worker.py —— P3 任务队列 worker 入口。

启动：python -m backend.tasks.worker
（需 task_queue_enabled=True 且 Redis 可达；否则 queue_enabled() 为 False，worker 仍会启动但消费不到任务）
"""
from __future__ import annotations

from backend.tasks.queue import run_worker

if __name__ == '__main__':
    run_worker()
