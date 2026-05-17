# 代码审查处理记录

日期：2026-05-14

本文记录本轮代码仓库审查后的处理决策。目标不是逐条机械应用审查意见，而是区分：可以直接修复的确定问题、需要结合当前研究/demo 场景区别处理的问题，以及暂时记录为 known issues 的生产化风险。

## 处理原则

1. 以 `CLAUDE.md`、`docs/AdaCascade_System_Design.md`、`docs/AdaCascade_Algorithm_Spec.md` 为裁决依据。
2. 对明确违反验收线或与现有实现直接矛盾的问题，直接修复。
3. 对涉及算法质量、工程折中、部署边界的问题，先记录决策，不做会引入更大架构风险的机械修改。
4. 对当前研究/demo 环境可接受、但生产部署前必须处理的问题，记录为 known issues。

## 可以严格按审查意见修改的事项

### P0：修复 mypy 8 个错误

结论：必须修复，没有争议。

原因：`CLAUDE.md` 明确要求 `mypy --strict adacascade/` 通过，且本轮审查发现的错误文件和行号均能对上当前实现。

处理要求：

- 修复全部 mypy strict 错误。
- 修复后重新运行 `mypy --strict adacascade/`。
- 不通过时不得把 M2/M3/M4/M5 的工程验收标记为通过。

### L2 degraded 标记 bug

结论：可以直接修复。

当前问题：`search_and_build_c2()` 在 fallback 之后再判断 `degraded`。fallback 后 `len(c2)` 可能已经达到 3，因此降级状态不会被记录。

正确处理：

- 在执行 fallback 之前先判断是否需要降级。
- fallback 执行后仍保留该 degraded 标记。
- 补充单元测试，覆盖 fallback 发生时 `degraded=True`。

依据：算法规格 §3.3 要求 fallback 时标记降级。

### TODO.md 状态修正

结论：可以直接修正。

需要修正的状态：

- `mypy --strict adacascade/` 通过：当前不准确，应改为未完成或注明当前已失效。
- 论文复现 benchmark：需要区分 benchmark runner/smoke 已完成，与论文指标验收未完成。
- 前端 lint：当前 `npm run lint` exit 0，但存在 warning；是否算通过取决于项目对“通过”的定义，TODO 需明确。

### 前端 API 默认地址冲突

结论：可以修改。

当前问题：`frontend/src/api/client.ts` 默认 `http://localhost:8080`，会绕过 Vite same-origin proxy；而 demo proxy 目标是 `localhost:6008`。

处理方向：

- demo 默认应走 same-origin proxy，避免公网访问时浏览器直接请求本机 `localhost`。
- `frontend/src/api/client.ts` 的 fallback 表示“没有任何 env 时”的运行行为；`.env.example` 中的 `VITE_API_BASE_URL=http://localhost:8080` 表示直接访问后端的文档示例，两者角色不同。
- 如果只修改 `client.ts` fallback，则 `.env.example` 需要同步说明：直接访问后端时必须显式设置 `VITE_API_BASE_URL`；demo same-origin proxy 模式应将其留空或不设置。
- `VITE_API_BASE_URL` 可继续作为显式覆盖项。
- 修改后运行前端 unit tests、build 和必要的浏览器 demo 验证。

## 需要区别对待的问题

### Planner 在 Profiling 之前导致 UNION 不生效

审查判断：方向上成立，但不能简单调换 planner/profiling 顺序。

不建议的修复：把 Profiling 放到 Planner 之前。

原因：

- Profiling 是重操作，包含 SBERT 编码与 Qdrant upsert。
- 把 Profiling 前置会让所有任务都先付出重成本，破坏 Planner 先路由的设计意图。
- 现有设计应保留轻量 planner 路由路径。

应采取的处理：

1. 查 `adacascade/api/routes/` 中各操作路由的初始 state 构造，确认请求体的 `user_hint` 是否写入 `state["plan"]["user_hint"]`。
2. 若未透传，则补充 user_hint 透传。
3. 文档/TODO 中说明：无 hint 且无显著主键特征时，默认 JOIN 是当前设计选择，而不是必须通过重 Profiling 才能判断的 bug。
4. 不通过调换 LangGraph 节点顺序来解决该问题。

### L3 batch_size 硬限为 1

审查判断：指出了延迟问题，但不能简单改回 10。

背景：当前本地 vLLM 常用 `VLLM_MAX_MODEL_LEN=4096`。多候选 L3 prompt 会带列名、类型、样本值，容易触发 context overflow。

不建议的修复：直接把 `_LLM_CANDIDATES_PER_CALL` 改回 10。

应采取的处理：

- 将每次 LLM 调用的候选数配置化。
- 默认值可以继续适配当前 local 4096 context，例如设为 1。
- 在 TODO 和注释中说明：local 4096 context 下当前按单候选调用；A100、更大 context 或更短 prompt 时可以调高。
- benchmark 报告应记录该配置，避免把工程 profile 与论文默认配置混淆。

### L2 fallback 范围与算法规格偏差

审查判断：规格层面成立，但不作为立即机械修复。

当前实现：fallback 仅在 `C1` 内选 top-3。

算法规格：fallback 应从 `W ∪ C1` 中放宽选取。

暂不直接修改的原因：

- `k2=40`、`k1=120` 下，`W` 中不在 `C1` 的候选通常在 L1 lexical 分数上较弱。
- 直接引入这类低 S1 候选可能降低质量，尤其是 JOIN 低召回已知存在排序噪声问题。
- 该修改涉及质量/召回/延迟取舍，不是纯 bugfix。

处理决策：

- 先修复 degraded 标记。
- 将 fallback 范围问题记录为“与算法规格 §3.3 的已知偏差”。
- 后续通过 benchmark 对比 `C1-only fallback` 与 `W ∪ C1 fallback`，再决定是否调整默认行为。

### 租户隔离

审查判断：生产场景有效，但当前不作为阻塞项。

当前边界：内部研究/demo 环境中使用 bearer token + 客户端传 `X-Tenant-Id` 的简化方案。

处理决策：

- 当前阶段不立即改成完整多租户鉴权体系。
- 记录为 known limitation。
- 对接课题组大系统或公网部署前，必须由可信上游注入 tenant，或引入 API key 与 tenant 的绑定校验。

### 上传无大小限制

审查判断：生产场景有效，但当前不作为阻塞项。

当前边界：内部工具与受控数据集场景下风险可控。

处理决策：

- 不作为当前 P0/P1 阻塞项。
- 记录为 M6 after / production hardening 项。
- 后续补充上传文件大小限制、行列上限、解析超时或流式处理策略。

## Known issues

以下问题本轮不立即修改，但需要记录并在后续版本处理：

1. L2 fallback 当前是 `C1-only`，与算法规格 §3.3 的 `W ∪ C1` 有偏差；需 benchmark 决策。
2. 当前租户隔离依赖内部研究/demo 假设；生产部署前需可信 tenant 注入或 API key-tenant 绑定。
3. 上传接口缺少文件大小、行数、列数和解析资源限制；生产部署前需补。
4. L3 单候选调用是 local 4096 context 下的工程折中；更大 context 环境应重新评估批大小。
5. 论文复现 benchmark 当前仍是 runner/smoke 层面，尚未完成论文指标验收。

## 建议执行顺序

1. 修复 mypy 8 个错误，恢复 `mypy --strict adacascade/` 验收线。
2. 修复 L2 degraded 标记 bug，并补单元测试。
3. 更新 `TODO.md`，避免 mypy、benchmark、lint 状态继续误导。
4. 将 L3 batch size 配置化，并在 TODO/注释中说明 local 4096 context 下默认设为 1。
5. 查 API 路由的初始 state 构造，确认 `user_hint` 是否透传到 `state["plan"]["user_hint"]`；若未透传则补充，并说明默认 JOIN 的设计边界。
6. 按需修复前端 API 默认地址与 lint warning；若修改 `client.ts` fallback，同步澄清 `.env.example` 的直接访问示例角色。
7. 将 L2 fallback 范围、租户隔离、上传限流保留为 known issues，不在当前轮次中强行修改。

## 验收建议

完成前 6 项后至少运行：

```bash
mypy --strict adacascade/
ruff check adacascade/ tests/ scripts/
pytest tests/unit/ -q
pytest tests/integration/ -q
npm --prefix frontend run lint
npm --prefix frontend run test -- --run
npm --prefix frontend run build
```

若涉及前端 API base URL 行为，还需要通过浏览器实际验证 same-origin proxy demo 流程。