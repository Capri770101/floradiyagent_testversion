# flora_diy_agent —— 成品化交付 Overview

> 目标（木木拍板）：按「鉴权 → 可切换数据源 → Docker 部署」顺序，做成一个**仅替换真实小程序连接数据即可接入**的成品。

## 做了什么

| 模块 | 改动 | 文件 |
|------|------|------|
| 配置集中化 | 新增微信登录、JWT、数据源、支付页路径等全部「真实小程序接入」字段 | `config.py` |
| 微信登录鉴权 | `wx_code2session` 换 openid + PyJWT 签发/校验；`get_current_user` 依赖（dev 模式兼容 / 上线强制 Bearer） | 新 `security.py` |
| 接口层 | `POST /auth/wx-login`；`/chat` 解析 `openid or user_id`；`/health` 暴露 `auth`/`data_source`；启动缺配置告警 | `api.py` |
| 数据源可切换 | `RemoteRepository`（httpx 调真实后端）+ `build_repository()` 工厂；`repo` 单例改为工厂产出；`DATA_SOURCE=remote` 缺 base 自动回退 Mock | `storage/repository.py`、`skills/skill_order.py` |
| 部署闭环 | `Dockerfile` + `docker-compose.yml`（env_file + data 卷）+ `.dockerignore` | 根目录 |
| 集成文档 | 重写 `.env.example`（「真实小程序接入配置」分组）+ 新 `INTEGRATION.md`（三步接入、小程序流程、远端接口契约、部署速查） | 根目录 |
| 依赖 & 测试 | `requirements.txt` 加 `PyJWT`；新增 `tests/test_auth.py`(5) + `tests/test_repository_remote.py`(4) | — |

## 验证结果
- **pytest 32 passed**（原 23 + 新 9）
- **ruff check** 全通过
- 实启冒烟：`/health` 显 `auth:dev/data_source:mock`；`/auth/wx-login` 未配微信→503；`/chat` dev 模式 200

## 接真实小程序只要三步（详见 INTEGRATION.md）
1. `.env` 填 `WECHAT_APPID` / `WECHAT_SECRET`
2. 填 `JWT_SECRET` 并设 `AUTH_REQUIRED=true`
3. 设 `DATA_SOURCE=remote` + `REMOTE_API_BASE`（后端按契约返回与 Mock 同形状的 Plan/Shop JSON）

业务代码零改动即对接真实小程序。

---

# 第二轮：定位纠正 + 知识库 / DIY 设计能力（木木指出核心应是「设计」而非「导购」）

## 关键纠正
- 木木明确：本智能体**不是花卉购买导购，而是花卉 DIY 设计智能体**——核心是「根据用户表达设计出符合需求的花卉方案」。原 `generate_diy_plan` 只是占位空壳（price=0、无设计推理），已重写。

## 落地内容
| 模块 | 改动 | 文件 |
|------|------|------|
| 知识库 | `knowledge/`：flowers/styles/pairings/budget/packaging 五份 JSON + `store.py`(轻量检索) + `__init__.py` | 新目录 |
| 检索工具 | `retrieve_knowledge(domain, query)` 注册进 TOOL_REGISTRY | `tools.py` |
| 设计函数 | `design_diy_plan`：抽维度→查知识→组装结构化方案(主花/配材/配比/色彩/包装/寓意/预算)+生图 prompt；主花优先级 对象>风格>场合 | `tools.py` |
| 生图可控 | `_latest_diy_plan` 存最近方案；`generate_effect_image("latest_diy")` 基于方案 `effect_prompt` 生图 | `tools.py` |

## 验证
- pytest **42 passed**（原 32 + 知识库 5 + DIY 设计 5）；`ruff check` 全绿
- smoke：妈妈→康乃馨+玫瑰、恋人→玫瑰+郁金香(粉紫)、探病→百合(纯洁祝福)，生图 prompt 均基于方案

## 下一步（待木木补数据）
- 把 `knowledge/*.json` 通用骨架替换为真实业务数据（花材/价格/风格标准/设计经验规则）；花材量大时可把 `store.py` 轻量检索升级为向量 RAG（接口不变）。

---

# 第三轮：设计函数打磨（场景感知 + 细分风格 + 反馈迭代）+ 知识库模板

## 木木决策
- 选 2（打磨设计函数：反馈迭代 + 风格细分 + 节日场景模板）+ 3（知识库内容清单模板）一起做。
- 目标：让 DIY 设计「懂场合、能细分、可迭代」，并给用户一份可照填真实数据的模板。

## 落地内容
| 模块 | 改动 | 文件 |
|------|------|------|
| 风格细分 | `styles.json` 每个风格扩 2 个 substyle（韩式甜美/高级、北欧极简/田园、复古油画/港风、自然野趣/森系、ins明亮/奶油、日式极简/物哀） | `knowledge/styles.json` |
| 场景模板 | 新增 `scenes.json` 14 个场景/节日（情人节/母亲节/生日/纪念日/表白/探病/道歉/乔迁/毕业/圣诞/新年/婚礼/教师节/悦己），含推荐风格/色板/主花倾向/寓意/预算锚点 | 新 `knowledge/scenes.json` |
| 检索扩展 | `store.py` 加载 `scene` 域 | `knowledge/store.py` |
| 场景感知 | `design_diy_plan` 识别节日/场景关键词 → 注入整组偏好（风格/色系/主花/寓意/预算） | `tools.py` |
| 风格细分 | 设计函数先定大类再选 substyle（「高级」→韩式高级），`get_style_full` 解析父子风格 | `tools.py` |
| 反馈迭代 | 新增 `revise_diy_plan(plan, feedback)`：解析降价/换花/改色等反馈 → 重跑设计管线 → 返回 v2（version+1，parent_id 可追溯）；注册为工具 | `tools.py` |
| 模板文档 | `knowledge/TEMPLATE.md`：逐文件字段说明 + 示例 + 填写规则 + 替换步骤 + 校验清单 | 新文件 |
| 文档同步 | README 标题/定位改 DIY 设计、工具表加 revise、知识库段落增补场景与增强、测试数 32→53 | `README.md` |

## 验证
- pytest **53 passed**（原 32 + 知识库 5 + DIY 设计 5 + 场景检索 5 + DIY 迭代 5）；`ruff check` 全绿
- smoke 设计质量：母亲节→康乃馨+韩式高级、情人节→韩式甜美红粉、生日→ins明亮打卡、探病→森系治愈、圣诞→复古港风红绿
- smoke 反馈迭代：便宜点→v2 入门档且 parent 可追溯；去掉康乃馨→主花变玫瑰+百合且无康乃馨；红色调→红置顶

## 现状小结
- 智能体现在具备：**场景感知设计 + 细分风格 + 结构化方案 + 反馈迭代 + 可控生图 prompt + 可切换知识库**。
- 仍是通用花艺骨架；**接入真实业务只需改 `knowledge/*.json`（见 TEMPLATE.md），无需动代码**。
- 下一步可选项：①填真实业务数据 ②(量大时)把 store.py 轻量检索升级为向量 RAG ③接千问平台（仍先观望）

