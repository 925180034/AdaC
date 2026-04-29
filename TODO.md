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
- [ ] 保留 `default` 租户作为 10 表 toy demo，避免破坏当前前端演示环境
- [ ] 新建 `benchmark` 租户用于全量数据与论文复现，避免 demo 数据与实验数据混杂
- [ ] 明确数据发现数据集：`tests/fixtures/retrieval_bench/join/`（1534 表、230 queries、1226 gt pairs）
- [ ] 明确数据发现数据集：`tests/fixtures/retrieval_bench/union/`（5487 表、823 queries、6512 gt pairs）
- [ ] 明确模式匹配数据集一：`tests/fixtures/matcher_bench/wikidata/`（Musicians 四场景：joinable / semjoinable / unionable / viewunion）
- [ ] 明确模式匹配数据集二：`tests/fixtures/matcher_bench/mimic_omop/`（MIMIC-III → OMOP，schema-only SMD，268 列映射标注）
- [ ] 数据发现 JOIN 与 UNION 使用隔离 corpus / artifact，不共用一个 TF-IDF 模型，避免语料分布互相污染
- [ ] MIMIC-OMOP schema-only 数据不得走依赖 Parquet 实例的常规 Profiling，必须走专用 SMD schema ingestion 路径
- [ ] 记录每个数据集的表数、列数、ground truth 数量、任务类型（JOIN/UNION/SMD/SSD/SLD）到 benchmark 报告

### M5.2 全量入湖与 Profiling 批处理
- [x] 扩展 `scripts/bulk_ingest.py` 支持 `--tenant-id benchmark`，可覆盖 manifest 中 tenant，并拒绝跨租户 `table_id` 碰撞
- [x] 新增 `scripts/profile_ingested.py`：批量处理有 Parquet 实例数据的 `INGESTED` 表，调用 Profiling → SBERT 编码 → Qdrant upsert → 状态转 `READY`
- [x] `profile_ingested.py` 支持 `--tenant-id`、`--limit`、`--retry-failed`、`--source-system` 与失败摘要，`--retry-failed` 会先复位为 `INGESTED` 再重跑
- [x] 新增 schema-only ingestion 路径：读取 MIMIC-OMOP JSON schema，写入 `TableRegistry` / `ColumnMetadata`，用表名、列名、列描述构造可加载 profile
- [x] schema-only SMD 路径跳过实例统计特征：`numeric_stats=None`、`categorical_stats=None`、`sample_values=[]`，但保留 `col_type` 与 description
- [x] schema-only SMD 路径仍需生成 SBERT 表/列向量并 upsert Qdrant，保证可被 Matcher benchmark 与可选检索调试加载
- [x] 小规模验证：已导入并 profile 20 张 retrieval bench JOIN 表，确认 SQLite / Qdrant / SBERT / 状态流转正确，并生成 `tfidf_benchmark_join.pkl`
- [ ] 中规模验证：扩展到 100 / 500 张表，记录单表 Profiling 平均耗时、失败率、GPU 显存
- [ ] 全量导入 retrieval bench JOIN + UNION，完成 7021 张候选表入湖与 Qdrant 索引
- [ ] 处理 matcher bench Wikidata 数据，确保 source/target 表均可被 direct Python benchmark runner 加载
- [ ] 处理 matcher bench MIMIC-OMOP schema-only 数据，确保无实例数据的 SMD 场景可直接进入 Matcher
- [x] 扩展 `scripts/rebuild_tfidf.py` 支持 `--tenant-id benchmark` 与 `--corpus join|union|matcher|all`，并提供 Retrieval L1 显式加载 scoped artifact 的入口
- [ ] 全量入湖后分别重建 JOIN、UNION、Matcher corpus 的 TF-IDF artifact，并记录 vocabulary size 与训练耗时

### M5.3 数据发现 / Retrieval Benchmark
- [ ] 新增 `scripts/run_retrieval_benchmark.py` 或 `tests/reproduction/test_retrieval_bench_*.py`
- [ ] Benchmark runner 直接调用 Python 层 Retrieval 核心函数，不通过 REST `/discover`，避免 HTTP/LangGraph/任务轮询噪声
- [ ] Benchmark runner 默认关闭 L3/Matcher LLM cache，保证耗时与质量指标可复现；生产/demo 运行可单独开启 cache
- [ ] JOIN benchmark：读取 `retrieval_bench/join/queries.json` 与 `ground_truth.json`，使用 JOIN 专属 TF-IDF artifact 批量运行 Retrieval
- [ ] UNION benchmark：读取 `retrieval_bench/union/queries.json` 与 `ground_truth.json`，使用 UNION 专属 TF-IDF artifact 批量运行 Retrieval
- [ ] 指标输出：R@1、R@5、R@10、平均耗时、P50、P95、失败率
- [ ] 分层耗时输出：L1 lexical、L2 Qdrant、L3 LLM rerank、aggregate
- [ ] 先跑 `--limit 20` smoke，再跑 `--limit 50/100`，最后跑完整 JOIN/UNION benchmark
- [ ] 对照论文目标：JOIN R@10 ≥ 63.9% ± 3%；UNION 指标按算法规格/ground truth 报告补齐

### M5.4 模式匹配 / Matcher Benchmark
- [ ] 新增 `scripts/run_matcher_benchmark.py` 或 `tests/reproduction/test_matcher_bench_*.py`
- [ ] Matcher benchmark runner 直接调用 Python 层 Matcher 函数，不通过 REST `/match`，避免 HTTP/LangGraph/任务轮询噪声
- [ ] Benchmark runner 默认关闭 Matcher LLM cache，生产/demo cache 与论文复现 benchmark 配置分离
- [ ] Wikidata benchmark：覆盖 joinable、semjoinable、unionable、viewunion 四个场景
- [ ] MIMIC-OMOP benchmark：覆盖 schema-only SMD 场景，验证 268 条列映射标注
- [ ] MIMIC-OMOP benchmark 使用 schema-only profiles：列名 + 类型 + 描述，不要求 Parquet 实例数据或统计特征
- [ ] 指标输出：Precision、Recall、F1、平均耗时、P50、P95、LLM pair 数、失败率
- [ ] 分阶段输出：candidate filtering 耗时、LLM verification 耗时、decision / 1:1 耗时
- [ ] 先跑单 pair smoke，再跑每个场景小样本，最后跑完整 matcher benchmark
- [ ] 对照论文目标：SLD F1 ≥ 92.52% ± 3%；SMD/SSD/其他场景按算法规格补齐目标指标

### M5.5 性能瓶颈定位与优化
- [ ] 给 Retrieval 与 Matcher 事件补充分层耗时字段，前端和日志均可看到每层耗时
- [ ] 限制 integrate 的 Matcher 目标表数量，只对 Retrieval ranking topK 进入 Matcher（例如 top 3/5/10，可配置）
- [ ] 增加 L3 rerank 缓存：同一 query table + candidate table 不重复请求 LLM，仅用于 production/demo 加速
- [ ] 增加 Matcher verification 缓存：同一 source column + target column + scenario 不重复请求 LLM，仅用于 production/demo 加速
- [ ] 明确 benchmark 配置必须禁用 LLM cache，避免缓存命中污染 P50/P95 与成本统计
- [ ] 评估 LLM batch size、并发数、timeout 对 API 与 local vLLM 的影响
- [ ] 区分论文默认配置、benchmark 复现配置与工程加速配置，避免随意修改算法规格默认超参
- [ ] 输出 API 模式与 local vLLM 模式对比：质量、耗时、失败率、成本/显存

### M5.6 A100 / local vLLM 压测
- [ ] 在 A100 环境下启动 local vLLM，记录模型、量化方式、max_model_len、gpu_memory_utilization
- [ ] 压测 `/integrate`：记录 P50 / P95 / P99、ranking 数、mappings 数、失败率
- [ ] 压测 Profiling 吞吐：目标 ≥ 1000 张/分钟（A100 + GPU SBERT），记录 batch size 与显存
- [ ] 记录 GPU 显存、水位、OOM/CPU fallback 情况
- [ ] 输出压测结论：是否达到 M4 原定性能指标；未达到时列出瓶颈与优化项

### M5.7 验收标准
- [ ] `benchmark` 租户完成 retrieval bench JOIN + UNION 全量入湖、Profiling、Qdrant 索引、TF-IDF 重建
- [ ] Matcher 两个数据集（Wikidata、MIMIC-OMOP）均可被 benchmark runner 稳定加载和执行
- [ ] Retrieval benchmark 输出 R@K 与分层耗时报告
- [ ] Matcher benchmark 输出 Precision / Recall / F1 与分阶段耗时报告
- [ ] A100 压测输出 `/integrate` P95、Profiling 吞吐、GPU 显存和降级情况
- [ ] 根据 benchmark 结果形成下一轮优化清单，区分算法质量问题与工程性能问题

---

## 当前状态

**阶段**：✅ M1 完成 → ✅ M2 工程验收完成（Week1/2/3）→ ✅ M3 本地集成完成 → ✅ M3.5 前端演示工作台完成 → ✅ M4 非 Docker 上线/运维固化完成 → 当前准备进入 M5 全量数据入湖、Benchmark 与性能优化
**最后更新**：2026-04-29

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
