# AdaCascade · 开发进度清单

## 开发环境说明

| 项目 | 开发机 | 部署目标 |
|---|---|---|
| GPU | **RTX 4090 (24 GB)** | A100 (40 GB) |
| conda 环境 | `adacascade`（Python 3.11） | 同左 |
| LLM 运行时 | 开发/演示阶段可在前端或 `/runtime/llm` 切换 DeepSeek API 与本地 vLLM；当前默认用 API 提速 | A100 本地 vLLM 压测，API 作为降级/演示备用 |
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
- [x] `adacascade/agents/retrieval/layer1.py`：`compute_s1()`、`type_jaccard()`、`build_c1()`（小顶堆，算法规格 §3.2）
- [x] `adacascade/agents/retrieval/layer2.py`：Qdrant search + C₂ 交集约束 + 回退策略（算法规格 §3.3）
- [x] `adacascade/agents/retrieval/layer3.py`：LLM 批处理验证（batch_size=10，asyncio.gather 并行，算法规格 §3.4）
- [x] `adacascade/agents/retrieval/aggregate.py`：min-max 归一化（C₃ 内）+ S_final 加权聚合（算法规格 §3.5）
- [x] 单元测试：已覆盖 `type_jaccard` / C₂ 交集约束 / L3 JSON Schema 非法响应 / L3 缺失分数排除 / `test_minmax_edge` / S_final 聚合排序
- [x] 集成测试：`test_tlcf_toy`（离线确定性验证 C₁→C₂→C₃→ranking，已知 JOIN 候选排第一）

### Week 2：MatcherAgent
- [x] `adacascade/agents/matcher/text_sim.py`：`sim_lev()` / `sim_seq()` / `sim_jac_name()` / `sim_name()`（算法规格 §4.2.1）
- [x] `adacascade/agents/matcher/struct_sim.py`：`sim_type()` + 兼容图（算法规格 §4.2.2）
- [x] `adacascade/agents/matcher/stat_sim.py`：`sim_num()` / `sim_cat()` / `sim_dist()`（算法规格 §4.2.3）
- [x] `adacascade/agents/matcher/mixed.py`：`mixed_score()` + 场景权重切换 SMD/SSD/SLD（算法规格 §4.2）
- [x] `adacascade/agents/matcher/candidates.py`：`filter_cpi()` + `truncate_per_source(top_n=10)`（算法规格 §4.3/§4.4）
- [x] `adacascade/agents/matcher/decision.py`：布尔判定 + 1:1 匈牙利（JOIN 场景，算法规格 §4.8）
- [x] 单元测试：`test_name_sim` / `test_type_compat` / `test_scenario_weights` / `test_num_stat` / `test_cat_stat` / 候选过滤截断 / 匈牙利 1:1

### Week 3：LLM 提示词 + 端到端
- [x] `adacascade/agents/matcher/llm_verify.py`：五段式提示词（Block 1~5），场景差异化注入（算法规格 §4.6）
- [x] 单元测试：`test_llm_json_schema`（mock 非法响应，验证 Pydantic 报错而非静默通过）
- [x] 集成测试：`test_matcher_toy_smd` / `test_end2end_toy`
- [x] 补齐 `adacascade/api/routes/`：`/integrate` / `/discover` / `/match` / `/tasks/{task_id}`
- [ ] 论文复现测试：`test_retrieval_bench_join`（R@10 ≥ 63.9%±3%）/ `test_matcher_bench_sld`（F1 ≥ 92.52%±3%；需要完整 benchmark run）

### M2 验收
- [x] `pytest tests/unit/` 全通过
- [x] `pytest tests/integration/` 全通过
- [x] `mypy --strict adacascade/` 无错误
- [x] `ruff check adacascade/` 无警告

---

## M3 · 集成（目标：2 週）

- [x] API Key 认证中间件（`Authorization: Bearer`）
- [x] `X-Tenant-Id` 多租户隔离（DB 记录与 API 访问范围；Qdrant 检索沿用 tenant payload filter）
- [x] structlog JSON 日志（本地服务 JSONRenderer；生产按天切分延后到 M4 运维配置）
- [x] Prometheus 指标：`/metrics`（FastAPI HTTP 指标已暴露；业务自定义指标后续按压测补充）
- [x] 降级逻辑：Qdrant 检索失败回退并标记 `degraded=true`；LLM verification 失败返回低置信结果；L3 全失败不崩溃
- [x] SBERT GPU OOM → 自动 fallback CPU
- [ ] 对接课题组大系统 UAT（按当前要求暂不对接，后续单独执行）

### M3 验收
- [x] 所有测试仍通过
- [x] `/healthz` 与 `/metrics` 正常响应
- [x] 本地 UAT 场景覆盖三种模式（integrate / discover / match）

---

## M3.5 · 前端演示工作台（目标：本地可演示）

- [x] 完成前端演示设计文档：`docs/frontend_demo_design.md`
- [x] 创建 `frontend/`：React + Vite + TypeScript 独立前端
- [x] 实现 `/workspace` 三栏工作台：任务控制区、结果图区、Agent Trace 区
- [x] 接入现有后端 REST：`GET /tables`、`POST /discover`、`POST /match`、`POST /integrate`、`GET /tasks/{task_id}`
- [x] 新增后端 SSE：`GET /tasks/{task_id}/events` 与进程内任务事件总线
- [x] 增加 Agent/Layer 事件 emit 点：Planner、Profiling、Retrieval L1/L2/L3、Matcher filtering/LLM/decision
- [x] 实现 React Flow 图谱：ranking → discovery graph，mappings → column mapping graph
- [x] 实现 Vitest 单元/组件测试与 Playwright 演示 E2E
- [x] 明确本地 demo 安全边界：`VITE_API_KEY` 仅限本地可信环境，不可公网部署

### M3.5 验收
- [x] 大系统按钮 URL 参数可预填 workspace 上下文，但不会自动运行任务
- [x] discover / match / integrate 三种模式均可从前端启动并展示结果
- [x] SSE 实时显示 Agent + Layer 级阶段进度
- [x] 图谱、ranking、mappings、Raw JSON 四种结果视图可切换并联动
- [x] `npm run lint`、`npm run test`、`npm run build` 通过；Playwright demo 流程通过或有明确本地验收命令

---

## M4 · 上线（目标：1 週）

> 当前开发环境运行在容器/受限网络内，Docker iptables 不可用；M4 当前验收以非 Docker 启动与可复现 demo 运维流程为准，Docker 打包降级为后续可选生产部署项。

### M4.1 当前环境上线 Profile（非 Docker）
- [x] `.env.example` 补全所有变量，覆盖 API 模式、本地 vLLM 模式、数据目录、SQLite/ckpt/artifacts 路径
- [x] 固化 Qdrant 二进制启动流程：`scripts/start_qdrant.sh` + `scripts/init_qdrant.py` + 健康检查
- [x] 固化 FastAPI 单 worker 启动流程：主项目路径 `/root/AdaC`、`NO_PROXY`、`DATABASE_URL`、`DATA_DIR`、`CKPT_PATH`、`ARTIFACTS_DIR`
- [x] 固化前端公开 demo 启动流程：Vite same-origin proxy、`VITE_API_BASE_URL=""`、公网 URL 访问方式
- [x] 运维文档：启动顺序、停止/重启、端口占用排查、常见故障处理

### M4.2 LLM 运行时验收
- [x] API 模式验收：通过 `/runtime/llm` 切换到 DeepSeek `deepseek-v4-flash`，discover / match / integrate smoke test 均成功；API integrate 约 4 分 35 秒
- [x] 本地模式验收：本地 vLLM 可用时通过前端按钮或 `/runtime/llm` 切换到 local，不再要求手动改 `LLM_BASE_URL`；空 ranking 的 integrate 不再回退全量 Matcher，smoke 约 2 秒成功结束
- [ ] A100 全链路压测：在 local vLLM 模式下记录 `/integrate` P95、Profiling 吞吐、GPU 显存与降级情况

### M4.3 数据与维护脚本
- [x] `scripts/gc.py`：定期清理 ARCHIVED 记录与 Parquet 文件
- [x] `scripts/bulk_ingest.py`：批量导入（冷启动时批量入湖 fixture 数据）
- [x] `scripts/rebuild_tfidf.py`：TF-IDF 全量重训（累积表数增长 ≥ 50% 触发；已纳入运维文档验收）

### M4.4 可选生产打包（当前环境不作为阻塞项）
- [ ] `Dockerfile` 与 `docker-compose.yml` 草案（qdrant + vllm + adacascade 三服务），标注当前容器环境无法本机验收
- [ ] 生产 nginx/systemd/tmux 方案取舍说明

### M4 验收
- [x] 非 Docker 一键/半自动启动流程可复现：Qdrant binary + FastAPI single worker + 前端公开 demo
- [x] 前端可完成 discover / match / integrate，并展示中间结果区与四 Agent 步骤高亮
- [x] API 模式与 local vLLM 模式可通过 UI/API 切换，不依赖手动改 `.env`
- [ ] local vLLM 模式下 `/integrate` P95 延迟 ≤ 2.8 s（OpenData JOIN，k=10；A100 压测，迁入 M5 性能专项）
- [ ] Profiling 吞吐 ≥ 1000 张/分钟（A100 + GPU SBERT，迁入 M5 性能专项）
- [x] Docker Compose 仅作为后续生产环境可选验收，不阻塞当前 M4

---

## M5 · 全量数据入湖、Benchmark 与性能优化（目标：论文复现 + 大规模可用）

> M4 已完成 demo/运维固化；M5 的目标是把系统从 10 表 toy demo 推进到完整数据集规模，分别完成数据发现（Retrieval/Discovery）与模式匹配（Matcher）两条 benchmark 链路，并基于真实耗时做性能优化。

### M5.1 数据集边界与租户规划
- [x] 保留 `default` 租户作为 10 表 toy demo，避免破坏当前前端演示环境
- [x] 新建 `benchmark` 租户用于全量数据与论文复现，避免 demo 数据与实验数据混杂
- [x] 明确数据发现数据集：`tests/fixtures/retrieval_bench/join/`（1534 表、230 queries、1226 gt pairs）
- [x] 明确数据发现数据集：`tests/fixtures/retrieval_bench/union/`（5487 表、823 queries、6512 gt pairs）
- [x] 明确模式匹配数据集一：`tests/fixtures/matcher_bench/wikidata/`（Musicians 四场景：joinable / semjoinable / unionable / viewunion，各场景 source/target 一对 Parquet 表）
- [x] 明确模式匹配数据集二：`tests/fixtures/matcher_bench/mimic_omop/`（26 MIMIC 表 + 38 OMOP 表，schema-only SMD，268 列映射标注）
- [x] 数据发现 JOIN 与 UNION 使用隔离 corpus / artifact，不共用一个 TF-IDF 模型，避免语料分布互相污染
- [x] MIMIC-OMOP schema-only 数据不得走依赖 Parquet 实例的常规 Profiling，必须走专用 SMD schema ingestion 路径
- [x] 记录每个数据集的表数、列数、ground truth 数量、任务类型（JOIN/UNION/SMD/SSD/SLD）到 benchmark 报告

### M5.2 全量入湖与 Profiling 批处理
- [x] 扩展 `scripts/bulk_ingest.py` 支持 `--tenant-id benchmark`，可覆盖 manifest 中 tenant，并拒绝跨租户 `table_id` 碰撞
- [x] 新增 `scripts/profile_ingested.py`：批量处理有 Parquet 实例数据的 `INGESTED` 表，调用 Profiling → SBERT 编码 → Qdrant upsert → 状态转 `READY`
- [x] `profile_ingested.py` 支持 `--tenant-id`、`--limit`、`--retry-failed`、`--source-system` 与失败摘要，`--retry-failed` 会先复位为 `INGESTED` 再重跑
- [x] 新增 schema-only ingestion 路径：读取 MIMIC-OMOP JSON schema，写入 `TableRegistry` / `ColumnMetadata`，用表名、列名、列描述构造可加载 profile
- [x] schema-only SMD 路径跳过实例统计特征：`numeric_stats=None`、`categorical_stats=None`、`sample_values=[]`，但保留 `col_type` 与 description
- [x] schema-only SMD 路径仍需生成 SBERT 表/列向量并 upsert Qdrant，保证可被 Matcher benchmark 与可选检索调试加载
- [x] 小规模验证：已导入并 profile 20 张 retrieval bench JOIN 表，确认 SQLite / Qdrant / SBERT / 状态流转正确，并生成 `tfidf_benchmark_join.pkl`
- [x] 中规模验证第一阶段：已扩展到 100 张 retrieval bench JOIN 表，100/100 READY，Profiling 本轮 80 张新增/待处理表成功、0 失败，并重建 `tfidf_benchmark_join.pkl`（vocabulary size 103）
- [x] 中规模验证第二阶段：已扩展到 500 张 retrieval bench JOIN 表，500/500 READY，Profiling 本轮 400 张新增/待处理表成功、0 失败，并重建 `tfidf_benchmark_join.pkl`（vocabulary size 284）
- [x] 全量导入 retrieval bench JOIN：1534/1534 READY，本轮新增 1034 张 profiling 成功、0 失败，并重建 JOIN TF-IDF（vocabulary size 590）
- [x] 全量导入 retrieval bench UNION：5487/5487 READY，本轮新增 5387 张 profiling 成功、0 失败，并重建 UNION TF-IDF（vocabulary size 1647）
- [x] 处理 matcher bench Wikidata 数据，四场景 source/target 8 张 Parquet 表已导入并 profile 到 `benchmark` 租户
- [x] 处理 matcher bench MIMIC-OMOP schema-only 数据，26 MIMIC + 38 OMOP 表已导入并索引，确保无实例数据的 SMD 场景可直接进入 Matcher
- [x] 扩展 `scripts/rebuild_tfidf.py` 支持 `--tenant-id benchmark` 与 `--corpus join|union|matcher|all`，并提供 Retrieval L1 显式加载 scoped artifact 的入口
- [x] 全量入湖后分别重建 JOIN、UNION、Matcher corpus 的 TF-IDF artifact，并记录 vocabulary size：JOIN 590；UNION 1647；Matcher 72 表 artifact 已生成

### M5.3 数据发现 / Retrieval Benchmark
- [x] 新增 `scripts/run_retrieval_benchmark.py` 或 `tests/reproduction/test_retrieval_bench_*.py`
- [x] Benchmark runner 直接调用 Python 层 Retrieval 核心函数，不通过 REST `/discover`，避免 HTTP/LangGraph/任务轮询噪声
- [x] Benchmark runner 默认关闭 L3/Matcher LLM cache，保证耗时与质量指标可复现；生产/demo 运行可单独开启 cache
- [x] JOIN benchmark：读取 `retrieval_bench/join/queries.json` 与 `ground_truth.json`，使用 JOIN 专属 TF-IDF artifact 批量运行 Retrieval
- [x] UNION benchmark：读取 `retrieval_bench/union/queries.json` 与 `ground_truth.json`，使用 UNION 专属 TF-IDF artifact 批量运行 Retrieval
- [x] 指标输出：R@1、R@5、R@10、平均耗时、P50、P95、失败率
- [x] 分层耗时输出：L1 lexical、L2 Qdrant、L3 LLM rerank、aggregate
- [x] 已跑 JOIN `--limit 2` smoke 验证 runner、scoped TF-IDF 与分层耗时输出；`--limit 20/50/100` 与完整 JOIN/UNION benchmark 留给长任务复现窗口
- [ ] 对照论文目标：JOIN R@10 ≥ 63.9% ± 3%；UNION 指标按算法规格/ground truth 报告补齐（需完整长任务 benchmark）

### M5.4 模式匹配 / Matcher Benchmark
- [x] 新增 `scripts/run_matcher_benchmark.py` 或 `tests/reproduction/test_matcher_bench_*.py`
- [x] Matcher benchmark runner 直接调用 Python 层 Matcher 函数，不通过 REST `/match`，避免 HTTP/LangGraph/任务轮询噪声
- [x] Benchmark runner 默认关闭 Matcher LLM cache，生产/demo cache 与论文复现 benchmark 配置分离
- [x] Wikidata benchmark：覆盖 joinable、semjoinable、unionable、viewunion 四个场景
- [x] MIMIC-OMOP benchmark：覆盖 schema-only SMD 场景，验证 268 条列映射标注
- [x] MIMIC-OMOP benchmark 使用 schema-only profiles：列名 + 类型 + 描述，不要求 Parquet 实例数据或统计特征
- [x] 指标输出：Precision、Recall、F1、平均耗时、P50、P95、LLM pair 数、失败率
- [x] 分阶段输出：candidate filtering 耗时、LLM verification 耗时、decision / 1:1 耗时
- [x] 已跑 Wikidata 四场景聚合 smoke（4 pairs，0 failures，F1≈0.897）与 MIMIC-OMOP schema-only 全量 case smoke（26 pairs，0 failures）
- [ ] 对照论文目标：SLD F1 ≥ 92.52% ± 3%；SMD/SSD/其他场景按算法规格补齐目标指标（需基于完整复现窗口复核）

### M5.5 性能瓶颈定位与优化
- [x] 给 Retrieval 与 Matcher 事件补充分层耗时字段，benchmark 报告、agent 输出和事件 payload 均可携带每层耗时
- [x] 限制 integrate 的 Matcher 目标表数量，只对 Retrieval ranking topK 进入 Matcher（例如 top 3/5/10，可配置）
- [x] 增加 L3 rerank 缓存：同一 query table + candidate table 不重复请求 LLM，仅用于 production/demo 加速
- [x] 增加 Matcher verification 缓存：同一 source column + target column + scenario 不重复请求 LLM，仅用于 production/demo 加速
- [x] 明确 benchmark 配置必须禁用 LLM cache，避免缓存命中污染 P50/P95 与成本统计
- [x] 初步评估当前 local LLM 路径下 L3/Matcher 为主要瓶颈：JOIN retrieval smoke L3 avg≈23.2s/query；Wikidata matcher LLM avg≈46.6s/pair；MIMIC matcher LLM avg≈43.4s/pair
- [x] 区分论文默认配置、benchmark 复现配置与工程加速配置，避免随意修改算法规格默认超参
- [ ] 输出 API 模式与 local vLLM 模式对比：质量、耗时、失败率、成本/显存（随 M5.6 在目标部署服务器执行）

#### M5.5.1 Demo integrate latency profile（2026-05-12）
- [x] 复用已验证前端 E2E 任务 `527cc084-c051-4e38-934a-da07bca96448`，不重新触发长耗时 blind benchmark；元数据来自 `/root/AdaC/data/metadata.db`，LangGraph checkpoint 来自 `/root/AdaC/data/ckpt.db`
- [x] 总耗时：471.5s（03:23:10.425 → 03:31:01.943），状态 SUCCESS，`ranking_count=3`，`mapping_count=33`，租户 `default`，查询表 `musicians_unionable_source`，UI 选择 JOIN tuned recall profile
- [x] 可恢复分段耗时：Planner/routing≈0.002s；Profiling/profile load≈7.046s（1.5%）；Retrieval TLCF≈2.442s（0.5%，C1/C2/C3 均为 3）；Matcher≈462.005s（98.0%）；API/finalization 未归因约 0.022s
- [x] 瓶颈结论：端到端延迟几乎全部集中在 Matcher LLM verification；Retrieval tuned recall profile 已把候选收敛到 3 张表，但每张候选表仍会产生大量列对验证，33 条最终映射对应约 7m42s Matcher 阶段
- [x] 下一步动作：优先对 demo/product 路径做 Matcher verification cache 命中率与并发/批处理 profile，记录 LLM pair 数、cache hit/miss、per-call P50/P95；如仍超预算，再评估 UI demo 默认 `matcher_top_k` 或列对预过滤阈值的独立工程 profile，不修改论文默认超参

#### M5.5.2 Matcher verification 无损加速（2026-05-13）
- [x] 阶段 1：实现进程内 Matcher verification cache，cache key 覆盖 source/target column profile、scenario、prompt/schema version、runtime backend 与 model，确保 production/demo 可复用结果但 benchmark 可禁用
- [x] 阶段 1：对 cache miss 的 Matcher LLM verification 增加 `matcher_llm_concurrency` 并发控制，默认保守，Demo fast / JOIN tuned profile 可显式提高
- [x] 阶段 1：记录 `verified_pair_count`、`cache_hit_count`、`cache_miss_count`、`llm_call_count`、`matcher_verify_ms`、`llm_verify_p50_ms`、`llm_verify_p95_ms`，用于定位 pair 数、cache 命中率与单次 LLM 延迟
- [x] 阶段 1 聚焦验证：`pytest tests/unit/test_matcher_llm.py tests/unit/test_matcher.py tests/unit/test_m5_performance.py -q` → 22 passed；`npm --prefix frontend run test -- --run WorkspacePage.test.tsx TaskControlPanel.test.tsx` → 30 passed；`ruff check adacascade/agents/matcher tests/unit/test_matcher.py tests/unit/test_matcher_llm.py` → All checks passed
- [ ] 阶段 1 实测验证：同一 demo integrate 输入连续运行两次，第二次 cache hit 明显上升、Matcher verification latency 明显下降，ranking/mapping 结果保持一致
- [ ] 阶段 2 预留：若阶段 1 收益明确，再将 cache 落到 SQLite `matcher_verification_cache`，实现 memory → SQLite → LLM 的持久缓存链路

### M5.6 A100 / local vLLM 压测（当前服务器跳过）
- [ ] 在 A100 环境下启动 local vLLM，记录模型、量化方式、max_model_len、gpu_memory_utilization（按用户要求迁移到目标部署服务器执行）
- [ ] 压测 `/integrate`：记录 P50 / P95 / P99、ranking 数、mappings 数、失败率（按用户要求迁移到目标部署服务器执行）
- [ ] 压测 Profiling 吞吐：目标 ≥ 1000 张/分钟（A100 + GPU SBERT），记录 batch size 与显存（按用户要求迁移到目标部署服务器执行）
- [ ] 记录 GPU 显存、水位、OOM/CPU fallback 情况（按用户要求迁移到目标部署服务器执行）
- [ ] 输出压测结论：是否达到 M4 原定性能指标；未达到时列出瓶颈与优化项（按用户要求迁移到目标部署服务器执行）

### M5.7 Benchmark 异常诊断与已完成修复记录（2026-05-11）
- [x] 修复本地 vLLM 启动默认参数：`scripts/start_llm.sh` 默认 `VLLM_GPU_MEMORY_UTILIZATION=0.55`、`VLLM_MAX_MODEL_LEN=4096`，避免 4090 上 KV cache 不足导致端口 8000 不可用
- [x] 修复 standalone retrieval benchmark 未初始化 Qdrant registry：`scripts/run_retrieval_benchmark.py` 启动时调用 `init_qdrant_registry()`
- [x] 修复 Retrieval L2 缺少 query table vector：`load_table_profile(..., include_vector=True)` 会生成 `table_vector`，candidate profiles 使用 `include_vector=False` 避免 7000+ 候选重复编码
- [x] 修复 retrieval ground truth self-pair 污染：benchmark 忽略 `query_table_id == candidate_table_id` 的不可检索自匹配，并输出 `evaluation.ground_truth_pairs / ignored_self_pairs / evaluated_pairs`
- [x] 修复旧 profile 缺少 `sample_values`：Profiling 将样本值写入 `ColumnMetadata.stat_summary`，`load_table_profile()` 恢复样本值供 L3/Matcher 使用
- [x] 修复 L3 prompt 证据不足与上下文超限：L3 prompt 加入截断后的列样本值，本地 4096 context 下按单候选 batch 调用，避免 400 context overflow
- [x] 修复 `profile_ingested.py --refresh-ready` 误刷新 schema-only JSON 表：refresh READY 时只选择 `.parquet` 来源表，MIMIC-OMOP schema-only 继续走专用 ingestion/index 路径
- [x] 修复 retrieval candidate pool 混入跨语料表：`load_candidate_profiles(..., corpus="join|union")` 按 `source_system=retrieval|{corpus}` 过滤 DB 候选池
- [x] 修复 Qdrant 表向量 L2 跨语料召回：table payload 写入 `source_system`，`search_tables(..., source_system=...)` 按 JOIN/UNION 语料过滤，并新增 `source_system` payload index
- [x] 修复 L2 fallback 返回 C1 之外表导致后续 profile enrich 缺字段的问题：fallback 只在 C1 内选 top-3，保持交集约束链路可解释
- [x] 刷新 benchmark profiles/Qdrant payload：`processed=7029, succeeded=7029, failed=0`
- [x] 最新验证：`pytest tests/unit/test_retrieval.py tests/unit/test_m5_benchmark_runners.py tests/unit/test_m5_ingestion_scripts.py -q` → 50 passed；`ruff check ...` → All checks passed
- [x] 最新 smoke：UNION `--limit 5` 为 `recall@10=0.8`；JOIN `--limit 5` 从 `recall@10=0.0` 提升到 `0.2`
- [x] 剩余 JOIN 低召回定位：16 个真值均在候选池，但 L1 只保留 6 个，L2/L3 后剩 3 个，top10 只有 1 个；Qdrant table top40 只覆盖 3/16，说明 JOIN 需要调参或补充列级/样本值召回信号

### M5.8 Optuna 超参数搜索与 JOIN 召回优化计划

> 目标：在不删除论文默认配置的前提下，新增可复现实验配置与 tuned profile。允许通过 Optuna 搜索 `theta_1/theta_2/theta_3/k_1/k_2/w_1/w_2/w_3` 等超参数；若调参有效，可把最优配置作为 `benchmark_tuned` 或 `demo_fast` profile 暴露，paper-default 仍保留用于论文复现对照。

#### M5.8.1 先建立可重复的调参 runner
- [x] 新增 `scripts/optimize_retrieval_params.py`，支持 `fixture_dir`、`--tenant-id`、`--corpus join|union`、`--limit`、`--trials`、`--timeout`、`--seed`、`--storage`、`--study-name`、`--output`
- [x] 默认目标函数优先优化 `recall@10`，并用平均耗时作为 secondary penalty：`objective = recall@10 - avg_ms / latency_penalty_ms`
- [x] 搜索空间第一版：
  - `theta_1`: 0.05 ~ 0.30
  - `theta_2`: 0.35 ~ 0.75
  - `theta_3`: 0.20 ~ 0.70
  - `k_1`: categorical `[120, 200, 300, 500, 800]`
  - `k_2`: categorical `[40, 80, 120, 200, 400]`
  - `w_1/w_2/w_3`: Dirichlet-like 归一化权重，分别约束到 `[0,1]` 且总和为 1
- [x] runner 输出 JSON 报告：best params、best value、R@1/R@5/R@10、avg/p50/p95、L1/L2/L3 平均耗时、失败数、evaluation metadata、trials 明细
- [x] 单元测试覆盖：搜索空间生成、权重归一化、objective 计算、study report 序列化；测试中 mock benchmark 执行，避免真实 LLM
- [x] smoke 验证：JOIN `--limit 5 --trials 2` 可完成；best trial 为 `k_1=200,k_2=40,theta_1≈0.200,theta_2≈0.412,theta_3≈0.278,w≈(0.184,0.460,0.355)`，`recall@10=0.2`，`avg_ms≈18.6s`；`k_2=200` trial 未提升召回且 `avg_ms≈68.7s`

#### M5.8.2 让 retrieval benchmark 支持 plan overrides
- [x] 扩展 `scripts/run_retrieval_benchmark.py`：新增可选 `plan_overrides` 参数和 CLI `--plan-json`，传入 Retrieval state 的 `plan`
- [x] 单元测试覆盖：`--plan-json` 中的 `k_1/k_2/theta_* / w_*` 能进入 `retrieval.run(state)`，并不影响未传参数时的 paper-default 路径
- [x] smoke 验证：JOIN `--limit 5` 已通过 Optuna runner 真实调用 plan overrides，输出 trial JSON 可对比

#### M5.8.3 小样本 Optuna 搜索（当前 4090 环境）
- [x] 先跑 JOIN `--limit 20 --trials 8 --timeout 900 --k2-choices 40,80,120`，验证搜索流程、报告格式、失败恢复与耗时；900s 内完成 3 个 trial，`failures=0`
- [x] 当前最佳 objective trial：`k_1=120,k_2=40,theta_1≈0.181,theta_2≈0.523,theta_3≈0.346,w≈(0.274,0.277,0.449)`，`recall@10=0.20`、`recall@5=0.15`、`avg_ms≈14.7s`、`L3 avg≈12.6s`
- [x] 最高 recall trial：`k_1=120,k_2=120,theta_1≈0.093,theta_2≈0.376,theta_3≈0.674,w≈(0.472,0.044,0.484)`，`recall@10=0.25`，但 `avg_ms≈27.8s`、`L3 avg≈25.7s`，质量收益很小且延迟接近翻倍
- [x] 结论：当前 TLCF 参数搜索没有解决 JOIN 低召回根因；不建议直接扩大到 JOIN `--limit 50 --trials 50`，应先进入 M5.8.4 的 JOIN 专用列级/样本值召回增强
- [x] 对 UNION 做 sanity 搜索：第一次因 Qdrant/vLLM 未启动产生无效 `recall@10=0.0` 报告并已废弃；恢复 Qdrant + vLLM 后，UNION `--limit 5 --trials 2 --k2-choices 40,80,120` 有效报告为 `failures=0`、两次 trial 均 `recall@1=0.6, recall@5=0.8, recall@10=0.8`，确认没有破坏当前 UNION smoke 表现
- [ ] 若后续增强方案稳定优于默认，再将最优参数写入 `configs/default.yaml` 的独立 profile（例如 `retrieval_profiles.benchmark_tuned.join`），不覆盖 `tlcf` paper-default

#### M5.8.4 如纯调参不足，再设计 JOIN 专用召回增强
- [x] 若 Optuna 后 JOIN R@10 仍显著低于目标，新增列级/样本值补充召回设计，不直接替换 TLCF 默认路径
- [x] 候选方案 A：用 `col_embeddings` 对 query 列检索候选表，默认关闭在 plan 中通过 `column_recall_enabled` 启用；候选先按 `source_system=retrieval|join` 过滤，再只允许补入当前 candidate pool 中的表
- [x] 候选方案 A 实现约束：列召回不再合并进 C1，避免挤掉 lexical 真值候选；改为 L2 后、L3 前补入，并用 `column_recall_add_k` 限制额外 L3 候选数量
- [x] 候选方案 A 数据刷新：JOIN column Qdrant payload 已补写 `source_system`，刷新结果 `processed=1534, succeeded=1534, failed=0`，并新增 `col_embeddings.source_system` payload index
- [x] 候选方案 A smoke 结论：Qdrant/vLLM 均恢复后，JOIN `--limit 5` + `{"column_recall_enabled": true, "column_recall_top_k": 20, "column_recall_add_k": 10}` 将 `recall@10` 从默认 baseline `0.2` 提升到 `0.4`，`recall@5` 从 `0.2` 提升到 `0.4`；C2 平均从 `25.8` 增至 `32.8`，avg latency 从 `17.98s` 增至 `21.54s`
- [x] 候选方案 A limit=20 对照：默认 baseline 为 `recall@1=0.00, recall@5=0.15, recall@10=0.20, avg=15.68s, C2=25.0`；`top_k=20/add_k=10` 提升到 `recall@1=0.05, recall@5=0.20, recall@10=0.30, avg=18.89s, C2=32.0`，质量收益明确但 L3 成本增加约 `3.2s/query`
- [x] 候选方案 A 小网格结论：`add_k=5` 与 `add_k=8` 均只到 `recall@10=0.20`，无法超过 baseline；`add_k=10` 达到 `recall@10=0.30`；`add_k=15` 仍为 `recall@10=0.30` 但 avg 增至 `20.69s`，没有继续扩大价值；`top_k=10/20/40` 在 `add_k=10` 下指标相同，建议当前最佳工程折中采用 `column_recall_top_k=10, column_recall_add_k=10`
- [x] 候选方案 A query-level 诊断：limit=20 的 18 个有真值 query 中，C1 命中 13 个、baseline C2 命中 8 个、column recall 后 C2 命中 9 个；column recall 实际只新增 1 个真值候选，说明收益有限且已到平台期
- [x] 候选方案 A k2 诊断：单独扩大 `k_2=120` 将 C2 均值从 25.0 增至 53.9，但 `recall@10` 从 baseline 0.20 降到 0.15，avg latency 增至 29.51s；继续扩大 L2/L3 候选不是有效方向，排序噪声会抵消召回收益
- [x] 候选方案 A 环境诊断：一次 `recall@10=0.0` smoke 无效，根因是 vLLM 8000 未监听导致 L3 全部 `Connection error`；恢复 vLLM 后同一配置 `failures=0` 且 L3 正常输出
- [x] 候选方案 B：已新增默认关闭的 `sample_recall_enabled` / `sample_recall_add_k` / `sample_recall_min_overlap`，用 query/candidate `sample_values` 的 normalized overlap 在 L2 后、L3 前补入候选；实现中过滤 `0`、`0.0`、`.000`、`null`、`n/a` 等低信息 token，避免放大高频噪声
- [x] 候选方案 B 信号诊断：limit=20 的 84 个真值 pair 中，C1 漏掉 40 个；其中仅 7 个存在 sample overlap，且最大 overlap=1，多数为 `0`/`0.0` 这类低信息数值，说明 sample overlap 是弱信号
- [x] 候选方案 B benchmark 结论：sample recall 单独配置 `sample_recall_add_k=10,min_overlap=1` 得到 `recall@10=0.25, recall@5=0.10, avg=18.97s, C2=33.0`，只略优于 baseline 的 R@10 但劣于 column recall；column+sample hybrid 为 `recall@10=0.30, recall@5=0.15, avg=22.12s, C2=39.95`，没有超过 column-only 且延迟更高，因此不作为当前最佳配置
- [x] 候选方案 C 初探：已新增默认关闭的 `join_sample_boost_enabled` / `join_sample_boost_weight` 实验开关，并用单测证明样本值重叠可提升弱文本候选进入 C1
- [x] 候选方案 C smoke 结论：JOIN `--limit 5` 开启 `join_sample_boost_weight=0.4` 后 `recall@10` 从之前 smoke 的 0.2 降到 0.0；诊断显示它没有把第 4 个 query 的缺失真值拉入 C1，反而干扰已有真值排序，因此不作为主优化方向
- [x] 每个已实现增强方案均按 TDD 覆盖：样本值 boost、列召回 source_system 过滤、L2 后补入、`column_recall_add_k` 限制、sample recall 与低信息 token 过滤均已有单元测试
- [x] 代码审查收口：sample token 归一化集中到 `layer1.sample_tokens()`，L1 sample boost 只预计算一次 query sample tokens，sample recall 用 `limit` + heap 保留 top-K，避免全量排序；`pytest tests/unit/ -q` → 105 passed，`ruff check adacascade/ scripts/ tests/` → no issues
- [x] 当前推荐实验配置：仅启用 column recall，`{"column_recall_enabled": true, "column_recall_top_k": 10, "column_recall_add_k": 10}`；sample recall 与 join sample boost 保持 default-off，不写入 paper-default `tlcf` 超参
- [x] 前端工作台已新增显式 `JOIN tuned recall` 执行 profile，并通过 Vitest/build/lint 与浏览器请求体验证确认会发送 column recall options；默认 `Reproducible` 路径仍保持 paper-default

#### M5.8.5 验收标准
- [x] `scripts/optimize_retrieval_params.py --corpus join --limit 20 --trials 8 --timeout 900 --k2-choices 40,80,120` 可稳定输出 JSON 报告；20-trial 长搜不在当前 4090 环境继续盲跑
- [x] paper-default 与实验 plan override 的结果可在同一 runner 中对比，报告记录所有参数
- [x] 当前实验 plan 优于默认但仍属 JOIN 专用增强：结论记录到本 TODO，paper-default `tlcf` 超参保持不变
- [x] 不在当前 4090 环境执行 A100 压测；A100/local vLLM 长压测仍迁移到目标部署服务器

### M5.9 验收标准
- [x] `benchmark` 租户完成 retrieval bench JOIN + UNION 全量入湖、Profiling、Qdrant 索引、TF-IDF 重建
- [x] Matcher 两个数据集（Wikidata、MIMIC-OMOP）均可被 benchmark runner 稳定加载和执行
- [x] Retrieval benchmark 输出 R@K 与分层耗时报告
- [x] Matcher benchmark 输出 Precision / Recall / F1 与分阶段耗时报告
- [x] Optuna 输出 JOIN/UNION 小样本 tuned 参数搜索报告，并与 paper-default 对照；结论是纯调参收益有限，采用显式 JOIN column-recall profile 作为当前 4090-safe 工程折中
- [ ] A100 压测输出 `/integrate` P95、Profiling 吞吐、GPU 显存和降级情况（当前服务器跳过，迁移到目标部署服务器验收）
- [x] 根据 smoke benchmark 形成下一轮优化方向：优先做 Retrieval 参数搜索，其次评估 JOIN 专用列级/样本值召回增强
- [x] 前端端到端 demo 稳定性验证：Vite same-origin proxy + FastAPI 6008 + Qdrant + local vLLM 下，从 UI 选择 `JOIN tuned recall` 并启动真实 integrate 任务；任务 `527cc084-c051-4e38-934a-da07bca96448` 成功结束，输出 3 个 ranking candidates、33 个 mappings，SSE trace 展示到 Retrieval/Matcher 阶段，结果区 Graph/Ranking/Mappings tab 可见

---

## 当前状态

**阶段**：✅ M1 完成 → ✅ M2 工程验收完成（Week1/2/3）→ ✅ M3 本地集成完成 → ✅ M3.5 前端演示工作台完成 → ✅ M4 非 Docker 上线/运维固化完成 → ✅ M5.8 4090-safe Retrieval 调优收口 → 当前进入 M5.9/M6 前端到端 demo 稳定性验证
**最后更新**：2026-05-12

### M1 完成摘要
- 所有骨架代码实现完毕（24 个 Python 源文件）
- E2E 链路：`POST /tables` → 后台 Profiling（GPU SBERT cuda:0）→ Qdrant upsert → `READY`
- `mypy --strict` 0 错误，`ruff check` 0 警告，7/7 集成测试通过
- 已解决环境问题：PyTorch cu130→cu124（CUDA 12.6 兼容），Qdrant 二进制替代 Docker

### M2 当前完成摘要
- Retrieval Layer 1 已完成：TF-IDF + type Jaccard + C₁ 构建
- Retrieval Layer 2 已完成：Qdrant 召回、`C₁ ∩ topK` 交集约束、回退策略
- Retrieval Layer 3 已完成：LLM 批处理验证、Pydantic JSON Schema 校验、缺失分数按 0 排除
- Retrieval aggregate 已完成：C₃ 内 min-max 归一化 + `S_final` 加权排序
- Matcher Week2 公式层已完成：名称/类型/统计相似度、场景权重、候选过滤、Top-N 截断、布尔判定、1:1 匈牙利
- Matcher Week3 已完成：五段式 LLM verification、图节点真实状态流转、`/integrate` / `/discover` / `/match` / `/tasks/{task_id}`、toy 端到端测试
- 本地 Qwen AWQ 已部署到 `/root/autodl-tmp/models/qwen3.5-9b-awq`，`/root/models/qwen3.5-9b-awq` 为软链接
- vLLM 已可用：运行时验证参数为 `VLLM_GPU_MEMORY_UTILIZATION=0.35 VLLM_MAX_MODEL_LEN=4096`
- SBERT 已验证运行在 `cuda:0`，可与 vLLM 同时使用
- 最新验证：`pytest tests/unit/ -v` 23/23 通过；`pytest tests/integration/ -v` 10/10 通过；`ruff format adacascade/ tests/` 完成；`ruff check adacascade/ tests/ scripts/` 通过；`mypy --strict adacascade/` 通过

### M2 剩余工作
- 论文复现测试：retrieval R@10 与 matcher SLD F1（需要完整 benchmark run，不属于本次 toy/offline 工程验收）

### M3 本地完成摘要
- API Key 中间件已启用，除 `/healthz`、`/metrics`、文档端点外均要求 `Authorization: Bearer dev-local-token`
- `X-Tenant-Id` 已作为本地 API 权威租户上下文，覆盖表、任务与三种操作路由的 DB 可见范围
- `/metrics` 已通过 `prometheus-fastapi-instrumentator` 暴露，structlog 已配置 JSONRenderer
- Retrieval Qdrant/L3 失败与 Matcher LLM 失败已具备本地降级路径，SBERT CUDA OOM 会重试 CPU
- 本地 UAT 已覆盖 `/integrate`、`/discover`、`/match`；暂不对接课题组大系统
- 最新验证：`ruff format adacascade/ tests/` 完成；`ruff check adacascade/ tests/ scripts/` 通过；`pytest tests/unit/ -v` 23/23 通过；`pytest tests/integration/ -v` 19/19 通过；`mypy --strict adacascade/` 通过

### M4 当前完成摘要
- 非 Docker demo/部署路径已固化：Qdrant binary + FastAPI single worker + Vite same-origin public proxy
- `.env.example` 与 `docs/M4_Operations_Guide.md` 已覆盖 API/local runtime、主数据目录、启动顺序、维护脚本与常见故障
- DeepSeek API 模式 smoke 已覆盖 discover / match / integrate；API integrate 约 4 分 35 秒
- local vLLM 模式 smoke 已覆盖 runtime 切换与 integrate 空 ranking 快速结束；Matcher 不再对空 ranking 回退全量候选
- M4 维护脚本已补齐：`scripts/bulk_ingest.py`、`scripts/gc.py`、`scripts/rebuild_tfidf.py` 运维入口
- 最新验证：`pytest tests/unit/ tests/integration/` 74/74 通过；`npm --prefix frontend run test -- --run` 58/58 通过；`ruff check adacascade/ tests/ scripts/` 通过；`mypy --strict adacascade/` 通过

### 后续专项（M5）
- 全量数据入湖：retrieval bench JOIN/UNION 进入 `benchmark` 租户并完成 Profiling / Qdrant / TF-IDF
- 模式匹配数据准备：Wikidata 四场景与 MIMIC-OMOP SMD 数据均纳入 Matcher benchmark runner
- 论文复现 benchmark：retrieval R@10 与 matcher SLD F1
- A100/local vLLM 指标压测：`/integrate` P95、Profiling 吞吐、GPU 显存与降级记录
- 性能优化：分层耗时、Matcher topK 限制、LLM cache、API/local 对比
- 可选生产打包：Docker Compose / nginx / systemd / tmux 方案文档化

### 环境备注
- GPU：RTX 4090，驱动 560.35.03，CUDA 12.6，PyTorch 2.6.0+cu124
- Qdrant：二进制 v1.17.1，持久化到 `data/qdrant/`
- vLLM：`vllm==0.8.5`，`transformers==4.51.3`，默认 `xgrammar` guided decoding backend
- 代理：`http_proxy=127.0.0.1:7890`，访问 localhost 需加 `--noproxy '*'`
