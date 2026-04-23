# AdaCascade · 开发进度清单

## 开发环境说明

| 项目 | 开发机 | 部署目标 |
|---|---|---|
| GPU | **RTX 4090 (24 GB)** | A100 (40 GB) |
| conda 环境 | `adacascade`（Python 3.11） | 同左 |
| vLLM | 4090 显存紧张，开发阶段用云端 API（DeepSeek / Qwen），M4 前切回本地 | 本地 vLLM |
| SBERT 设备 | `cuda:0`（4090） | `cuda:0`（A100） |

> **激活环境**：`conda activate adacascade`
> **数据集路径**：`/root/AdaC/datasets → /root/autodl-tmp/Adac-dataset`（软链接）
> **Fixture 路径**：`/root/AdaC/tests/fixtures/`（已生成，不入 git）

---

## 已完成项（M1 前置）

- [x] conda 环境 `adacascade`（Python 3.11）创建完毕
- [x] `pandas` / `pyarrow` 安装至 adacascade 环境
- [x] datasets 软链接建立：`/root/AdaC/datasets → /root/autodl-tmp/Adac-dataset`
- [x] `dl/webtable-noise.zip` 解压至 `datasets/dl/`
- [x] 数据集完整性验证
  - 表文件存在性：JOIN 1534 张 / UNION 5487 张，query + gt 引用的所有表均存在 ✓
  - 列名验证：UNION 是表级匹配（无列字段）✓；JOIN 中 26/28 列名差异为 webtable-noise 设计噪音（`POS` → `POS_val`、`col_SPG` 等），2 个真正缺失，数据集可用 ✓
- [x] `scripts/prepare_fixtures.py` 完成并全量运行（零错误）
  - `tests/fixtures/toy_lake/`：10 张精选表，5 个 gt pairs（Wikidata×3 场景 + WebTable×2 对）
  - `tests/fixtures/retrieval_bench/join/`：1534 张 Parquet，230 queries，1226 gt pairs
  - `tests/fixtures/retrieval_bench/union/`：5487 张 Parquet，823 queries，6512 gt pairs
  - `tests/fixtures/matcher_bench/wikidata/`：4 场景（joinable/semjoinable/unionable/viewunion），各含 source.parquet + target.parquet + ground_truth.json
  - `tests/fixtures/matcher_bench/mimic_omop/`：26 MIMIC 表 + 38 OMOP 表（schema-only JSON，SMD 场景），268 列映射标注
- [x] `.gitignore` 配置（datasets 软链接、大型 fixture、data/ 均排除）
- [x] 远程仓库推送：`git@github.com:925180034/AdaC.git`

---

## M1 · 骨架（目标：2 周）

> 目标：`POST /tables` → Profiling → 状态变 READY，四个 Agent 用 mock 数据

### 环境与基础设施
- [x] 创建 `requirements.txt`（参考系统设计 §8.2 版本约束）
- [x] 安装项目依赖至 adacascade 环境（`pip install -r requirements.txt`）
- [x] 创建 `.env.example`，拷贝为 `.env` 并按 4090 配置（`SBERT_DEVICE=cuda:0`，`LLM_BASE_URL` 指向云端）
- [x] 创建 `configs/default.yaml`（算法规格 §5 全部超参，勿硬编码）
- [x] `python scripts/init_db.py` — 建 SQLite 元数据表（`data/metadata.db` 已创建）
- [x] 启动 Qdrant 二进制 v1.17.1（此环境 Docker iptables 受限，改用二进制），`python scripts/init_qdrant.py` — 建 collection + payload 索引
- [x] 验证 Qdrant 连通：`curl --noproxy '*' http://localhost:6333/healthz`

### 包骨架
- [x] 创建 `adacascade/` 包结构（按 CLAUDE.md §7 目录）
- [x] `adacascade/config.py`：pydantic-settings 读 `.env` 与 `configs/default.yaml`
- [x] `adacascade/state.py`：`IntegrationState` TypedDict 完整定义
- [x] `adacascade/llm_client.py`：OpenAI 兼容客户端封装
- [x] `adacascade/llm_schemas.py`：`PlannerDecision` / `L3BatchResult` / `MatchResult` Pydantic schema
- [x] `adacascade/artifacts.py`：大对象读写工具（`save_pkl` / `load_pkl`）

### 数据库层
- [x] `adacascade/db/models.py`：SQLAlchemy 模型（`table_registry` / `column_metadata` / `integration_task` / `agent_step` / `discovery_result` / `column_mapping`）
- [x] `scripts/init_db.py`：建表脚本（对应 system_design §6.2 全部 DDL）

### 入库链路
- [x] `adacascade/ingest/pipeline.py`：PENDING → INGESTED（格式校验、转 Parquet、schema_hash 计算）
- [x] `adacascade/ingest/reconcile.py`：`reconcile_orphan_ingests()`
- [x] `adacascade/indexing/qdrant_client.py`：封装 upsert / search / delete（含 payload 过滤）
- [x] `adacascade/agents/profiling.py`：完整 ProfilingAgent（text_blob + TF-IDF transform + SBERT GPU 编码 + Qdrant upsert）

### API 骨架
- [x] `adacascade/api/app.py`：FastAPI lifespan（Qdrant 连接 + LangGraph 编译 + reconciliation）
- [x] `adacascade/api/routes/tables.py`：`POST /tables`（202）、`GET /tables/{id}`、`GET /tables`、`DELETE /tables/{id}`
- [x] `adacascade/graph/build.py`：LangGraph 图定义（四 Agent，Retrieval / Matcher 暂用 mock 桩）
- [x] `scripts/start_api.sh`：单 worker 启动脚本

### M1 验收
- [x] `pytest tests/integration/test_m1_ingest.py` 全通过（7/7）
- [x] 手工调 `POST /tables` 上传 CSV，`GET /tables/{id}` 返回 `status=READY`（GPU SBERT，<3s）
- [x] `mypy --strict adacascade/` 无错误（24 源文件）
- [x] `ruff check adacascade/` 无警告

---

## M2 · 算法实现（目标：3 周）

> 目标：TLCF 三层 + Matcher 所有公式 + LLM JSON Schema，复现论文指标

### Week 1：RetrievalAgent / TLCF
- [ ] `adacascade/agents/retrieval/layer1.py`：`compute_s1()`、`type_jaccard()`、`build_c1()`（小顶堆，算法规格 §3.2）
- [ ] `adacascade/agents/retrieval/layer2.py`：Qdrant search + C₂ 交集约束 + 回退策略（算法规格 §3.3）
- [ ] `adacascade/agents/retrieval/layer3.py`：LLM 批处理验证（batch_size=10，asyncio.gather 并行，算法规格 §3.4）
- [ ] `adacascade/agents/retrieval/aggregate.py`：min-max 归一化（C₃ 内）+ S_final 加权聚合（算法规格 §3.5）
- [ ] 单元测试：`test_type_jaccard` / `test_minmax_edge` / `test_c2_intersection` / `test_l3_batch`
- [ ] 集成测试：`test_tlcf_toy`（toy_lake 10 表，已知 JOIN 对全进 C₃）

### Week 2：MatcherAgent
- [ ] `adacascade/agents/matcher/text_sim.py`：`sim_lev()` / `sim_seq()` / `sim_jac_name()` / `sim_name()`（算法规格 §4.2.1）
- [ ] `adacascade/agents/matcher/struct_sim.py`：`sim_type()` + 兼容图（算法规格 §4.2.2）
- [ ] `adacascade/agents/matcher/stat_sim.py`：`sim_num()` / `sim_cat()` / `sim_dist()`（算法规格 §4.2.3）
- [ ] `adacascade/agents/matcher/mixed.py`：`mixed_score()` + 场景权重切换 SMD/SSD/SLD（算法规格 §4.2）
- [ ] `adacascade/agents/matcher/candidates.py`：`filter_cpi()` + `truncate_per_source(top_n=10)`（算法规格 §4.3/§4.4）
- [ ] `adacascade/agents/matcher/decision.py`：布尔判定 + 1:1 匈牙利（JOIN 场景，算法规格 §4.8）
- [ ] 单元测试：`test_name_sim` / `test_type_compat` / `test_scenario_weights` / `test_num_stat` / `test_cat_stat`

### Week 3：LLM 提示词 + 端到端
- [ ] `adacascade/agents/matcher/llm_verify.py`：五段式提示词（Block 1~5），场景差异化注入（算法规格 §4.6）
- [ ] 单元测试：`test_llm_json_schema`（mock 非法响应，验证 Pydantic 报错而非静默通过）
- [ ] 集成测试：`test_matcher_toy_smd` / `test_end2end_toy`
- [ ] 补齐 `adacascade/api/routes/`：`/integrate` / `/discover` / `/match` / `/tasks/{task_id}`
- [ ] 论文复现测试：`test_retrieval_bench_join`（R@10 ≥ 63.9%±3%）/ `test_matcher_bench_sld`（F1 ≥ 92.52%±3%）

### M2 验收
- [ ] `pytest tests/unit/` 全通过
- [ ] `pytest tests/integration/` 全通过
- [ ] `mypy --strict adacascade/` 无错误
- [ ] `ruff check adacascade/` 无警告

---

## M3 · 集成（目标：2 週）

- [ ] API Key 认证中间件（`Authorization: Bearer`）
- [ ] `X-Tenant-Id` 多租户隔离（Qdrant payload filter + DB 记录）
- [ ] structlog JSON 日志，强制含 `task_id`，按天切分
- [ ] Prometheus 指标：`/metrics`（`adac_task_latency_seconds` / `adac_llm_tokens_total` / `adac_tlcf_pruning_rate`）
- [ ] 降级逻辑：Qdrant 不可达 → 503；LLM 超时回退；L3 全失败 → `degraded=true`
- [ ] SBERT GPU OOM → 自动 fallback CPU
- [ ] 对接课题组大系统 UAT

### M3 验收
- [ ] 所有测试仍通过
- [ ] `/healthz` 与 `/metrics` 正常响应
- [ ] UAT 场景覆盖三种模式（integrate / discover / match）

---

## M4 · 上线（目标：1 週）

- [ ] `Dockerfile` 与 `docker-compose.yml`（qdrant + vllm + adacascade 三服务）
- [ ] `.env.example` 补全所有变量
- [ ] `scripts/gc.py`：定期清理 ARCHIVED 记录与 Parquet 文件
- [ ] `scripts/bulk_ingest.py`：批量导入（冷启动时批量入湖 fixture 数据）
- [ ] `scripts/rebuild_tfidf.py`：TF-IDF 全量重训（累积表数增长 ≥ 50% 触发）
- [ ] 运维文档（启动顺序、常见故障处理）
- [ ] 切换 `LLM_BASE_URL` 到本地 vLLM，在 A100 全链路压测

### M4 验收
- [ ] `docker-compose up` 一键启动三服务
- [ ] `/integrate` P95 延迟 ≤ 2.8 s（OpenData JOIN，k=10）
- [ ] Profiling 吞吐 ≥ 1000 张/分钟（A100 + GPU SBERT）

---

## 当前状态

**阶段**：✅ M1 完成 → M2 待开始
**最后更新**：2026-04-23

### M1 完成摘要
- 所有骨架代码实现完毕（24 个 Python 源文件）
- E2E 链路：`POST /tables` → 后台 Profiling（GPU SBERT cuda:0）→ Qdrant upsert → `READY`
- `mypy --strict` 0 错误，`ruff check` 0 警告，7/7 集成测试通过
- 已解决环境问题：PyTorch cu130→cu124（CUDA 12.6 兼容），Qdrant 二进制替代 Docker

### 环境备注
- GPU：RTX 4090，驱动 560.35.03，CUDA 12.6，PyTorch 2.6.0+cu124
- Qdrant：二进制 v1.17.1，持久化到 `data/qdrant/`
- 代理：`http_proxy=127.0.0.1:7890`，访问 localhost 需加 `--noproxy '*'`
