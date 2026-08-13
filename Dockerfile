# 基于官方 slim 镜像，体积小、启动快
FROM python:3.12-slim

ENV PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1 \
    PIP_NO_CACHE_DIR=1

WORKDIR /app

# 先装依赖（利用层缓存，仅 requirements 变动时才重装）
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# 再拷源码
COPY . .

# 运行时需要落盘的目录
RUN mkdir -p data/generated

EXPOSE 8000

# 生产用多 worker；开发排查可改 --reload 或加 --workers 1
CMD ["python", "-m", "uvicorn", "api:app", "--host", "0.0.0.0", "--port", "8000"]
