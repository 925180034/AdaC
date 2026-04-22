# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## 1. 项目一句话概述

AdaCascade（**Ada**ptive scenario matching + **Cascade**d filtering）是一个嵌入课题组数据集成大系统的单体 Python 服务，用 FastAPI + LangGraph 1.1 编排四个智能体（Planner / Profiling / Retrieval / Matcher），通过三层级联过滤（TLCF）与多场景自适应模式匹配（SMD/SSD/SLD）完成数据湖的表格发现与列级对齐。

---

## 2. 权威文档与裁决规则

| 文档 | 覆盖范围 | 裁决域 |
|---|---|---|
| `docs/AdaCascade_System_Design.md` | 工程架构、API 契约、数据库 schema、部署方式、目录结构、依赖版本、降级策略 | **工程问题**的唯一真相源 |
| `docs/AdaCascade_Algorithm_Spec.md` | 四个 Agent 内部的算法细节、公式、默认超参、提示词模板、伪代码、JSON Schema | **算法问题**的唯一真相源 |

**冲突裁决**：
- 工程细节冲突（目录、依赖、端点、DB schema）→ 以系统设计文档为准
- 算法细节冲突（公式、阈值默认值、提示词）→ 以算法规格文档为准
- 两者都没写 → **先问用户，不要自己编**。这是硬规则。

**不要做的事**：
- ❌ 不要"优化"算法规格里的默认超参——`ω₁=0.7`、`θ₁=0.20`、`k₂=40` 这些都是论文实验验证过的，除非用户明确要求否则保持原值
- ❌ 不要擅自把单体架构改成微服务
- ❌ 不要擅自引入 Celery/RabbitMQ/Kafka 等重依赖，系统设计文档 §3.4 已给出轻量替代方案
- ❌ 不要把 hnswlib 换回来——我们已经用 Qdrant 了，见系统设计文档 §6.3
- ❌ 不要用 `response_format={"type": "json_object"}`，必须用 `"type": "json_schema"` + Pydantic schema（算法文档 §7）

---

## 3. 启动顺序

```bash
# 1. 初始化 SQLite 元数据库
python scripts/init_db.py

# 2. 启动 Qdrant（持久化到 ./data/qdrant）
bash scripts/start_qdrant.sh

# 3. 初始化 Qdrant collections 与 payload 索引
python scripts/init_qdrant.py

# 4. 启动 vLLM（独立 tmux/screen）
bash scripts/start_llm.sh
curl http://localhost:8000/v1/models   # 确认模型在线

# 5. 启动 FastAPI（单 worker，不得修改）
bash scripts/start_api.sh
# uvicorn adacascade.api.app:app --host 0.0.0.0 --port 8080 --workers 1
```

**关键**：必须使用 `--workers 1`。LangGraph 共享状态与 BackgroundTasks 依赖单进程内存。

---

## 4. 核心设计决策（高密度摘要）

| 维度 | 定型决策 | 依据章节 |
|---|---|---|
| 服务形态 | 单体 FastAPI，**单 worker** | 系统设计 §8.3 |
| 多智能体编排 | LangGraph **≥ 1.1.8** | 系统设计 §2.3 |
| 模式路由 | 三种模式对等：`/integrate` `/discover` `/match` | 系统设计 §4.1 |
| Checkpoint | `langgraph-checkpoint-sqlite` 的 `AsyncSqliteSaver` | 系统设计 §4.3 |
| 向量存储 | **Qdrant**（docker 单节点，有硬删除） | 系统设计 §6.3 |
| 嵌入模型 | Sentence-BERT (MiniLM-L6-v2)，**跑在 cuda:0** | 系统设计 §2.3 |
| LLM 运行时 | vLLM **≥ 0.8.5**，OpenAI 兼容 + JSON Schema 约束解码 | 系统设计 §7.4 |
| LLM 模型 | **qwen3.5:9b (AWQ 4bit)**，占 A100 #1 大约 5GB | 系统设计 §7.1 |
| 元数据库 | SQLite 默认，PostgreSQL 生产（用 SQLAlchemy 切换） | 系统设计 §6.1 |
| 原始表存储 | 本地 Parquet：`data/tables/{tenant}/{table_id}/data.parquet` | 系统设计 §3.2 |
| 异步任务 | FastAPI `BackgroundTasks` + **启动时 reconciliation** | 系统设计 §3.4 |
| 大对象外置 | `similarity_matrix` 写到 `data/artifacts/{task_id}/sim.pkl` | 系统设计 §5.1 |
| Matcher 截断 | 每个源列只取混合相似度 top-10 送 LLM | 算法规格 §4.4 |

---

## 5. 开发顺序（严格按此执行）

```
M1 骨架（2周）   ─┐  系统设计 §2 §3 §4 §6 的最小骨架
                 ├─→ 能跑通 POST /tables → Profiling → READY
                 │   四个 Agent 用 mock 数据
M2 算法（3周）   ─┤  算法规格 §2 §3 §4 的完整实现
                 ├─→ 先做 Profiling 全链路
                 ├─→ 再做 TLCF 三层，按 §8.1/§8.2 测试覆盖
                 ├─→ 最后做 Matcher 所有公式 + 场景权重 + Top-N
                 │   期间所有 LLM 调用走 §7 的 JSON Schema
M3 集成（2周）   ─┐  认证、多租户、监控、降级
M4 上线（1周）   ─┘  docker-compose 打包、运维文档
```

**每个里程碑结束前**，先跑一次对应的测试集（见算法规格 §8），再进下一阶段。

---

## 6. 代码风格与规范

- Python 3.11+，类型注解覆盖率 100%（`mypy --strict` 通过）
- 代码格式：`ruff format` + `ruff check`
- 所有公共函数必须有 Google-style docstring
- 单元测试：`pytest`，覆盖率目标 ≥ 80%
- 所有 LLM 交互必须用 Pydantic schema 强约束（见算法规格 §7）
- 所有日志用 `structlog`，必须包含 `task_id` 字段
- 配置全部从 `configs/default.yaml` 读取（用 pydantic-settings），不要硬编码

**测试命令**：
```bash
pytest tests/unit/                    # 单元测试
pytest tests/integration/             # 集成测试
mypy --strict adacascade/             # 类型检查
ruff check adacascade/                # lint
ruff format adacascade/               # 格式化
```

---

## 7. 目录结构

```
adacascade/                          # Python 包根目录
├── adacascade/
│   ├── agents/
│   │   ├── planner.py              # 算法规格 §1
│   │   ├── profiling.py            # 算法规格 §2
│   │   ├── retrieval/              # 算法规格 §3
│   │   │   ├── layer1.py           # TLCF L1：TF-IDF + Jaccard
│   │   │   ├── layer2.py           # TLCF L2：Qdrant 向量召回
│   │   │   ├── layer3.py           # TLCF L3：LLM 批处理验证
│   │   │   └── aggregate.py        # 归一化 + 聚合
│   │   └── matcher/                # 算法规格 §4
│   │       ├── text_sim.py         # Sim_name 的三个分量
│   │       ├── struct_sim.py       # Sim_type
│   │       ├── stat_sim.py         # Sim_num + Sim_cat
│   │       ├── mixed.py            # 混合相似度 + 场景权重
│   │       ├── candidates.py       # C_pi 过滤 + Top-N 截断
│   │       ├── llm_verify.py       # LLM 五段式提示词 + 判定
│   │       └── decision.py         # 布尔判定 + 1:1 匈牙利
│   ├── api/                        # FastAPI 路由 + lifespan
│   ├── db/                         # SQLAlchemy 模型
│   ├── graph/                      # LangGraph 编排
│   ├── indexing/                   # Qdrant 客户端封装
│   ├── ingest/                     # 入库 + reconcile
│   ├── llm_schemas.py              # Pydantic schema 集中定义
│   ├── llm_client.py               # OpenAI 兼容客户端
│   ├── artifacts.py                # 大对象外置工具
│   ├── state.py                    # IntegrationState TypedDict
│   └── config.py                   # pydantic-settings
├── data/                           # 运行时数据，.gitignore
├── configs/default.yaml            # 所有默认超参（勿硬编码）
├── scripts/                        # init_db, init_qdrant, start_* 等
├── tests/
│   ├── unit/                       # 算法规格 §8.1
│   ├── integration/                # 算法规格 §8.2
│   ├── fixtures/toy_lake/          # 10 表玩具数据湖
│   └── reproduction/               # 算法规格 §8.3（论文复现）
└── docs/
    ├── AdaCascade_System_Design.md
    └── AdaCascade_Algorithm_Spec.md
```

---

## 8. 遇到不确定的地方怎么办

1. **grep 设计文档**：先在两份 docs 里搜关键词，80% 的问题答案都在
2. **看公式编号**：算法规格文档里的每个公式都有论文对应编号，回查可以验证
3. **查 §5 超参表**：常见问题是"这个值设多少"，集中在算法规格 §5
4. **查 §6 对照表**：不知道某个公式代码放哪个文件，查算法规格 §6
5. **以上都不行** → **停下来问用户**，不要猜，不要编

---

## 9. 常见陷阱提示

- **Qdrant 向量归一化**：SBERT encode 时必须 `normalize_embeddings=True`，Qdrant collection 用 Cosine 距离；两者配合才等价于内积计算，不要二次归一化
- **TF-IDF 不要重训**：新表入湖只用 `transform`，不要 `fit_transform`，否则所有历史向量失效
- **TLCF L2 的交集约束**：Qdrant 查询返回的 top-k 不是 C₂，C₂ 必须等于 `C1 ∩ Qdrant_topK`（算法规格 §3.3）
- **min-max 归一化在 C₃ 内部做**：不是全库做，见算法规格 §3.5
- **SMD 场景 λ_stat = 0**：这不是"很小"，是严格等于 0；即便 Sim_stat 返回值很大也必须被乘没
- **LLM 返回 JSON Schema 错误**：绝不 silently 忽略，用 Pydantic `model_validate_json` 会自动报错，让它报
- **single worker**：不要加 `--workers N`，LangGraph 共享状态是单进程的
- **Qwen3 思考模式**：判定类任务必须 `enable_thinking=False`，不然延迟和 token 都会爆
- **checkpoint 不放大对象**：state 里的大字段一律外置到 pkl，ckpt.db 要控制在 KB 级

---

## 10. 成功标准

一个 milestone 的"已完成"定义：
- 相关的单元测试全部通过（`pytest tests/unit/`）
- 相关的集成测试全部通过（`pytest tests/integration/`）
- `mypy --strict adacascade/` 无错误
- `ruff check adacascade/` 无警告
- 论文复现测试（M2 结束时）指标达到算法规格 §3.7 / §4.9 要求的误差范围内
