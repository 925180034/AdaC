# AdaCascade

AdaCascade（**Ada**ptive scenario matching + **Cascade**d filtering）是一个面向数据湖表发现与列级模式匹配的单体应用。系统用 FastAPI + LangGraph 编排 Planner / Profiling / Retrieval / Matcher 四个智能体，通过三层级联过滤（TLCF）和多场景自适应模式匹配（SMD / SSD / SLD）完成候选表发现、列对齐和数据集成任务。

本仓库同时包含：

- Python 后端服务（FastAPI、LangGraph、SQLite、Qdrant、SBERT、OpenAI-compatible LLM 客户端）；
- React + Vite 前端工作台；
- 本地开发脚本、Docker Compose 部署配置、部署服务器档案；
- 系统设计、算法规格、运维与 demo 数据说明文档。

> 算法公式、默认超参与提示词模板以 [`docs/AdaCascade_Algorithm_Spec.md`](docs/AdaCascade_Algorithm_Spec.md) 为准；工程架构、API、部署和数据布局以 [`docs/AdaCascade_System_Design.md`](docs/AdaCascade_System_Design.md) 为准。

---

## 1. 功能概览

| 模式 | API | 目标 | 典型输出 |
|---|---|---|---|
| 表发现 | `/discover` | 从数据湖中找出与查询表相关的候选表 | 候选表排序、TLCF 层级分数 |
| 模式匹配 | `/match` | 在给定源表和目标表之间执行列级匹配 | 列映射、场景标签、置信度 |
| 数据集成 | `/integrate` | 先做候选表发现，再做列级对齐 | 候选排序 + 最终列映射 |

四个智能体的职责：

1. **Planner**：解析任务并选择 discover / match / integrate 路由；
2. **Profiling**：抽取表级、列级、统计与文本特征；
3. **Retrieval**：通过 TLCF L1/L2/L3 逐层缩小候选表范围；
4. **Matcher**：计算混合相似度、截断候选列对、调用 LLM 复核并输出最终映射。

---

## 2. 架构概览

```text
React Workbench
  └─ Nginx / Vite proxy
      └─ FastAPI backend（单 worker）
          ├─ LangGraph workflow
          ├─ SQLite metadata + checkpoint
          ├─ Qdrant table/column embeddings
          ├─ Sentence-BERT profiling/indexing
          └─ OpenAI-compatible LLM runtime
                ├─ local vLLM
                └─ external API backend
```

核心原则：

- 后端保持单体服务，不拆分微服务；
- FastAPI 必须使用 **单 worker**，不要把 `--workers 1` 改成多 worker；
- Qdrant 是向量存储，SQLite 是默认元数据库；
- 大对象制品（例如相似度矩阵、TF-IDF pickle）放在 `data/artifacts/` 或部署运行时目录；
- LLM 支持本地 vLLM 与外部 OpenAI-compatible API 后端切换。

---

## 3. 目录结构

| 路径 | 说明 |
|---|---|
| `adacascade/` | Python 后端包：API、agents、graph、ingest、indexing、DB、LLM runtime |
| `frontend/` | React + Vite 前端工作台 |
| `scripts/` | 初始化、启动、demo、批量导入、TF-IDF 重建脚本 |
| `configs/default.yaml` | 默认配置与运行时参数 |
| `docker-compose.yml` | Docker Compose 部署入口 |
| `Dockerfile.backend` | 后端镜像构建文件 |
| `requirements.txt` | 本地/完整开发依赖，包括 vLLM 栈 |
| `requirements.backend.txt` | Docker 后端依赖，不重复安装本地 vLLM/Torch pin stack |
| `docs/` | 系统设计、算法规格、运维和前端设计文档 |
| `deploy/` | Docker 部署指南、Nginx 配置、实验室服务器档案 |
| `demo_data/agri_lake/` | 农业 demo 数据与使用说明 |
| `tests/` | 单元测试、集成测试、fixtures 和复现实验测试 |

---

## 4. 本地开发快速开始（非 Docker）

本流程适合本地开发、调试和 demo。部署服务器上的 Docker Compose 流程见 [`deploy/README.md`](deploy/README.md)。

### 4.1 初始化 SQLite 元数据库

```bash
python scripts/init_db.py
```

### 4.2 启动本地 Qdrant

```bash
bash scripts/start_qdrant.sh
NO_PROXY=localhost,127.0.0.1 python scripts/init_qdrant.py
```

Qdrant 本地默认端口：

- HTTP: `6333`
- gRPC: `6334`

### 4.3 启动本地 vLLM（可选）

如果使用本地模型后端：

```bash
bash scripts/start_llm.sh
curl --noproxy '*' http://localhost:8000/v1/models
```

如果使用外部 API 后端，可通过运行时切换接口或前端模型切换控件选择 API 模型。

### 4.4 启动 FastAPI 后端

```bash
NO_PROXY=localhost,127.0.0.1 bash scripts/start_api.sh
```

或直接运行：

```bash
NO_PROXY=localhost,127.0.0.1 uvicorn adacascade.api.app:app --host 0.0.0.0 --port 8080 --workers 1
```

> 必须保持 `--workers 1`。LangGraph 状态、BackgroundTasks、LLM runtime manager 和本地 vLLM idle monitor 都依赖单进程内存状态。

### 4.5 启动前端开发服务

```bash
npm --prefix frontend install
npm --prefix frontend run dev
```

Vite 默认开发端口为 `5173`。`scripts/start_demo.sh` 会使用本地 demo API 端口 `6008` 和 Vite 代理流程。

---

## 5. 端口表

| 端口 | 场景 | 服务 |
|---:|---|---|
| `8080` | 本地/容器内部 | FastAPI backend |
| `6008` | 本地 demo | demo FastAPI backend，供 Vite 代理使用 |
| `6333` | 本地 Qdrant | Qdrant HTTP API |
| `6334` | 本地 Qdrant | Qdrant gRPC |
| `8000` | 本地 LLM | vLLM OpenAI-compatible API |
| `5173` | 本地前端 | Vite dev server |
| `13000` | Docker 部署 | Nginx + React 前端宿主机端口 |

---

## 6. LLM 运行时

AdaCascade 支持本地 vLLM 与外部 OpenAI-compatible API 后端。前端模型切换区域会显示当前后端和本地 vLLM 状态。

| 场景 | 典型地址 | 启动方式 | 说明 |
|---|---|---|---|
| 本地 vLLM | `http://localhost:8000/v1` | `bash scripts/start_llm.sh` | 适合本地模型调试；切换到本地时会等待模型 ready |
| 外部 API | 由部署本地配置提供 | 不由本仓库启动 | 可接 DeepSeek 或其他 OpenAI-compatible 服务 |
| Docker 部署 | `http://host.docker.internal:8000/v1` 或外部 API 地址 | 由 `.env` 指定 | Compose 不默认启动 vLLM 服务，后端连接已配置 endpoint |

本地 vLLM runtime manager 的默认行为：

- 切换到 local 时：若本地 vLLM 未 ready，会启动并轮询 `/v1/models`；
- 切换到 api 时：会停止由 AdaCascade manager 托管启动的本地 vLLM；
- 本地 vLLM 无请求超过默认 `900s` 后会自动 idle stop；
- 前端会显示 `未知 / 未启动 / 启动中 / 已启动 / 停止中 / 启动失败` 等本地 vLLM 状态。

---

## 7. Docker Compose 部署入口

Docker 部署使用仓库根目录的 [`docker-compose.yml`](docker-compose.yml)，包含三个服务：

- `qdrant`：私有 Compose 网络中的向量数据库；
- `backend`：FastAPI + LangGraph 后端；
- `frontend`：React 静态资源 + Nginx，默认发布到宿主机 `13000` 端口。

基础流程：

```bash
docker compose config
docker compose build
docker compose up -d qdrant
docker compose run --rm backend python scripts/init_db.py
docker compose run --rm backend python scripts/init_qdrant.py
docker compose up -d
```

完整部署说明见 [`deploy/README.md`](deploy/README.md)。课题组实验室服务器环境约束见 [`deploy/LAB_SERVER.md`](deploy/LAB_SERVER.md)。

---

## 8. Demo 数据

农业 demo 数据说明见 [`demo_data/agri_lake/README.md`](demo_data/agri_lake/README.md)。常用试用方式：

- Discover：以 `research_projects` 作为查询表执行表发现；
- Match：比较 `farmers` 与 `farm_workers` 的列级匹配；
- Integrate：以 `livestock_herds` 作为查询表执行数据集成。

上传或批量导入数据后，运行 Discover / Integrate 前建议显式重建 TF-IDF：

```bash
python scripts/rebuild_tfidf.py --tenant-id default --corpus all
```

Docker 部署中使用：

```bash
docker compose run --rm backend python scripts/rebuild_tfidf.py --tenant-id default --corpus all
```

---

## 9. 验证命令

后端与算法：

```bash
pytest tests/unit/
pytest tests/integration/
mypy --strict adacascade/
ruff check adacascade/
```

前端：

```bash
npm --prefix frontend run lint
npm --prefix frontend run test -- --run
npm --prefix frontend run build
```

部署配置：

```bash
docker compose --ansi never config --no-interpolate
```

健康检查：

```bash
curl http://localhost:8080/healthz
curl --noproxy '*' http://localhost:8000/v1/models  # 仅本地 vLLM 场景
```

---

## 10. 安全与配置

- 真实 `.env` 只能保存在本地开发机或部署服务器，不能提交到 git；
- API token、外部 LLM 凭据、代理凭据等敏感信息不要写入 README、部署文档或提交记录；
- 前端 demo 构建会嵌入与后端一致的 bearer token，生产或公网环境必须使用部署本地强令牌并重新构建 frontend；
- 访问 localhost 服务时，如宿主机设置了代理，请使用 `NO_PROXY=localhost,127.0.0.1` 或 `curl --noproxy '*'`。

---

## 11. 文档导航

| 文档 | 用途 |
|---|---|
| [`docs/README.md`](docs/README.md) | 文档索引与推荐阅读路径 |
| [`docs/AdaCascade_System_Design.md`](docs/AdaCascade_System_Design.md) | 工程架构、API、数据库、部署与目录结构 |
| [`docs/AdaCascade_Algorithm_Spec.md`](docs/AdaCascade_Algorithm_Spec.md) | 算法公式、默认超参、提示词、JSON Schema 与测试指标 |
| [`docs/M4_Operations_Guide.md`](docs/M4_Operations_Guide.md) | 本地 demo / 运维操作指南 |
| [`docs/frontend_demo_design.md`](docs/frontend_demo_design.md) | 前端工作台设计说明 |
| [`deploy/README.md`](deploy/README.md) | Docker Compose 通用部署指南 |
| [`deploy/LAB_SERVER.md`](deploy/LAB_SERVER.md) | 课题组实验室服务器档案与约束 |
| [`demo_data/agri_lake/README.md`](demo_data/agri_lake/README.md) | 农业 demo 数据集说明 |
