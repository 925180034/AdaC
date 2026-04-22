# AdaCascade · 顶层系统设计文档

> **项目名**：**AdaCascade**（**Ada**ptive scenario matching + **Cascade**d filtering）
> **代号 / 命名空间**：`adac` / `adacascade`
> **版本**：v2.2
> **定位**：作为独立服务嵌入课题组数据集成大系统，提供数据发现与模式匹配能力
> **形态**：单体 Python 服务（FastAPI + LangGraph），外挂 Qdrant + vLLM 两个独立进程
> **LLM 后端**：本地 vLLM 托管 **qwen3.5:9b**（AWQ 4bit 量化），OpenAI 兼容接口 + JSON Schema 约束解码
> **编排框架**：**LangGraph 1.1.x**（2025-10 GA 首个稳定大版本）

命名说明：**Ada** 指向本框架的场景自适应匹配（SMD / SSD / SLD 三场景权重动态切换），**Cascade** 指向 TLCF 三层级联过滤（TF-IDF → 向量 → LLM）。两大创新点合并为 AdaCascade，学术写作中可自然称为 "the AdaCascade framework"，工程代码中使用 `adacascade` 作为 Python 包名、`adac` 作为短前缀。

### v2.2 对 v2.1 的关键变更

1. **向量引擎**：`hnswlib`（进程内）→ **Qdrant**（独立轻量服务）。解决硬删除、并发读写、免定期重建三个痛点。
2. **SBERT 设备**：CPU → **GPU（cuda:0）**，与 vLLM 共享 A100 #1。Profiling 吞吐量数量级提升。
3. **LLM 结构化输出**：JSON Mode → **JSON Schema 约束解码**（Pydantic 生成 schema），省去重试逻辑。
4. **异步任务鲁棒性**：`BackgroundTasks` + **启动时 reconciliation**，保证进程 crash 后孤儿入库任务自动恢复。
5. **超大中间变量外置**：`similarity_matrix` 序列化到文件，checkpoint 仅存路径引用。
6. **Matcher Top-N 截断**：LLM 判定前对候选列按混合相似度截断到 Top-10，规避超宽表上下文爆炸。

---

## 1. 系统定位与设计原则

### 1.1 定位
AdaCascade 是一个**单体 Python 服务**，通过 REST API 嵌入课题组大系统，承担数据湖的「语义计算层」：接收用户或上游系统入湖的 Web 表格，完成特征画像、TLCF 级联发现、多场景列级匹配，并把结构化结果回传给调用方。

### 1.2 设计原则
- **单体优先**：一个 FastAPI 进程承载四智能体与业务逻辑；外挂 Qdrant 与 vLLM 两个独立服务。不做微服务拆分。
- **三模式对等**：数据发现、模式匹配、端到端全链路三种工作模式平权，都是一等公民。
- **LLM 解耦**：所有 LLM 调用走 OpenAI 兼容接口，换模型只改 `LLM_BASE_URL`，业务代码零改动。
- **资源隔离**：A100 #1 独占本系统（vLLM + SBERT 共享），A100 #2 留给组员。
- **可降级**：无 GPU 时切换 `LLM_BASE_URL` 到线上 API、`SBERT_DEVICE` 到 CPU，保留完整链路。

---

## 2. 总体架构

### 2.1 逻辑分层
```
┌──────────────────────────────────────────────────────────────┐
│  L0  调用方：课题组大系统 或 研究者（浏览器/脚本）            │
└────────────────────────┬─────────────────────────────────────┘
                         │  HTTPS / JSON
┌────────────────────────▼─────────────────────────────────────┐
│  L1  FastAPI 服务（单进程，uvicorn）                          │
│      /tables   /integrate   /discover   /match   /tasks ...  │
│      + BackgroundTasks(Profiling)                            │
│      + 启动时 reconciliation（回补孤儿 INGESTED 任务）        │
└────────────────────────┬─────────────────────────────────────┘
                         │
┌────────────────────────▼─────────────────────────────────────┐
│  L2  LangGraph 1.1 编排层（同进程内）                         │
│      Planner ──► Profiling ──► Retrieval ──► Matcher         │
│                    │                │         ▲              │
│                    └──► 条件边 ─────┴─────────┘              │
│      共享状态 IntegrationState（指针化，大对象外置）          │
│      持久化：AsyncSqliteSaver → data/ckpt.db                 │
└───┬──────────────────┬──────────────────┬────────────────────┘
    │ OpenAI 兼容 API   │ gRPC             │ 进程内
    ▼                   ▼                  ▼
┌───────────────────┐ ┌──────────────────┐ ┌──────────────────┐
│ L3a  vLLM 服务    │ │ L3b  Qdrant      │ │ L3c  SBERT (GPU) │
│ qwen3.5:9b (AWQ)  │ │ 单节点 docker    │ │ all-MiniLM-L6-v2 │
│ + JSON Schema 解码│ │ 硬删除/并发读写   │ │ cuda:0 常驻      │
│ A100 #1 ~5GB      │ │ 持久化到卷        │ │ A100 #1 ~0.1GB   │
└───────────────────┘ └──────────────────┘ └──────────────────┘
                      │
                      ▼
┌──────────────────────────────────────────────────────────────┐
│  L3d  存储：SQLite（元数据+任务+checkpoint）+ 本地文件系统    │
│        data/tables/*.parquet  +  data/artifacts/*.pkl         │
└──────────────────────────────────────────────────────────────┘
```

### 2.2 物理部署（双 A100 环境）
| 资源 | 用途 | 显存占用 |
|---|---|---|
| 主机 CPU / 内存 | FastAPI + LangGraph + Qdrant client + 任务调度 | 单进程常驻 |
| **A100 #1** | vLLM (qwen3.5:9b AWQ) + SBERT (MiniLM) | ≈ 5.1 GB（~14% 占用） |
| A100 #2 | 组员其他任务 | 完全隔离 |
| 本地磁盘 | SQLite、Parquet、Qdrant volume、artifacts | 单机文件系统 |

> 说明：A100 #1 上 vLLM 与 SBERT 通过 `gpu-memory-utilization=0.35` 为 vLLM 预留 KV-cache，SBERT 作为常驻小模型占用极低，**不会** 与 vLLM 发生资源冲突。

### 2.3 技术栈
| 组件 | 选型 | 版本 / 说明 |
|---|---|---|
| Web 框架 | **FastAPI** + Uvicorn | 单进程、异步、自动 OpenAPI |
| 多智能体编排 | **LangGraph** | **≥ 1.1.8**（2025-10 GA） |
| Checkpoint 持久化 | **langgraph-checkpoint-sqlite** | AsyncSqliteSaver 配合 lifespan |
| 嵌入模型 | **Sentence-BERT** (all-MiniLM-L6-v2) | **GPU (cuda:0)** 推理，384 维 |
| 向量存储 | **Qdrant**（docker 单节点） | 硬删除、并发读写、payload 过滤（多租户隔离） |
| LLM 运行时 | **vLLM ≥ 0.8.5** | OpenAI 兼容、AWQ 量化、**JSON Schema 结构化输出** |
| LLM 模型 | **qwen3.5:9b（AWQ 4bit）** | 论文基线 LLaMA3.1-8B 的中文友好替代 |
| 元数据库 | **SQLite** 默认 / PostgreSQL 生产 | SQLAlchemy 切换 |
| LLM 客户端 | **openai-python** | 改 BASE_URL 即可切换后端 |
| 配置 | **pydantic-settings** + `.env` | 阈值、路径、模型名集中管理 |
| 日志 / 指标 | structlog + prometheus-fastapi-instrumentator | JSON 日志 + `/metrics` 端点 |

---

## 3. 数据摄入与表格生命周期

### 3.1 表格的来源（三条摄入通道）
| 通道 | 入口 | 使用场景 |
|---|---|---|
| **A. REST 主动上传** | `POST /tables` 携带 Parquet/CSV 文件 | 研究者手工上传、大系统集成时的主要方式 |
| **B. 批量导入脚本** | `python scripts/bulk_ingest.py --dir /path/to/csv_folder` | 冷启动时一次性导入已有数据集（OpenData、Valentine benchmark） |
| **C. 大系统引用注册** | `POST /tables` 只传 `source_uri` 与 schema，不传文件本体 | 文件已在大系统共享存储中 |

### 3.2 表格存储布局
```
data/tables/{tenant_id}/{table_id}/
    ├── data.parquet          # 统一转 Parquet（CSV/XLSX 入库时即转码）
    └── manifest.json         # schema 快照、行列数、上传者、哈希
```

### 3.3 入库流程（状态机）
```
       POST /tables
              │
              ▼
       ┌────────────┐   格式错误/重复      ┌─────────┐
       │  PENDING   │────────────────────▶│ REJECTED│
       └─────┬──────┘                     └─────────┘
             │  校验通过、转 Parquet、schema_hash 计算
             ▼
       ┌────────────┐
       │  INGESTED  │  文件已落盘、元数据已入库，未建索引
       └─────┬──────┘
             │  BackgroundTasks 拉起 ProfilingAgent
             ▼
       ┌────────────┐   Profiling 失败      ┌─────────┐
       │ PROFILING  │────────────────────▶ │  FAILED │
       └─────┬──────┘                     └─────────┘
             │  统计特征 + SBERT(GPU) 向量 + upsert 到 Qdrant
             ▼
       ┌────────────┐
       │   READY    │  所有三种模式可用
       └─────┬──────┘
             │  用户主动 DELETE 或 schema 变更
             ▼
       ┌────────────┐
       │  ARCHIVED  │  从 Qdrant 硬删除，元数据保留
       └────────────┘
```

**关键实现要点**：
- `POST /tables` 202 Accepted 立即返回，Profiling 由 FastAPI `BackgroundTasks` 异步执行。
- 只有 `READY` 状态的表才参与候选池；Retrieval 查询 Qdrant 时用 payload filter 强制过滤 `status=READY`。

### 3.4 异步任务鲁棒性（启动时 reconciliation）

单纯依赖 `BackgroundTasks` 存在一个真实的漏洞：进程在 Profiling 期间 crash，arrive 中排队的任务会丢失，状态机永远卡在 `INGESTED` 或 `PROFILING`。

**解决方案**：FastAPI 启动 lifespan 中增加一次扫描：

```python
# adacascade/ingest/reconcile.py
async def reconcile_orphan_ingests(db, scheduler):
    """
    进程启动时扫描孤儿记录，重新入队。这是比 Taskiq/Celery 更轻的方案。
    """
    orphans = db.execute(
        "SELECT table_id FROM table_registry "
        "WHERE status IN ('INGESTED', 'PROFILING')"
    ).fetchall()
    for (table_id,) in orphans:
        # 把 PROFILING 状态回退到 INGESTED（避免误判为进行中）
        db.execute(
            "UPDATE table_registry SET status='INGESTED' WHERE table_id=?",
            (table_id,))
        # 重新交给后台任务
        scheduler.add_task(run_profiling, table_id)
    db.commit()
```

配合乐观锁（`UPDATE ... WHERE status='INGESTED'` 检查返回行数）防止并发重复执行。这套方案**零新依赖**即可达到"进程重启任务不丢"的保证；若未来真需要更复杂的调度（延时、重试、优先级），再引入 Taskiq（见附录 B）。

### 3.5 Schema 变更处理
同一 `(tenant_id, source_system, table_name)` 再次上传时：
1. 计算新文件的 `schema_hash`（列名 + 类型 + 顺序的 SHA-256）。
2. 与已有记录比对：
   - **一致**：仅更新 `row_count`、`updated_at`，不重建向量。
   - **不一致**：原记录置 `ARCHIVED`，从 Qdrant 硬删除旧向量，新建记录重走入库流程。

### 3.6 并发与幂等
- 同一 `task_id` 任务重复提交不会重复执行（DB 唯一键 + LangGraph checkpoint 自然幂等）。
- 同一文件重复上传通过 `content_hash + schema_hash` 双重去重，命中则复用已有 `table_id`。

### 3.7 清理与归档
- **软删除**：`DELETE /tables/{id}` 置 `ARCHIVED`，Parquet 保留，**Qdrant 同步硬删除对应 point**（Qdrant 原生支持，不再需要维护 mask 名单或定期重建）。
- **硬清理**：`scripts/gc.py` 定期删除超过保留期的 `ARCHIVED` 记录及其 Parquet 文件。

---

## 4. 三种工作模式（对等设计）

### 4.1 模式对比
| 模式 | 端点 | 输入 | 执行路径 | 输出 |
|---|---|---|---|---|
| **全链路** | `/integrate` | 查询表 Tq | Planner → Profiling → Retrieval → Matcher | 排名 + 列映射 |
| **仅发现** | `/discover` | 查询表 Tq | Planner → Profiling → Retrieval | 候选表排名 |
| **仅匹配** | `/match` | 源表 Tq + 目标表 Tt | Planner → Profiling → [跳过 Retrieval] → Matcher | 列映射 |

### 4.2 LangGraph 1.1 图定义

```python
# adacascade/graph/build.py
from langgraph.graph import StateGraph, START, END
from adacascade.agents import planner, profiling, retrieval, matcher
from adacascade.state import IntegrationState


def route_after_planner(state: IntegrationState) -> str:
    return "profiling_pair" if state["task_type"] == "MATCH_ONLY" else "profiling_pool"

def route_after_profiling(state: IntegrationState) -> str:
    return "matcher" if state["task_type"] == "MATCH_ONLY" else "retrieval"

def route_after_retrieval(state: IntegrationState) -> str:
    return END if state["task_type"] == "DISCOVER_ONLY" else "matcher"


def build_graph():
    g = StateGraph(IntegrationState)
    g.add_node("planner",         planner.run)
    g.add_node("profiling_pool",  profiling.run_pool)   # Tq + 候选池（查询 Qdrant）
    g.add_node("profiling_pair",  profiling.run_pair)   # Tq + Tt
    g.add_node("retrieval",       retrieval.run)
    g.add_node("matcher",         matcher.run)

    g.add_edge(START, "planner")
    g.add_conditional_edges("planner", route_after_planner,
        {"profiling_pool": "profiling_pool", "profiling_pair": "profiling_pair"})
    g.add_edge("profiling_pair", "matcher")
    g.add_conditional_edges("profiling_pool", route_after_profiling,
        {"retrieval": "retrieval", "matcher": "matcher"})
    g.add_conditional_edges("retrieval", route_after_retrieval,
        {"matcher": "matcher", END: END})
    g.add_edge("matcher", END)
    return g
```

### 4.3 FastAPI lifespan

```python
# adacascade/api/app.py
from contextlib import asynccontextmanager
from fastapi import FastAPI
from langgraph.checkpoint.sqlite.aio import AsyncSqliteSaver
from qdrant_client import AsyncQdrantClient
from adacascade.graph import build_graph
from adacascade.ingest.reconcile import reconcile_orphan_ingests
from adacascade.config import settings


@asynccontextmanager
async def lifespan(app: FastAPI):
    # 1) 打开 checkpoint
    async with AsyncSqliteSaver.from_conn_string(settings.CKPT_PATH) as ckpt:
        # 2) 连接 Qdrant
        app.state.qdrant = AsyncQdrantClient(url=settings.QDRANT_URL)
        # 3) 编译图
        app.state.graph = build_graph().compile(checkpointer=ckpt)
        # 4) 启动时 reconciliation（回补孤儿入库任务）
        await reconcile_orphan_ingests(app.state.db, app.state.scheduler)
        yield
        await app.state.qdrant.close()

app = FastAPI(title="AdaCascade", lifespan=lifespan)
```

### 4.4 API 端点一览
| 端点 | 方法 | 语义 |
|---|---|---|
| `POST /tables` | 上传/注册新表，触发后台 Profiling，返回 `table_id` |
| `GET  /tables/{id}` | 查询表的 status |
| `GET  /tables` | 列表查询，按 `tenant_id`、`status` 过滤 |
| `DELETE /tables/{id}` | 软删除 + Qdrant 硬删除 |
| `POST /integrate` | **全链路**：query_table_id → 排名 + 映射 |
| `POST /discover` | **仅发现**：query_table_id → 候选排名 |
| `POST /match` | **仅匹配**：source_table_id + target_table_id → 列映射 |
| `GET  /tasks/{task_id}` | 任务状态与 agent_step 执行轨迹 |
| `GET  /healthz`、`GET /metrics` | 健康检查与 Prometheus 指标 |

---

## 5. 核心智能体设计

### 5.1 共享状态对象（含大对象外置策略）

```python
# adacascade/state.py
from typing import TypedDict, Literal, Optional
from datetime import datetime

class IntegrationState(TypedDict, total=False):
    # 任务元信息
    task_id:   str
    tenant_id: str
    task_type: Literal["INTEGRATE", "DISCOVER_ONLY", "MATCH_ONLY"]
    created_at: datetime

    # Planner 输出
    plan: dict          # Θ: θ1, θ2, θ3, w1, w2, w3

    # Profiling 输出（轻量：只存 col_id 与 SBERT 向量 id，真实数据在 SQLite/Qdrant）
    query_profile:      dict                     # Φq 的句柄
    target_profile:     dict                     # Φt（仅 MATCH_ONLY）
    candidate_profiles: dict[str, dict]          # {ΦTi} 的句柄

    # TLCF 三层中间结果（只存 id 列表）
    c1_meta: list[str]
    c2_vec:  list[str]
    c3_llm:  list[str]

    # 最终输出
    ranking:           list[dict]                # 候选排名（N×O(1) 字段）
    # 大对象外置：只存路径引用，真实矩阵在 data/artifacts/{task_id}/sim.pkl
    similarity_matrix_path: Optional[str]
    final_mappings:    list[dict]

    # 执行轨迹
    trace: list[dict]
    status: Literal["RUNNING", "SUCCESS", "FAILED"]
```

**大对象外置规则**：任何预计 > 1 MB 的中间变量（如 `similarity_matrix` 在数百列 × 数百列规模）都序列化到 `data/artifacts/{task_id}/*.pkl`，state 里只存路径字符串。这样 `ckpt.db` 的每个 checkpoint 快照都控制在 KB 级别。

### 5.2 四智能体职责

| Agent | 输入 | 核心动作 | 输出（写入 state） |
|---|---|---|---|
| **Planner** | 请求参数 + Tq（+ 可选 Tt） | LLM 识别 `task_type`，生成 plan 配置 | `task_type`, `plan` |
| **Profiling** | Tq（+ 候选池 / Tt） | 元数据解析 + 统计特征 + **SBERT(GPU) 批量编码** + upsert Qdrant | profiles（句柄） |
| **Retrieval** | profiles + plan | **TLCF 三层过滤**：TF-IDF → Qdrant 向量检索 → LLM 验证 | `c1_meta`, `c2_vec`, `c3_llm`, `ranking` |
| **Matcher** | profiles + ranking（或 Tt） | 场景识别（SMD/SSD/SLD）→ 混合相似度 → **Top-N 截断** → LLM 判定 | `similarity_matrix_path`, `final_mappings` |

**Matcher 的 Top-N 截断**（对应评审意见第 6 条）：

对于单个查询列 `c_q`，Matcher 先用混合相似度 `Sim_mixed = λ1·Text + λ2·Struct + λ3·Stat` 计算它与所有候选列的得分，然后**只把 Top-10 候选列的统计信息 + 样本值拼进 LLM 的 prompt**，其余列不再送入 LLM。这样即便查询表有数百列 × 候选表有数百列，单次 LLM 调用的上下文也被严格控制在 ~2K token 以内，规避 Qwen3 8K 上下文的爆炸与"lost in the middle"问题。

---

## 6. 数据库与存储设计

### 6.1 存储划分
| 数据类别 | 介质 | 说明 |
|---|---|---|
| 原始表（Parquet） | 本地文件 `data/tables/{tenant}/{table_id}/data.parquet` | §3.2 |
| 元数据、任务记录、结果 | **SQLite** 默认 / PostgreSQL 生产 | `DATABASE_URL` 切换 |
| 表级/列级稠密向量 | **Qdrant**（docker 单节点） | payload 过滤 tenant 与 status |
| LangGraph checkpoint | SQLite `data/ckpt.db` | AsyncSqliteSaver |
| 大对象 artifacts | 本地文件 `data/artifacts/{task_id}/*.pkl` | similarity_matrix 等 |
| LLM 校验缓存（可选） | SQLite `data/cache.db` | (col_q, col_c) 哈希，TTL 7 天 |

### 6.2 元数据库表设计（SQLite / PostgreSQL 通用）

#### 6.2.1 表与列元数据
```sql
CREATE TABLE table_registry (
    table_id        TEXT PRIMARY KEY,             -- UUID
    tenant_id       TEXT NOT NULL DEFAULT 'default',
    source_system   TEXT NOT NULL,                -- upload/bulk/host_platform
    source_uri      TEXT NOT NULL,                -- data/tables/.../data.parquet
    table_name      TEXT NOT NULL,
    row_count       INTEGER,
    col_count       INTEGER,
    schema_hash     TEXT,                         -- SHA-256(列名+类型+序)
    content_hash    TEXT,                         -- SHA-256(parquet)
    uploaded_by     TEXT,
    uploaded_at     TIMESTAMP NOT NULL,
    updated_at      TIMESTAMP NOT NULL,
    status          TEXT NOT NULL DEFAULT 'PENDING'
                    CHECK(status IN ('PENDING','INGESTED','PROFILING',
                                     'READY','FAILED','ARCHIVED','REJECTED'))
);
CREATE INDEX ix_tr_tenant_status ON table_registry(tenant_id, status);
CREATE UNIQUE INDEX ix_tr_content ON table_registry(tenant_id, content_hash);

CREATE TABLE column_metadata (
    column_id       TEXT PRIMARY KEY,
    table_id        TEXT NOT NULL REFERENCES table_registry(table_id) ON DELETE CASCADE,
    ordinal         INTEGER NOT NULL,
    col_name        TEXT NOT NULL,
    col_type        TEXT NOT NULL,
    col_description TEXT,
    null_ratio      REAL,
    distinct_ratio  REAL,
    stat_summary    TEXT,                         -- JSON
    qdrant_point_id TEXT,                         -- Qdrant 中对应 point 的 UUID
    UNIQUE(table_id, ordinal)
);
```

#### 6.2.2 任务与执行轨迹
```sql
CREATE TABLE integration_task (
    task_id         TEXT PRIMARY KEY,
    tenant_id       TEXT NOT NULL DEFAULT 'default',
    task_type       TEXT NOT NULL
                    CHECK(task_type IN ('INTEGRATE','DISCOVER_ONLY','MATCH_ONLY')),
    query_table_id  TEXT REFERENCES table_registry(table_id),
    target_table_id TEXT REFERENCES table_registry(table_id),
    plan_config     TEXT,                         -- JSON
    status          TEXT NOT NULL,
    submitted_by    TEXT,
    submitted_at    TIMESTAMP NOT NULL,
    finished_at     TIMESTAMP,
    error_message   TEXT,
    artifacts_dir   TEXT                          -- data/artifacts/{task_id}
);
CREATE INDEX ix_it_status ON integration_task(status, submitted_at);

CREATE TABLE agent_step (
    step_id         INTEGER PRIMARY KEY AUTOINCREMENT,
    task_id         TEXT NOT NULL,
    agent_name      TEXT NOT NULL,
    layer           TEXT,                         -- TLCF L1/L2/L3
    input_size      INTEGER,
    output_size     INTEGER,
    latency_ms      INTEGER,
    llm_tokens      INTEGER,
    recall_loss     REAL,
    started_at      TIMESTAMP NOT NULL,
    finished_at     TIMESTAMP
);
CREATE INDEX ix_as_task ON agent_step(task_id);
```

#### 6.2.3 结果与模型版本
```sql
CREATE TABLE discovery_result (
    task_id         TEXT NOT NULL,
    rank            INTEGER NOT NULL,
    candidate_table TEXT NOT NULL REFERENCES table_registry(table_id),
    score           REAL NOT NULL,
    layer_scores    TEXT,                         -- JSON: {l1, l2, l3}
    PRIMARY KEY(task_id, rank)
);

CREATE TABLE column_mapping (
    mapping_id      TEXT PRIMARY KEY,
    task_id         TEXT NOT NULL,
    src_column_id   TEXT NOT NULL REFERENCES column_metadata(column_id),
    tgt_column_id   TEXT NOT NULL REFERENCES column_metadata(column_id),
    scenario        TEXT NOT NULL,                -- SMD/SSD/SLD
    confidence      REAL NOT NULL,
    is_matched      INTEGER NOT NULL,
    reasoning       TEXT,
    created_at      TIMESTAMP NOT NULL,
    UNIQUE(task_id, src_column_id, tgt_column_id)
);

CREATE TABLE model_version (
    model_key       TEXT PRIMARY KEY,             -- sbert / llm / matcher
    version         TEXT NOT NULL,
    params          TEXT,                         -- JSON
    activated_at    TIMESTAMP NOT NULL
);
```

### 6.3 Qdrant 向量存储设计

替代 v2.1 中的 hnswlib。两条 Collection 分别承载表级与列级向量：

| Collection | 向量维度 | 距离 | payload 字段 |
|---|---|---|---|
| `tbl_embeddings` | 384 | Cosine | `tenant_id`, `table_id`, `status`, `created_at` |
| `col_embeddings` | 384 | Cosine | `tenant_id`, `table_id`, `column_id`, `status`, `col_type` |

**初始化脚本片段**：
```python
# scripts/init_qdrant.py
from qdrant_client import QdrantClient
from qdrant_client.models import Distance, VectorParams, PayloadSchemaType

client = QdrantClient(url="http://localhost:6333")

for name in ["tbl_embeddings", "col_embeddings"]:
    if not client.collection_exists(name):
        client.create_collection(
            collection_name=name,
            vectors_config=VectorParams(size=384, distance=Distance.COSINE),
        )
    # 为 payload 过滤字段建索引（加速 tenant + status 过滤）
    for field, schema in [("tenant_id", PayloadSchemaType.KEYWORD),
                          ("status",    PayloadSchemaType.KEYWORD),
                          ("table_id",  PayloadSchemaType.KEYWORD)]:
        client.create_payload_index(name, field, schema)
```

**检索调用示例**（Retrieval Agent 的 L2 层）：
```python
from qdrant_client.models import Filter, FieldCondition, MatchValue

hits = qdrant.search(
    collection_name="col_embeddings",
    query_vector=query_col_emb,
    query_filter=Filter(must=[
        FieldCondition(key="tenant_id", match=MatchValue(value=tenant_id)),
        FieldCondition(key="status",    match=MatchValue(value="READY")),
    ]),
    limit=settings.TLCF_L2_TOPK,
)
```

**删除（软删除联动）**：
```python
qdrant.delete(collection_name="col_embeddings",
              points_selector=Filter(must=[
                  FieldCondition(key="table_id", match=MatchValue(value=table_id))
              ]))
```

**Qdrant 相较 hnswlib 的工程收益**：
1. **硬删除**：`DELETE /tables/{id}` 可以真正从向量索引里删掉记录，不再需要维护 mask 名单或定期重建。
2. **并发读写**：Qdrant 独立进程通过 gRPC/REST 提供多客户端并发访问能力，为未来多 worker 水平扩展保留接口。
3. **Payload 过滤**：多租户与状态过滤在检索层一并完成，比 hnswlib 取出大 top-K 再在内存过滤更高效。
4. **持久化零运维**：数据自动落 volume，进程重启无需 reload。

### 6.4 目录约定
```
data/
├── tables/{tenant}/{table_id}/
│   ├── data.parquet
│   └── manifest.json
├── artifacts/{task_id}/             # 大对象外置
│   ├── sim.pkl                      # similarity_matrix
│   └── ...
├── qdrant/                          # Qdrant volume
├── metadata.db                      # SQLite 元数据
├── ckpt.db                          # LangGraph checkpoint
└── cache.db                         # LLM 校验缓存（可选）
```

---

## 7. LLM 后端设计

### 7.1 模型选型
| 角色 | 模型 | 量化 | 显存 | 说明 |
|---|---|---|---|---|
| 主力（所有 Agent） | **qwen3.5:9b** | AWQ 4bit | ≈ 5 GB | 单 A100 40G 绰绰有余 |
| 备选（仅 Matcher） | Jellyfish-7B | 原精度 | ≈ 14 GB | 论文中模式匹配任务参考 |
| 兜底（无 GPU） | DeepSeek / Qwen 线上 API | — | — | 改 `LLM_BASE_URL` |

> 权重获取：`qwen3.5:9b` 通过 Ollama 或 HuggingFace；若获取困难，`Qwen/Qwen3-8B-AWQ` 为官方替代，`--served-model-name qwen3.5:9b` 保持对外 tag 一致。

### 7.2 统一 LLM 客户端
```python
# adacascade/llm_client.py
from openai import OpenAI
from adacascade.config import settings

_client = OpenAI(
    base_url=settings.LLM_BASE_URL,
    api_key=settings.LLM_API_KEY or "EMPTY",
    timeout=settings.LLM_TIMEOUT,
)

def chat(messages, *, model=None, temperature=0.0, response_format=None, **kw):
    return _client.chat.completions.create(
        model=model or settings.LLM_MODEL,
        messages=messages,
        temperature=temperature,
        response_format=response_format,
        **kw,
    )
```

### 7.3 vLLM 启动脚本
```bash
# scripts/start_llm.sh
#!/usr/bin/env bash
export CUDA_VISIBLE_DEVICES=0              # 独占 A100 #1
vllm serve /path/to/qwen3.5-9b-awq \
    --served-model-name qwen3.5:9b \
    --quantization awq \
    --max-model-len 8192 \
    --gpu-memory-utilization 0.35 \        # 给 SBERT 和其他进程留空间
    --guided-decoding-backend outlines \   # 启用结构化输出后端
    --port 8000
```

### 7.4 LLM 调用约束（JSON Schema 结构化输出）

v2.1 中用的 `response_format={"type": "json_object"}` 只是 JSON Mode，只能保证"输出是合法 JSON"，无法保证"字段名/类型符合预期"。vLLM 0.8.5+ 支持 **JSON Schema 约束解码**（底层通过 outlines 在 token 生成时直接过滤非法 token），可以 100% 保证输出结构。

**用法**：用 Pydantic 定义输出模型，直接用它生成 schema：

```python
# adacascade/agents/matcher.py
from pydantic import BaseModel, Field
from adacascade.llm_client import chat

class MatchResult(BaseModel):
    is_matched: bool = Field(description="源列与目标列是否语义等价")
    confidence: float = Field(ge=0.0, le=1.0, description="置信度")
    scenario: Literal["SMD", "SSD", "SLD"]
    reasoning: str = Field(max_length=500)

def llm_verify(src_col, tgt_col, context) -> MatchResult:
    resp = chat(
        messages=[
            {"role": "system", "content": MATCHER_SYSTEM_PROMPT},
            {"role": "user",   "content": build_prompt(src_col, tgt_col, context)},
        ],
        response_format={
            "type": "json_schema",
            "json_schema": {
                "name": "MatchResult",
                "schema": MatchResult.model_json_schema(),
                "strict": True,
            },
        },
        extra_body={"chat_template_kwargs": {"enable_thinking": False}},
    )
    return MatchResult.model_validate_json(resp.choices[0].message.content)
```

**收益**：
- 彻底删除 JSON 解析失败的 try/except 重试逻辑。
- Pydantic `model_json_schema()` 自动生成，字段变更时 schema 零维护成本。
- `enable_thinking=False` 关闭 Qwen3 的思考模式，判定类任务快一倍。

### 7.5 其他调用约束
- **温度**：所有判定类调用 `temperature=0.0`。
- **超时**：默认 30s；连续 2 次失败则该步骤降级（仅返回 L1+L2 结果，标记 `degraded=true`）。
- **缓存**：L3 LLM 验证结果按 (query_col_hash, cand_col_hash) 缓存 7 天。

---

## 8. 部署与运维

### 8.1 代码与数据目录
```
adacascade/
├── adacascade/
│   ├── agents/                          # planner.py / profiling.py / retrieval.py / matcher.py
│   ├── api/                             # FastAPI 路由 + lifespan
│   ├── db/                              # SQLAlchemy 模型 + 迁移
│   ├── graph/                           # LangGraph 编排
│   ├── indexing/                        # Qdrant 客户端封装
│   ├── ingest/                          # 入库流程 + reconcile
│   ├── artifacts.py                     # 大对象外置工具
│   ├── llm_client.py
│   ├── state.py
│   └── config.py
├── data/                                # 运行时数据（见 §6.4）
├── configs/
│   ├── default.yaml
│   └── prod.yaml
├── scripts/
│   ├── init_db.py                       # 建表
│   ├── init_qdrant.py                   # 建 collection + payload 索引
│   ├── bulk_ingest.py                   # 批量导入
│   ├── gc.py                            # 归档数据清理
│   ├── start_llm.sh
│   ├── start_qdrant.sh
│   └── start_api.sh
├── Dockerfile
├── docker-compose.yml
├── requirements.txt
└── .env.example
```

### 8.2 `requirements.txt` 关键版本
```
fastapi>=0.115
uvicorn[standard]>=0.30
langgraph>=1.1.0
langgraph-checkpoint-sqlite>=2.0.6
langchain-core>=0.3
openai>=1.40
sentence-transformers>=3.0
torch>=2.2                      # SBERT GPU 推理
qdrant-client>=1.10
pandas>=2.2
pyarrow>=16.0
sqlalchemy>=2.0
pydantic>=2.8
pydantic-settings>=2.4
structlog>=24.1
prometheus-fastapi-instrumentator>=7.0
```

### 8.3 启动四步
```bash
# 1) 初始化 SQLite
python scripts/init_db.py

# 2) 启动 Qdrant（docker 一行，持久化到 ./data/qdrant）
bash scripts/start_qdrant.sh
# 等价于：
#   docker run -d --name adac-qdrant \
#     -p 6333:6333 -p 6334:6334 \
#     -v $(pwd)/data/qdrant:/qdrant/storage \
#     qdrant/qdrant:latest

# 3) 初始化 Qdrant collections
python scripts/init_qdrant.py

# 4) 启动 vLLM（独立 screen / tmux / systemd）
bash scripts/start_llm.sh
curl http://localhost:8000/v1/models       # 确认模型在线

# 5) 启动 FastAPI 服务
bash scripts/start_api.sh
# uvicorn adacascade.api.app:app --host 0.0.0.0 --port 8080 --workers 1
```

> **单 worker 原则**：LangGraph 共享状态 + 后台任务队列依赖单进程内存。高并发需求通过加机器 + 前置 Nginx 扩展；若确定要多 worker，见附录 B 的演进路径。

### 8.4 `.env` 示例
```bash
# 服务
APP_HOST=0.0.0.0
APP_PORT=8080

# 数据
DATABASE_URL=sqlite:///data/metadata.db
DATA_DIR=./data
CKPT_PATH=./data/ckpt.db
ARTIFACTS_DIR=./data/artifacts

# 向量存储
QDRANT_URL=http://localhost:6333
QDRANT_COLLECTION_TABLES=tbl_embeddings
QDRANT_COLLECTION_COLUMNS=col_embeddings

# LLM
LLM_BASE_URL=http://localhost:8000/v1
LLM_API_KEY=EMPTY
LLM_MODEL=qwen3.5:9b
LLM_TIMEOUT=30

# SBERT
SBERT_MODEL=sentence-transformers/all-MiniLM-L6-v2
SBERT_DEVICE=cuda:0                         # 从 CPU 切到 GPU
SBERT_BATCH_SIZE=256                        # GPU 上大批次更划算

# TLCF
TLCF_L1_THRESHOLD=0.20
TLCF_L2_TOPK=40
TLCF_L3_TOPK=10
TLCF_WEIGHTS=0.2,0.3,0.5

# Matcher
MATCH_WEIGHTS_SMD=0.7,0.3,0.0
MATCH_WEIGHTS_SSD=0.5,0.3,0.2
MATCH_WEIGHTS_SLD=0.3,0.2,0.5
MATCH_DECISION_THRESHOLD=0.7
MATCH_LLM_TOPN=10                           # §5.2 Top-N 截断
```

### 8.5 Docker Compose
```yaml
services:
  qdrant:
    image: qdrant/qdrant:latest
    ports: ["6333:6333", "6334:6334"]
    volumes: ["./data/qdrant:/qdrant/storage"]
    restart: unless-stopped

  vllm:
    image: vllm/vllm-openai:latest
    command: >
      --model Qwen/Qwen3-8B-AWQ
      --served-model-name qwen3.5:9b
      --quantization awq
      --gpu-memory-utilization 0.35
      --max-model-len 8192
      --guided-decoding-backend outlines
    deploy:
      resources:
        reservations:
          devices: [{ driver: nvidia, count: 1, capabilities: [gpu] }]
    ports: ["8000:8000"]

  adacascade:
    build: .
    env_file: .env
    environment:
      - LLM_BASE_URL=http://vllm:8000/v1
      - QDRANT_URL=http://qdrant:6333
      - SBERT_DEVICE=cuda:0
    volumes: ["./data:/app/data"]
    deploy:
      resources:
        reservations:
          devices: [{ driver: nvidia, count: 1, capabilities: [gpu] }]
    ports: ["8080:8080"]
    depends_on: [vllm, qdrant]
```

### 8.6 可观测性
- **日志**：structlog JSON，强制含 `task_id`，按天切分。
- **指标**：`/metrics` 暴露 Prometheus 指标，核心 `adac_task_latency_seconds`（按 agent/mode 切片）、`adac_llm_tokens_total`、`adac_tlcf_pruning_rate`、`adac_profiling_throughput`。
- **轨迹**：`agent_step` 表记录每步耗时/tokens/recall_loss，直接复现论文图表。

### 8.7 降级与容错
| 故障 | 自动响应 |
|---|---|
| vLLM 不可达 | 环境变量切换 `LLM_BASE_URL` 至线上 API |
| Qdrant 不可达 | 返回 503；Retrieval 降级为仅 L1 （TF-IDF） |
| LLM 单次超时 | 指数回退重试 2 次，失败则该步骤降级 |
| Retrieval L3 全失败 | 跳过 L3，仅用 L1+L2，标记 `degraded=true` |
| SBERT GPU OOM | 自动 fallback 到 CPU（捕获异常后降级推理） |
| FastAPI 进程 crash | 重启时 (1) LangGraph 从 checkpoint 续跑 (2) reconcile 扫描孤儿入库任务 |

---

## 9. 与课题组大系统的集成

### 9.1 集成方式
**只通过 REST API 一种通道**，不引入消息队列，不共享数据库。

| 场景 | 调用 |
|---|---|
| 注册新表 | `POST /tables` 上传 Parquet/CSV → 后台 Profiling |
| 用户主动发起发现 | `POST /discover` |
| 已知源/目标表做匹配 | `POST /match` |
| 全链路集成 | `POST /integrate` |
| 结果回查 | `GET /tasks/{task_id}` |

### 9.2 请求样例

**(a) 上传表**
```http
POST /tables
Content-Type: multipart/form-data

file: <parquet or csv>
metadata: {"table_name": "musician_labels", "source_system": "host_platform"}

→ 202 Accepted
{ "table_id": "a3e8...", "status": "INGESTED" }
```

**(b) 全链路集成**
```http
POST /integrate
{ "query_table_id": "a3e8...", "options": { "top_k": 10 } }

→ 200 OK
{
  "task_id": "f9c1...",
  "status": "SUCCESS",
  "ranking": [{ "table_id": "b7d2...", "score": 0.91,
                "layer_scores": {"l1": 0.42, "l2": 0.73, "l3": 0.93} }],
  "mappings": [{ "src_col": "musicianLabel", "tgt_col": "musicianName",
                 "scenario": "SLD", "confidence": 0.88, "is_matched": true }],
  "degraded": false,
  "latency_ms": 2440
}
```

**(c) 仅匹配**
```http
POST /match
{ "source_table_id": "a3e8...", "target_table_id": "c5f1...",
  "options": { "scenario_hint": "SLD" } }

→ 200 OK
{ "task_id": "...", "status": "SUCCESS", "mappings": [...] }
```

### 9.3 认证与多租户
- 认证：大系统签发 API Key，`Authorization: Bearer <key>`。
- 多租户：Header `X-Tenant-Id` 写入所有存储记录，Qdrant 检索用 payload filter 强制隔离。

### 9.4 版本与向后兼容
API 前缀 `/v1/...`；请求/响应 schema 由 Pydantic 定义，自动导出 OpenAPI schema。

---

## 10. 非功能目标

| 项 | v2.1 目标 | **v2.2 目标（改进后）** | 依据 |
|---|---|---|---|
| `/integrate` P95 延迟（OpenData JOIN, k=10） | ≤ 3.0s | ≤ 2.8s | SBERT GPU + JSON Schema 省重试 |
| `/discover` P95 延迟 | ≤ 2.8s | ≤ 2.5s | 同上 |
| `/match` P95 延迟（SLD, 20 列对） | ≤ 2.0s | ≤ 1.8s | |
| 入湖 Profiling 吞吐 | ≥ 100 张/分钟 | **≥ 1000 张/分钟** | SBERT 从 CPU 移至 GPU |
| 新表从 INGESTED 到 READY | ≤ 30s | ≤ 10s | 同上 |
| 单任务 LLM 调用上限 | ≤ 60 次 | ≤ 60 次 | 论文 TLCF 约束 |
| 服务可用性 | 月 99% | 月 99% | 课题组研究环境 |

---

## 11. 实施路线

| 阶段 | 时间 | 交付 |
|---|---|---|
| M1 骨架 | 2 周 | FastAPI + LangGraph 1.1 + Qdrant + SBERT(GPU) + `/tables` 上传链路跑通 |
| M2 能力 | 3 周 | Profiling + TLCF + 三场景 Matcher + JSON Schema 输出 + Top-N 截断；OpenData/Valentine 复现论文指标（±3%） |
| M3 集成 | 2 周 | 对接大系统 API Key + Tenant 隔离 + reconciliation + 监控；UAT |
| M4 上线 | 1 周 | Docker Compose 打包 + 启动脚本 + 运维文档 |

---

## 附录 A · 关键术语

| 术语 | 含义 |
|---|---|
| AdaCascade | **Ada**ptive + **Cascade**d，本框架名；工程代号 `adac` / `adacascade` |
| TLCF | Three-Layer Cascaded Filtering，三层级联过滤算法 |
| SMD/SSD/SLD | 仅元数据 / 少样本 / 全量数据 三种可用性场景 |
| INGESTED/READY/ARCHIVED | 表格生命周期中的关键状态（§3.3） |
| Checkpoint | LangGraph 的状态持久化快照（SQLite） |
| Reconciliation | 启动时扫描孤儿状态并重新入队的机制（§3.4） |
| Qdrant Collection | Qdrant 中的向量集合，对应 hnswlib 的索引文件 |
| Payload Filter | Qdrant 在检索时按字段过滤的能力，用于租户与状态隔离 |
| JSON Schema 约束解码 | vLLM 通过 outlines 在 token 级强制符合 schema 的解码模式 |

---

## 附录 B · 未来演进路径

本附录收集当前版本**未采纳**但在规模增长时可以无痛升级的路径。每一条都不需要改业务代码，只需改配置或替换依赖。

### B.1 多 Worker 水平扩展
**触发条件**：单机 QPS 无法满足，或出现 CPU-bound 瓶颈。
**升级动作**：
1. LangGraph checkpoint：`AsyncSqliteSaver` → `AsyncPostgresSaver`（改 `CKPT_DSN`）。
2. 元数据库：SQLite → PostgreSQL（改 `DATABASE_URL`）。
3. uvicorn：`--workers 1` → `--workers N`，前置 Nginx 做负载均衡。
4. Qdrant 本身已支持并发读写，无需变更。

### B.2 更强的异步任务保证
**触发条件**：入库任务链路变长（例如加入 DQ 校验、人工标注），需要重试/延时/优先级调度。
**升级动作**：
- 引入 **Taskiq**（async 原生、支持多种 broker），把 `BackgroundTasks` + reconciliation 换成标准任务队列。
- 启动一个独立 worker 进程，用 SQLite 或 Redis 做 broker。

### B.3 大规模向量（千万级以上）
**触发条件**：Qdrant 单节点查询延迟明显上升或磁盘吃紧。
**升级动作**：
- Qdrant 单节点 → Qdrant Cluster（自带的 raft 集群模式），collection 开启 shard。
- 客户端代码零变动。

### B.4 更好的监控与实验追踪
**升级动作**：
- 接入 **LangSmith**（LangGraph 原生支持），获得逐 agent 调用链可视化与 A/B 实验对比能力，对论文图表生成友好。
