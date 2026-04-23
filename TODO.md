# AdaCascade · 开发进度清单

## 开发环境说明

| 项目 | 开发机 | 部署目标 |
|---|---|---|
| GPU | **RTX 4090 (24 GB)** | A100 (40 GB) |
| conda 环境 | `adacascade`（Python 3.11） | 同左 |
| vLLM | 4090 可跑 qwen3.5:9b AWQ，但显存紧张，开发阶段可用云端 API 替代 | 本地 vLLM |
| SBERT 设备 | `cuda:0`（4090） | `cuda:0`（A100） |

> **激活环境**：`conda activate adacascade`
> **注意**：4090 显存 24 GB，vLLM + SBERT 同时跑可能 OOM。开发阶段建议把 `LLM_BASE_URL` 指向云端 API（DeepSeek / Qwen 线上），只在 M4 上线前切回本地 vLLM。

---

## 前置完成项

- [x] conda 环境 `adacascade`（Python 3.11）已创建
- [x] datasets 软链接：`/root/AdaC/datasets → /root/autodl-tmp/Adac-dataset`
- [x] `dl/webtable-noise.zip` 已解压
- [x] 数据集完整性验证（表文件 + 列名交叉核查）
- [x] `scripts/prepare_fixtures.py` 完成，零错误运行
  - toy_lake：10 张精选表，5 个 gt pairs
  - retrieval_bench：join 1534 张 + union 5487 张，全部转 Parquet
  - matcher_bench：Wikidata 4 场景 + MIMIC-OMOP（SMD schema-only）

---

## M1 · 骨架（目标：2 周）

> 目标：`POST /tables` → Profiling → 状态变 READY，四个 Agent 用 mock 数据

### 环境与基础设施
- [ ] 安装项目依赖（`pip install -r requirements.txt`）
- [ ] 拷贝 `.env.example` → `.env`，按 4090 环境配置变量
- [ ] `python scripts/init_db.py` — 建 SQLite 元数据表
- [ ] 启动 Qdrant docker，`python scripts/init_qdrant.py` — 建 collection + payload 索引
- [ ] 验证 Qdrant 连通：`curl http://localhost:6333/healthz`

### 包骨架
- [ ] 创建 `adacascade/` 包结构（按 CLAUDE.md §7 目录）
- [ ] `config.py`：pydantic-settings 读 `.env` 与 `configs/default.yaml`
- [ ] `state.py`：`IntegrationState` TypedDict 完整定义
- [ ] `llm_client.py`：OpenAI 兼容客户端封装
- [ ] `llm_schemas.py`：`PlannerDecision` / `L3BatchResult` / `MatchResult` Pydantic schema
- [ ] `artifacts.py`：大对象读写工具（save_pkl / load_pkl）

### 数据库层
- [ ] `db/models.py`：SQLAlchemy 模型（table_registry / column_metadata / integration_task / agent_step / discovery_result / column_mapping）
- [ ] `db/migrations/`：Alembic 初始化

### 入库链路
- [ ] `ingest/pipeline.py`：PENDING → INGESTED（格式校验、转 Parquet、schema_hash）
- [ ] `ingest/reconcile.py`：`reconcile_orphan_ingests()`
- [ ] `agents/profiling.py`：完整 ProfilingAgent（TF-IDF + SBERT + Qdrant upsert）
- [ ] `indexing/qdrant_client.py`：封装 upsert / search / delete

### API 骨架
- [ ] `api/app.py`：FastAPI lifespan（Qdrant 连接 + LangGraph 编译 + reconciliation）
- [ ] `api/routes/tables.py`：`POST /tables`（202）、`GET /tables/{id}`、`GET /tables`、`DELETE /tables/{id}`
- [ ] `graph/build.py`：LangGraph 图定义（四 Agent，Retrieval / Matcher 暂用 mock）

### M1 验收
- [ ] `pytest tests/integration/test_m1_ingest.py` 全通过
- [ ] 手工调 `POST /tables` 上传一张 CSV，`GET /tables/{id}` 返回 `status=READY`
- [ ] `mypy --strict adacascade/` 无错误

---

## M2 · 算法实现（目标：3 周）

> 目标：TLCF 三层 + Matcher 所有公式 + LLM JSON Schema，复现论文指标

### Week 1：RetrievalAgent / TLCF

- [ ] `retrieval/layer1.py`：`compute_s1()`、`type_jaccard()`、`build_c1()`（小顶堆）
- [ ] `retrieval/layer2.py`：Qdrant search + C₂ 交集约束 + 回退策略
- [ ] `retrieval/layer3.py`：LLM 批处理验证（batch_size=10，asyncio.gather 并行）
- [ ] `retrieval/aggregate.py`：min-max 归一化 + S_final 加权聚合
- [ ] 单元测试：`test_type_jaccard` / `test_minmax_edge` / `test_c2_intersection` / `test_l3_batch`
- [ ] 集成测试：`test_tlcf_toy`（toy_lake 10 表，已知 JOIN 对全进 C₃）

### Week 2：MatcherAgent

- [ ] `matcher/text_sim.py`：`sim_lev()` / `sim_seq()` / `sim_jac_name()` / `sim_name()`
- [ ] `matcher/struct_sim.py`：`sim_type()` + 兼容图
- [ ] `matcher/stat_sim.py`：`sim_num()` / `sim_cat()` / `sim_dist()`
- [ ] `matcher/mixed.py`：`mixed_score()` + 场景权重切换（SMD/SSD/SLD）
- [ ] `matcher/candidates.py`：`filter_cpi()` + `truncate_per_source(top_n=10)`
- [ ] `matcher/decision.py`：布尔判定 + 1:1 匈牙利（JOIN 场景）
- [ ] 单元测试：`test_name_sim` / `test_type_compat` / `test_scenario_weights` / `test_num_stat` / `test_cat_stat`

### Week 3：LLM 提示词 + 端到端

- [ ] `matcher/llm_verify.py`：四段式提示词（Block 1~5），场景差异化注入
- [ ] 单元测试：`test_llm_json_schema`（mock 非法响应，验证 Pydantic 报错）
- [ ] 集成测试：`test_matcher_toy_smd` / `test_end2end_toy`
- [ ] 补齐 `api/routes/`：`/integrate` / `/discover` / `/match` / `/tasks/{task_id}`
- [ ] 论文复现测试（可选，建议跑）：`test_opendata_join_r10`（R@10 ≥ 60%）/ `test_valentine_sld_f1`（F1 ≥ 90%）

### M2 验收
- [ ] `pytest tests/unit/` 全通过
- [ ] `pytest tests/integration/` 全通过
- [ ] `mypy --strict adacascade/` 无错误
- [ ] `ruff check adacascade/` 无警告

---

## M3 · 集成（目标：2 周）

- [ ] API Key 认证中间件（`Authorization: Bearer`）
- [ ] `X-Tenant-Id` 多租户隔离（Qdrant payload filter + DB 记录）
- [ ] structlog JSON 日志，强制含 `task_id`，按天切分
- [ ] Prometheus 指标：`/metrics`（`adac_task_latency_seconds` 等）
- [ ] 降级逻辑：Qdrant 不可达 → 503；LLM 超时回退；L3 全失败 → `degraded=true`
- [ ] SBERT GPU OOM → 自动 fallback CPU
- [ ] 对接课题组大系统 UAT

### M3 验收
- [ ] 所有测试仍通过
- [ ] `/healthz` 与 `/metrics` 正常响应
- [ ] UAT 场景覆盖三种模式（integrate / discover / match）

---

## M4 · 上线（目标：1 周）

- [ ] `Dockerfile` 与 `docker-compose.yml`（含 qdrant + vllm + adacascade 三服务）
- [ ] `.env.example` 补全所有变量
- [ ] `scripts/gc.py`：定期清理 ARCHIVED 记录与 Parquet 文件
- [ ] `scripts/bulk_ingest.py`：批量导入脚本
- [ ] `scripts/rebuild_tfidf.py`：TF-IDF 全量重训（累积表数增长 ≥ 50% 时）
- [ ] 运维文档（启动顺序、常见故障处理）
- [ ] 切换 `LLM_BASE_URL` 到本地 vLLM，在 A100 环境全链路压测

### M4 验收
- [ ] `docker-compose up` 一键启动三服务
- [ ] `/integrate` P95 延迟 ≤ 2.8 s（OpenData JOIN，k=10）
- [ ] Profiling 吞吐 ≥ 1000 张/分钟（A100 + GPU SBERT）

---

## 当前状态

**阶段**：M1 进行中
**最后更新**：2026-04-23
