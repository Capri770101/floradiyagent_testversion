#!/usr/bin/env bash
# 部署真实 SSL 证书到 flora-frontends（nginx）容器。
# 用法: ./misc/deploy_ssl_cert.sh <证书目录> <域名>
#   例: ./misc/deploy_ssl_cert.sh /home/admin/cert_c c.tiaowulan.com
# 行为: 备份旧证书 -> 从 <证书目录> 找 .pem(证书) 与 .key(私钥) ->
#       复制到 misc/certs/{fullchain,privkey}.pem -> 重启 frontends -> 验证。
set -euo pipefail

if [ $# -lt 2 ]; then
  echo "用法: $0 <证书目录> <域名>"
  echo "例:   $0 /home/admin/cert_c c.tiaowulan.com"
  exit 1
fi

SRC_DIR="$1"
DOMAIN="$2"
MISC_DIR="$(cd "$(dirname "$0")" && pwd)"
CERTS_DIR="$MISC_DIR/certs"

if [ ! -d "$SRC_DIR" ]; then
  echo "✗ 证书目录不存在: $SRC_DIR"
  exit 1
fi

echo "==> [1/5] 备份旧证书"
mkdir -p "$CERTS_DIR"
TS="$(date +%Y%m%d_%H%M%S)"
[ -f "$CERTS_DIR/fullchain.pem" ] && cp -p "$CERTS_DIR/fullchain.pem" "$CERTS_DIR/fullchain.pem.bak.$TS"
[ -f "$CERTS_DIR/privkey.pem" ]  && cp -p "$CERTS_DIR/privkey.pem"  "$CERTS_DIR/privkey.pem.bak.$TS"
echo "  备份后缀: $TS"

echo "==> [2/5] 在 $SRC_DIR 中定位证书与私钥"
KEY_FILE="$(ls "$SRC_DIR"/*.key 2>/dev/null | grep -i "$DOMAIN" | head -1)"
[ -z "$KEY_FILE" ] && KEY_FILE="$(ls "$SRC_DIR"/*.key 2>/dev/null | head -1)"
CERT_FILE="$(ls "$SRC_DIR"/*.pem 2>/dev/null | grep -iE "fullchain|$DOMAIN" | head -1)"
[ -z "$CERT_FILE" ] && CERT_FILE="$(ls "$SRC_DIR"/*.pem 2>/dev/null | head -1)"

if [ -z "$KEY_FILE" ] || [ -z "$CERT_FILE" ]; then
  echo "✗ 未在 $SRC_DIR 找到 .pem / .key 证书文件"
  echo "  目录内容:"; ls -la "$SRC_DIR"
  exit 1
fi
echo "  证书: $CERT_FILE"
echo "  私钥: $KEY_FILE"

echo "==> [3/5] 安装新证书（按域名分别存放）"
CERT_DST="$CERTS_DIR/$DOMAIN.pem"
KEY_DST="$CERTS_DIR/$DOMAIN.key"
cp -p "$CERT_FILE" "$CERT_DST"
cp -p "$KEY_FILE"  "$KEY_DST"
chmod 644 "$CERT_DST"
chmod 600 "$KEY_DST"
echo "  已写入 $CERT_DST 与 $KEY_DST"

echo "==> [4/5] 重建并启动 frontends（应用新的证书挂载/配置）"
cd "$MISC_DIR"
docker compose up -d flora-frontends
for i in $(seq 1 20); do
  if curl -k -sS -o /dev/null "https://localhost/"; then break; fi
  sleep 2
done

echo "==> [5/5] 验证"
echo "--- 证书主题/签发者 ---"
echo | openssl s_client -connect localhost:443 -servername "$DOMAIN" 2>/dev/null \
  | openssl x509 -noout -subject -issuer -dates 2>/dev/null || echo "(openssl 校验跳过)"
HTTP_CODE="$(curl -k -sS -o /dev/null -w '%{http_code}' "https://localhost/")"
echo "curl https://localhost/ -> $HTTP_CODE"
echo "完成。请用浏览器访问 https://$DOMAIN/ 确认绿锁。"
