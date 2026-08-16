# TODO：微信网页登录（OAuth2 授权）接入

> 状态：**待实现**。当前 H5 仅支持「微信内置浏览器内 `wx.login()`（小程序 API）」+ 手机号验证码登录。
> 用户暂无认证公众号 / 微信开放平台账号，等资质齐全后按本文接入。

## 目标

H5 在**任意浏览器**（含 PC）中提供真正的微信登录：

- 手机微信里打开 H5 → 公众号网页授权（静默 `snsapi_base`）→ 自动登录
- PC 浏览器 → 微信开放平台扫码登录（`snsapi_login`）

两条通道后端逻辑一致：`code → sns/oauth2/access_token → openid`，复用现有 `security.wx_login_user()` 自动建档/登录。

## 与现有实现的区别（重要）

| 通道 | 授权地址 | 换 openid 接口 | AppID 来源 |
| --- | --- | --- | --- |
| 小程序（现有 `/auth/wx-login`） | `wx.login()` 拿 code | `sns/jscode2session` | 小程序 AppID |
| 公众号 H5（待实现） | `connect/oauth2/authorize` | `sns/oauth2/access_token` | **公众号** AppID |
| 开放平台扫码（待实现） | `connect/qrconnect` | `sns/oauth2/access_token` | **网站应用** AppID |

> 三类 AppID 互不相同，需新增配置，不能复用 `WECHAT_APPID`（小程序）。

## 实现计划

### 后端

1. `config.py` 新增：
   - `wechat_web_appid` / `wechat_web_secret`（公众号或开放平台网站应用的凭据）
   - `wechat_web_redirect_uri`（授权回调地址，须在微信后台配置白名单；域名需已备案 https）
   - `wechat_web_scope`（`snsapi_base` 静默 / `snsapi_userinfo` 拿资料 / `snsapi_login` 扫码）
   - `wechat_web_oauth2_token_url = "https://api.weixin.qq.com/sns/oauth2/access_token"`
2. `security.py` 新增 `wx_web_code2session(code)`：POST oauth2/access_token 换 `{openid, unionid, nickname?}`。
3. `api.py` 新增 `POST /auth/wx-web-login`：`{code, state?}` →
   - 校验 state（防 CSRF，前端生成随机 state，回跳时带回）
   - 调 `wx_web_code2session` 换 openid
   - 复用 `security.wx_login_user(openid, nickname)` 建档/登录，返回 JWT
   - 未配置凭据时返回 503（与 `/auth/wx-login` 风格一致）
4. 测试：`tests/test_auth_phone_wechat.py` 追加 patch 版本用例（不触网）。

### 前端

1. `H5/src/api/auth.js`：
   - `wxWebLoginUrl()`：拼接授权跳转链接（`authorize?appid&redirect_uri&scope&state`，redirect_uri 指向 H5 当前页）
   - `wxWebLogin({ code })`：POST `/auth/wx-web-login` 换 token（复用 `setSession`）
   - 页面加载时检测 URL 是否带 `code` 参数 → 自动换取登录
2. `H5/src/pages/Profile.jsx` 登录方式弹层：
   - 「微信登录」按钮改为：微信内 → 跳转公众号授权链接；PC → 弹扫码二维码（`qrconnect` iframe）或整页跳转
   - 保留手机号登录入口
3. `Settings.jsx`「绑定微信」：同样改走网页授权换 openid 后调 `/auth/wx-bind`。

### 开发期联调

- 微信只认已备案公网 https 域名；`localhost` 无法授权回调。
- 用内网穿透（natapp / ngrok / 花生壳）把本地 8080 暴露成临时域名，并把该域名配到微信后台授权回调白名单。

## 相关文件

- `security.py`：`wx_code2session()`（小程序通道，L40）、`wx_login_user()`（自动建档，可直接复用）
- `api.py`：`/auth/wx-login`（小程序通道）、`/auth/wx-bind`（绑定）、`/auth/phone-code`、`/auth/phone-login`
- `config.py`：微信小程序配置段（L92 起）
- `H5/src/api/auth.js`：`wxLogin()` / `wxBind()`（均依赖微信内置浏览器 `window.wx.login`）
- `H5/src/pages/Profile.jsx`：登录方式选择弹层（微信 / 手机号）
- `H5/src/pages/Settings.jsx`：「绑定微信」入口