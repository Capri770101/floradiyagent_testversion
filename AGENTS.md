# 项目工作约定（AGENTS.md）

## 验证方式
- 除非用户明确说「验证 / 实时测试 / 实测」，否则**不要主动打开浏览器（Playwright）做验收**。
- 默认做法：改完代码、跑完本地静态检查（后端 pytest / 前端 eslint、vitest、build）即可，把结果留给用户自己验证。
- 用户说「验证」时才用 Playwright 逐项实测并回报。

## 常用检查命令
- 后端：`python -m pytest -q -c misc/pyproject.toml`（工作目录为项目根；测试分两处：`tests/` 后端业务 25 文件 + `agent/tests/` 智能体 13 文件，conftest 双份各自生效）
- 后端 lint：`python -m ruff check --config misc/pyproject.toml .`
- 前端：`npx eslint src`、`npx vitest run`、`npm run build`（工作目录为 `H5/`）
- 后端重启：查 8080 PID → Stop-Process → Start-Process `python -m uvicorn backend.api:app --host 127.0.0.1 --port 8080`（工作目录项目根）→ `/health` 探活；前端 Vite 5173 代理 /api。
- 配置读取 `misc/.env`（backend/config.py 指向）；密码/密钥都在 `.gitignore` 忽略列表内。

## 环境注意
- PowerShell 控制台中文会 GBK 乱码：中文输出写 UTF-8 临时文件（`C:\Users\Capri\AppData\Local\Temp\opencode\`）再读。
- 演示账号：`capri_demo/123456`（merchant，绑定 S001/S4c8080）；`customer_demo/123456`（user，C 端演示顾客）；`admin/admin123456`。
- 三端入口（本地 dev 同源、路径区分；Docker 部署后为 5173/5174/5175 三端口）：C 端 `http://localhost:5173/`、商家端 `http://localhost:5173/merchant.html`、管理端 `http://localhost:5173/admin.html`。
- 会话隔离：C 端令牌键 `floradiy_token`、商家端 `floradiy_merchant_token`、管理后台 `floradiy_admin_token`（三端互不干扰）；C 端 `/auth/login`、`/auth/phone-login` 拒绝 merchant/admin 角色，商家走 `/auth/merchant-login`、后台走 `/auth/admin-login`。
- `recommend_weights` 默认 0.4/0.4/0.2；定位键 `floradiy_location`（localStorage）。
