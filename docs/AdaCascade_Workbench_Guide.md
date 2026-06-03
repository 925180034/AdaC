# AdaCascade 工作台使用指南

本文面向演示人员、评审老师和首次使用 AdaCascade 的开发者，说明前端工作台每个区域的用途、常见操作流程和排错入口。系统架构与 API 契约以 [`AdaCascade_System_Design.md`](AdaCascade_System_Design.md) 为准；算法公式与默认超参以 [`AdaCascade_Algorithm_Spec.md`](AdaCascade_Algorithm_Spec.md) 为准。

---

## 1. 页面入口

### 1.1 本地 Demo 入口

当前服务器本地 Demo 推荐入口：

```text
http://localhost:6006/?tenant_id=default
```

本地 Demo 通常由前端 Vite 服务监听 `6006`，后端 FastAPI 监听 `6008`，前端通过同源代理转发 `/datasets`、`/tables`、`/tasks`、`/runtime` 等请求到后端。

### 1.2 常用 URL 参数

| 参数 | 示例 | 作用 |
|---|---|---|
| `tenant_id` | `default`、`benchmark` | 指定当前租户。`default` 用于演示数据，`benchmark` 用于基准数据。 |
| `dataset_id` | `benchmark_join` | 指定默认选中的数据集。省略时工作台会选择当前租户下第一个可用数据集。 |
| `mode` | `discover`、`integrate`、`match` | 指定默认运行模式。省略时默认进入 `integrate`。 |
| `query_table_id` | 表 ID | Discover / Integrate 模式下默认选中的查询表。 |
| `source_table_id` | 表 ID | Match 模式下默认选中的源表。 |
| `target_table_id` | 表 ID | Match 模式下默认选中的目标表。 |

常用入口：

```text
# 演示租户
http://localhost:6006/?tenant_id=default

# 基准租户
http://localhost:6006/?tenant_id=benchmark

# 直接进入表发现模式
http://localhost:6006/?tenant_id=default&mode=discover

# 直接进入列匹配模式
http://localhost:6006/?tenant_id=default&mode=match
```

---

## 2. 顶部工具栏

顶部工具栏用于设置工作台显示偏好和模型运行时。

### 2.1 语言切换

- **English**：切换为英文界面。
- **中文**：切换为中文界面。

语言偏好会写入浏览器本地存储，刷新页面后保持上次选择。

### 2.2 主题切换

- **浅色**：适合普通演示和截图。
- **深色**：适合暗光环境或长时间调试。

主题偏好同样保存在浏览器本地。

### 2.3 模型运行时切换

工作台支持两类 LLM 后端：

| 选项 | 含义 | 适用场景 |
|---|---|---|
| **API 模型** | 使用外部 OpenAI-compatible API，例如 DeepSeek | 不想占用本机 GPU、需要快速验证接口链路时使用。 |
| **本地模型** | 使用本机 vLLM 提供的 OpenAI-compatible API | 需要离线、可控或论文演示场景时使用。 |

本地 vLLM 状态区域会显示：

| 状态 | 含义 | 建议操作 |
|---|---|---|
| `未知` | 尚未查询到本地 runtime 状态 | 刷新页面或等待 runtime 查询完成。 |
| `未启动` | 当前没有本地 vLLM 进程处于 ready 状态 | 点击“本地模型”让后端尝试启动，或手动启动 vLLM。 |
| `启动中` | 后端正在启动或探测 vLLM | 等待 `/v1/models` ready。 |
| `已启动` | 本地 vLLM 已 ready，可以执行任务 | 可运行 Discover / Integrate / Match。 |
| `停止中` | 后端正在停止托管的本地 vLLM | 等待状态更新。 |
| `启动失败` | vLLM 进程退出或超时未 ready | 查看 `data/logs/vllm.log`，确认模型路径、端口、量化参数和 GPU 可用性。 |

> 注意：本地非 Docker 运行时，`LLM_MODEL_PATH` 应是宿主机真实路径，例如 `/root/autodl-tmp/models/qwen3-8b-awq`；Docker 部署时才使用容器内路径，例如 `/app/models/Qwen/Qwen3-8B-AWQ`。

---

## 3. 数据集面板

数据集面板用于选择数据集、查看表处理状态，以及创建或上传数据。

### 3.1 数据集选择

下拉框显示当前租户下的 ACTIVE 数据集，格式为：

```text
数据集名称 · ready_count/table_count
```

例如：

```text
agri_demo_lake_final5_1779158754 · 50/50
Benchmark JOIN · 1534/1534
```

如果数据集名称看起来不是预期值，先确认当前 URL 的 `tenant_id` 是否正确，再检查后端 `/datasets` 返回内容和本地 `data/metadata.db` 中的数据集状态。

### 3.2 数据集统计

数据集统计区包含：

| 字段 | 含义 |
|---|---|
| **表** | 当前数据集的表总数。 |
| **就绪** | 已完成 profiling、可参与任务的 READY 表数量。 |
| **处理中** | 前端当前拉取到的 INGESTED / PROFILING 表数量。 |
| **失败** | 后端记录的 FAILED 表数量。 |

运行 Discover / Integrate / Match 前，建议确认“就绪”数量大于 0。

### 3.3 数据集工具

点击“展开数据集工具”后可使用：

- **新建数据集**：创建一个当前租户下的 ACTIVE 数据集。
- **上传表**：上传 CSV、Parquet、Excel 或 ZIP 文件到当前数据集。
- **上传者**：可选元信息，用于标记上传来源。
- **表名前缀**：可选前缀，用于批量上传时区分表名。
- **最近表状态**：显示最近几张表的状态，并可点击预览。

上传成功后，后端会将表写入元数据库和本地 Parquet 存储，并通过 BackgroundTasks 触发 Profiling。处理中表会自动轮询刷新。

### 3.4 表预览

点击表名旁边的预览入口，可以打开表预览弹窗，查看列名、类型、行列规模和样例数据。预览用于确认任务输入是否选对，不会启动算法流程。

---

## 4. 任务控制面板

任务控制面板用于选择租户、执行配置、运行模式和输入表。

### 4.1 租户

默认租户选项：

| 租户 | 用途 |
|---|---|
| `default` | 日常演示和用户上传数据。 |
| `benchmark` | WebTable / matcher benchmark fixtures。 |

切换租户后，工作台会清空当前任务上下文并重新加载数据集与表列表。

### 4.2 执行配置

| 配置 | 含义 | 适用场景 |
|---|---|---|
| **可复现** | 使用论文默认参数和保守并发 | 评审、复现实验、正式对比。 |
| **演示加速** | 开启更高 LLM 并发和缓存友好设置 | 现场演示、快速验证。 |
| **JOIN 召回优化** | 增强列召回和 matcher 并发 | JOIN 场景候选召回不足时使用。 |

执行配置只覆盖运行参数，不修改算法规格中的默认超参定义。

### 4.3 运行模式

| 模式 | API | 输入 | 输出 |
|---|---|---|---|
| **表发现** | `/discover` | 查询表 | 候选表排序、TLCF 分层结果。 |
| **数据集成** | `/integrate` | 查询表 | 候选表排序 + 列级映射。 |
| **模式匹配** | `/match` | 源表 + 目标表 | 两张表之间的列映射结果。 |

### 4.4 高级参数

“展开高级参数”用于临时调整任务参数。常见参数包括 LLM 批大小、LLM 并发、候选截断数量和召回增强设置。除非是演示加速或定位问题，建议保持“可复现”配置。

### 4.5 运行与取消

- **运行 AdaCascade**：在当前输入合法且无任务运行时启用。
- **取消任务**：如果当前任务仍在运行，前端会展示取消入口。

任务启动后，前端会订阅 SSE 事件流；如果 SSE 断开，前端会回退到 `GET /tasks/{task_id}` 轮询，直到任务进入终态。

---

## 5. 结果工作区

结果工作区展示任务的主要输出。如果没有活跃任务，会显示占位说明。

任务完成后通常包含：

- **流程图 / 状态概览**：展示 Planner、Profiling、Retrieval、Matcher 的执行状态。
- **候选排序**：Discover / Integrate 模式下展示候选表、分数和层级过滤信息。
- **列映射结果**：Match / Integrate 模式下展示源列到目标列的映射、置信度和场景判断。
- **原始 JSON**：用于开发调试、论文复现实验和 API 输出核对。

结果工作区的表预览入口可用于回看候选表或匹配表的原始数据。

---

## 6. 四智能体执行面板

四智能体执行面板实时展示 AdaCascade workflow 的阶段状态。

### 6.1 Planner

Planner 负责解析任务模式和输入，决定使用 Discover、Match 或 Integrate 路由，并生成下游 Agent 所需的运行计划。

### 6.2 Profiling

Profiling 负责抽取表级、列级、文本、结构和统计特征，并将向量写入 Qdrant。上传新表后必须完成 Profiling，表才会进入 READY 状态。

### 6.3 Retrieval

Retrieval 负责三层级联过滤：

1. **L1**：TF-IDF + Jaccard 粗召回；
2. **L2**：Qdrant 向量召回，并与 L1 结果取交集；
3. **L3**：LLM 批处理验证候选表；
4. **Aggregate**：归一化并聚合分数，得到候选表排序。

### 6.4 Matcher

Matcher 负责列级匹配：

1. 计算文本、结构和统计相似度；
2. 按 SMD / SSD / SLD 场景权重混合；
3. 对每个源列截断 top-N 候选列；
4. 调用 LLM 做结构化判定；
5. 输出最终列映射，必要时应用 1:1 约束。

### 6.5 最近事件

最近事件日志显示 SSE 推送的任务事件，用于确认任务是否仍在运行、是否已经完成，以及哪个 Agent 正在执行。

---

## 7. 常见使用流程

### 7.1 用 API 模型运行一次 Integrate

1. 打开：

   ```text
   http://localhost:6006/?tenant_id=default
   ```

2. 顶部模型运行时选择 **API 模型**。
3. 在数据集面板选择一个 READY 表数量大于 0 的数据集。
4. 任务控制面板选择：
   - 执行配置：`可复现`；
   - 模式：`数据集成`；
   - 查询表：选择一个演示表。
5. 点击 **运行 AdaCascade**。
6. 在结果工作区查看候选排序和列映射。

### 7.2 切换本地模型运行

1. 确认当前运行方式：
   - 本地非 Docker：`LLM_MODEL_PATH` 必须是宿主机真实路径。
   - Docker 部署：`LLM_MODEL_PATH` 通常是容器内挂载路径。
2. 顶部模型运行时点击 **本地模型**。
3. 等待本地 vLLM 状态变为 **已启动**。
4. 再运行 Discover / Integrate / Match。

本地服务器常用环境变量示例：

```bash
export LLM_MODEL_PATH=/root/autodl-tmp/models/qwen3-8b-awq
export LLM_LOCAL_BASE_URL=http://localhost:8001/v1
export LLM_LOCAL_PORT=8001
export LLM_LOCAL_MODEL=qwen3:8b
export VLLM_QUANTIZATION=awq
```

### 7.3 使用 benchmark 数据集

打开：

```text
http://localhost:6006/?tenant_id=benchmark
```

可选数据集包括：

- `Benchmark JOIN`
- `Benchmark UNION`
- `Matcher MIMIC-OMOP`
- `Matcher Wikidata`

benchmark 数据量较大，正式运行前应确认当前模型后端、缓存状态和执行配置。

### 7.4 上传自己的数据

1. 在 `default` 租户中新建数据集，或选择已有数据集。
2. 展开数据集工具。
3. 上传 CSV、Parquet、Excel 或 ZIP。
4. 等待表状态进入 READY。
5. 如需提升 Discover / Integrate 的 TF-IDF 召回稳定性，上传后运行：

   ```bash
   python scripts/rebuild_tfidf.py --tenant-id default --corpus all
   ```

6. 回到工作台刷新数据集和表列表。

---

## 8. 常见问题

### 8.1 数据集显示不符合预期

检查顺序：

1. URL 中的 `tenant_id` 是否正确；
2. 是否传入了错误的 `dataset_id`；
3. 后端 `/datasets` 返回的 ACTIVE 数据集是否符合预期；
4. 本地 `data/metadata.db` 中旧演示数据集是否被归档为 `ARCHIVED`；
5. 上传或归档后是否刷新了页面。

### 8.2 本地模型启动失败

前端常见提示：

```text
启动失败：Local vLLM exited before becoming ready
```

优先检查：

1. `data/logs/vllm.log` 中的真实错误；
2. `LLM_MODEL_PATH` 是否是当前运行环境可见的真实路径；
3. `LLM_LOCAL_PORT` 是否被占用；
4. AWQ 模型是否设置 `VLLM_QUANTIZATION=awq`；
5. 是否错误使用了 Docker 容器路径 `/app/models/...` 来启动宿主机 vLLM；
6. Qwen3 判断类任务是否保持 thinking 关闭。

### 8.3 API 模型可运行，但本地模型失败

这通常说明业务流程和前端没有问题，问题集中在本地 vLLM runtime：

- API 模型由外部服务提供，不依赖本机模型路径和 GPU；
- 本地模型需要当前服务器能访问模型目录、GPU、vLLM 环境和端口；
- 本地非 Docker 与 Docker 部署的路径含义不同，不能混用。

### 8.4 SSE 断开后任务是否还在跑

如果任务仍在后端运行，前端会在 SSE 异常断开后自动轮询 `GET /tasks/{task_id}`。如果页面短暂显示连接错误，可以等待任务状态刷新，或直接在任务详情接口检查状态。

### 8.5 修改配置后为什么没有生效

- 本地脚本启动：需要停止并重新启动对应进程。
- Docker Compose：修改 `.env` 或 Compose 环境变量后，使用 `docker compose up -d` 重新创建受影响容器；不要只执行 `docker compose restart`。
- 前端构建参数：以 `VITE_` 开头的变量通常在构建时嵌入，修改后需要重新构建 frontend。

---

## 9. 相关文档

- [`../README.md`](../README.md)：项目入口、快速开始和文档导航。
- [`M4_Operations_Guide.md`](M4_Operations_Guide.md)：本地 demo、运行时切换和运维操作。
- [`frontend_demo_design.md`](frontend_demo_design.md)：前端工作台设计说明。
- [`../deploy/README.md`](../deploy/README.md)：Docker Compose 部署指南。
- [`../deploy/LAB_SERVER.md`](../deploy/LAB_SERVER.md)：课题组服务器环境约束。
