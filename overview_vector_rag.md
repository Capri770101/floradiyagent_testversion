# 知识库检索升级为向量 RAG（2026-08-13）

## 做了什么
把 `knowledge/store.py` 的 `query_knowledge(domain, query)` 由「纯关键词匹配」升级为 **TF-IDF 向量空间 + 字符 n-gram 切词 + 余弦相似度** 的混合检索（RAG 思路）。对外签名、返回结构完全不变（仅新增 `_score` 字段），上层 `tools.py` 与 `retrieve_knowledge` 工具零改动。

## 核心设计
- **混合策略**：关键词命中保底 ∪ 向量语义召回。
  - 短单 token（如「母亲节」「康乃馨」「妈妈」）→ 精确关键词，零退化（内部 `pairing` 查找、各单字测试不破）。
  - 多 token / 长自然语句（`retrieve_knowledge` 工具传来的中文 NL）→ 触发向量语义召回并按相关度排序。
  - 触发判定：`len(tokens) >= 2 or len(query) >= 6`。
- **零依赖可离线**：纯 Python（仅 `math/re/json`），不引入 numpy/sklearn，契合项目「dev 零成本」原则。
- **可回滚 / 调参**：`config.py` 新增 `rag_enabled / rag_top_k / rag_keyword_boost / rag_min_score`；`rag_enabled=False` 一键回退旧关键词。
- **升级路径**：当前为轻量向量空间模型（VSM）；花材量增大后把 `_VectorSpace` 换成句向量模型（sentence-transformers / OpenAI embeddings），接口不变即平滑升级到稠密向量 RAG。

## 改动文件
- `knowledge/store.py`：重写检索逻辑（新增 `_VectorSpace`、`_tokenize`、`_retrieve_domain`、`_allow_vector`）。
- `config.py`：新增 4 个 `rag_*` 配置项。
- `tests/test_knowledge_vector.py`：新增 6 例（向量相似度正确性、NL 语义召回、超集关系、关闭回退、返回结构兼容）。
- `tests/test_knowledge.py`：`test_no_match` 查询改为「量子计算机」（真实无重叠仍应空）。
- `README.md`：知识库段落补向量检索说明；测试数 53 → 59。
- `.workbuddy/memory/MEMORY.md` + `2026-08-13.md`：记录本次改造。

## 验证结果
- `pytest`：**59 passed**（原 53 + 新增 6）。
- `ruff check .`：All checks passed。
- 肉眼验证：
  - NL「看望生病住院的朋友带什么花合适」→ 顶部召回 `P_RECIP_FRIEND` / `P_OCC_GETWELL`（朋友/探病相关）。
  - 单 token「母亲节」→ 仅 `P_OCC_MOTHER`（score 1.0，无向量噪声）。
  - 设计管线零退化：母亲节仍出 `康乃馨+玫瑰` + `S_KOREAN_LUXE`。
  - 「量子计算机」→ 0 条（不误召回无关项）。

## 下一步可选
- 把 `knowledge/*.json` 换成真实业务数据（按 `knowledge/TEMPLATE.md`）。
- 花材量大时把 `_VectorSpace` 升级为稠密句向量 RAG（接口不变）。
