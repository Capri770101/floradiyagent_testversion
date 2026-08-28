# 基于官方 slim 镜像，体积小、启动快
FROM python:3.12-slim

ENV PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1 \
    PIP_NO_CACHE_DIR=1 \
    PIP_INDEX_URL=https://mirrors.aliyun.com/pypi/simple/ \
    PIP_TRUSTED_HOST=mirrors.aliyun.com

WORKDIR /app

# 先装依赖（利用层缓存，仅 requirements 变动时才重装）
COPY misc/requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# 再拷源码
COPY . .

# 运行时需要落盘的目录
RUN mkdir -p data/generated

# 以非 root 用户运行，缩小容器逃逸攻击面（SSRF/提权防护）
RUN useradd -m -u 1000 appuser \
    && chown -R appuser:appuser /app
USER appuser

EXPOSE 8000

# 生产用多 worker；开发排查可改 --reload 或加 --workers 1
# 构建方式：docker build -f misc/Dockerfile .
CMD ["python", "-m", "uvicorn", "backend.api:app", "--host", "0.0.0.0", "--port", "8000"]
