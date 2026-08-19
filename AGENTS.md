# 项目工作约定（AGENTS.md）

## 验证方式
- 除非用户明确说「验证 / 实时测试 / 实测」，否则**不要主动打开浏览器（Playwright）做验收**。
- 默认做法：改完代码、跑完本地静态检查（后端 pytest / 前端 eslint、vitest、build）即可，把结果留给用户自己验证。
- 用户说「验证」时才用 Playwright 逐项实测并回报。

## 常用检查命令
- 后端：`python -m pytest -q`（工作目录为项目根）
- 前端：`npx eslint src`、`npx vitest run`、`npm run build`（工作目录为 `H5/`）
- 后端重启：查 8080 PID → Stop-Process → Start-Process `python -m uvicorn api:app --host 127.0.0.1 --port 8080`（工作目录项目根）→ `/health` 探活；前端 Vite 5173 代理 /api。

## 环境注意
- PowerShell 控制台中文会 GBK 乱码：中文输出写 UTF-8 临时文件（`C:\Users\Capri\AppData\Local\Temp\opencode\`）再读。
- 演示账号：`capri_demo/123456`（merchant）；admin 后台独立入口 `http://localhost:5173/admin.html`，`admin/admin123456`。
- 会话隔离：C 端登录令牌键 `floradiy_token`，管理后台独立 `floradiy_admin_token`（互不干扰）；`/auth/login` 拒绝 admin 角色，后台登录走 `/auth/admin-login`（要求 role=admin）。
- `recommend_weights` 默认 0.4/0.4/0.2；定位键 `floradiy_location`（localStorage）。
