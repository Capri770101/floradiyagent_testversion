# 部署手册（flora_diy_agent · 阿里云 ECS 单机 + Docker Compose）

适用于：正式上线测试。架构为单台 ECS 上用 Docker Compose 跑
`postgres`(自托管) + `redis` + `flora-agent`(后端) + `flora-worker`(异步任务) + `flora-frontends`(nginx 三端)。

## 0. 服务器与环境
- 系统：Ubuntu/Alibaba Cloud Linux，已装 `docker` + `docker compose` v2。
- 域名（已备案）：`c.tiaowulan.com` / `admin.tiaowulan.com` / `merchant.tiaowulan.com` → ECS 公网 IP。
- 安全组放通 `22 / 80 / 443`。

## 1. 取代码
```bash
git clone <你的仓库> flora && cd flora
# 或本地改完 push 后，服务器上 git pull
```

## 2. 配置生产环境变量
```bash
cd misc
cp .env.example .env
# 编辑 .env，至少填：
#   JWT_SECRET=<openssl rand -hex 32>
#   LLM_API_KEY=<真实 key>
#   PUBLIC_BASE_URL=https://tiaowulan.com
#   AUTH_REQUIRED=true
#   CORS_ORIGINS=c.tiaowulan.com,admin.tiaowulan.com,merchant.tiaowulan.com
#   DATABASE_URL 与 REDIS_URL 已由 compose 注入，无需手填
#   PAYMENT_PROVIDER=wechat|alipay 及对应支付密钥（申请到后填）
#   SMS_PROVIDER=aliyun 及 SMS_* 密钥（申请到后填）
```

## 3. 放置 SSL 证书
将证书放到 `misc/certs/`：
- `fullchain.pem`
- `privkey.pem`
（nginx 已配置 443 + 80→443 跳转；证书被 .gitignore 忽略，切勿提交。）

## 4. 一键部署
```bash
cd misc
chmod +x deploy.sh
./deploy.sh
```
脚本会：构建镜像 → 启动服务 → 等待后端 `/health` 就绪 → 打印服务状态。

可选灌演示数据：取消 `deploy.sh` 末尾注释后重跑，或手动：
```bash
docker compose run --rm flora-agent python -m backend.scripts.seed_demo
```

## 5. 验证
- 三端页面：`https://c.tiaowulan.com/` 、`/merchant.html` 、`/admin.html`
- 后端探活：`curl https://<域名>/api/health`（nginx 已反代 `/api`）
- 日志：`docker compose logs -f flora-agent`

## 6. 备份（正式环境必做）
Postgres 数据在命名卷 `postgres-data`。定时备份示例（crontab）：
```bash
0 4 * * * docker compose -f /path/to/misc/docker-compose.yml exec -T postgres pg_dump -U flora flora > /backup/flora_$(date +\%F).sql
```

## 7. 常见问题
- **跨域 403**：检查 `.env` 的 `CORS_ORIGINS` 是否包含当前域名。
- **支付回调收不到**：确认微信/支付宝后台填的回调地址为
  `https://tiaowulan.com/api/pay/notify/wechat` 与 `.../alipay`，且 `WECHATPAY_NOTIFY_URL`/`ALIPAY_NOTIFY_URL` 已配。
- **短信发不出**：`SMS_PROVIDER=aliyun` 且 `SMS_ACCESS_KEY_ID/SECRET/SIGN_NAME/TEMPLATE_CODE` 齐全；dev 模式用固定码 `123456` 自测。
