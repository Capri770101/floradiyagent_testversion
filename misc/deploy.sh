#!/usr/bin/env bash
# 一键部署脚本（在 ECS 上执行）：构建并启动全部服务，等待后端就绪。
# 前置：已安装 docker + docker compose v2；当前目录含 docker-compose.yml / Dockerfile* / nginx。
set -euo pipefail
cd "$(dirname "$0")"

echo "==> [1/4] 前置检查"
if [ ! -f .env ]; then
  echo "✗ 缺少 misc/.env，请先复制 .env.example 并填好密钥（JWT_SECRET / LLM_API_KEY / 支付 / 短信 等）"
  exit 1
fi
if [ ! -f certs/fullchain.pem ] || [ ! -f certs/privkey.pem ]; then
  echo "⚠ 未检测到 SSL 证书（misc/certs/fullchain.pem + privkey.pem）。将只提供 HTTP，建议放入证书后重启 frontends。"
fi

echo "==> [2/4] 构建并启动服务"
docker compose up -d --build

echo "==> [3/4] 等待后端 /health 就绪（最多 ~90s）"
READY=0
for i in $(seq 1 30); do
  if docker compose run --rm --no-deps flora-agent python -c "import urllib.request,sys; urllib.request.urlopen('http://flora-agent:8000/health', timeout=5); print('ok')" >/dev/null 2>&1; then
    echo "✓ 后端就绪"
    READY=1
    break
  fi
  sleep 3
done
[ "$READY" -eq 1 ] || { echo "✗ 后端未在预期时间内就绪，请查看 docker compose logs flora-agent"; exit 1; }

echo "==> [4/4] 部署完成"
docker compose ps

# 可选：灌入演示数据（演示账号/店铺）。取消下行注释后重新跑本脚本：
# docker compose run --rm flora-agent python -m backend.scripts.seed_demo
echo ""
echo "提示：访问 https://<你的域名>/ 、/merchant.html 、/admin.html 验证三端。"
echo "      查看日志：docker compose logs -f flora-agent"
