# Flora DIY Agent —— 常用开发指令（python 指向当前解释器，managed venv 下即 managed python）
PYTHON ?= python

.PHONY: help dev run test lint fmt docker-build docker-up clean

help:
	@echo "make dev          本地开发启动 (uvicorn --reload)"
	@echo "make run          生产式启动"
	@echo "make test         运行 pytest"
	@echo "make lint         ruff 检查"
	@echo "make fmt          ruff 自动修复 + 格式化"
	@echo "make docker-build 构建镜像"
	@echo "make docker-up    用 docker compose 启动"

dev:
	$(PYTHON) -m uvicorn api:app --port 8000 --reload

run:
	$(PYTHON) -m uvicorn api:app --port 8000

test:
	$(PYTHON) -m pytest -q

lint:
	$(PYTHON) -m ruff check .

fmt:
	$(PYTHON) -m ruff check --fix .
	$(PYTHON) -m ruff format .

docker-build:
	docker build -t flora-diy-agent .

docker-up:
	docker compose up -d

clean:
	rm -rf .ruff_cache .pytest_cache
