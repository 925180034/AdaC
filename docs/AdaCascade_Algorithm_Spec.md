# AdaCascade · 算法规格文档

> **配套文档**：本文档与 `AdaCascade_System_Design.md` 互补使用。
> - 系统设计文档回答「**代码放哪、服务怎么部署、API 长什么样**」
> - 本算法规格文档回答「**每个 Agent 内部的计算细节、公式、默认参数、提示词模板**」
>
> Claude Code 开发时的权威裁决规则：
> - 工程细节与系统设计文档冲突 → 以系统设计文档为准
> - 算法细节与本文档冲突 → 以本文档为准
> - 两者都未涉及 → 先问，不要编

---

## 0. 符号约定

所有 Agent 共享下述统一符号。代码实现时应用完全一致的命名（`table_id`、`col_id`、`vec_tfidf` 等）。

| 符号 | 含义 |
|---|---|
| D = {T₁, ..., Tₙ} | 数据湖的表集合 |
| Tq, Tc | 查询表、候选表 |
| Tq, Tt | 源表、目标表（独立匹配模式专用） |
| A(T) = {a₁, ..., aₘ} | 表 T 的列集合 |
| a.name, a.type, a.desc | 列的名称、数据类型、描述 |
| V(a) = {v₁, ..., vₖ} | 列 a 的实例值集合 |
| τ ∈ {JOIN, UNION} | 数据发现任务类型 |
| e_T, e_a ∈ ℝᵈ | 表级、列级 SBERT 向量，d = 384 |
| v_tfidf(T) | 表 T 的 TF-IDF 稀疏向量 |
| Sim(x, y) ∈ [0, 1] | 统一相似度函数，越大越相似 |
| Sₗ, Cₗ, wₗ | TLCF 第 l 层的得分、候选集、聚合权重 |
| θ₁, θ₂, θ₃ | TLCF 三层阈值 |
| k₁, k₂ | TLCF 第 1/2 层候选截断数 |
| λ_text, λ_struct, λ_stat | Matcher 三类特征权重（场景自适应） |
| θ_cand, θ_match | Matcher 候选召回阈值、最终匹配判定阈值 |
| Rconf ∈ [0, 1] | LLM 输出的连续置信度得分 |

---

## 1. PlannerAgent · 意图识别与策略生成

### 1.1 输入 / 输出
**输入**：
- `task_source`：`"integrate" | "discover" | "match"`（由 API 端点决定，直接透传）
- `Tq`：查询表的 manifest（列名、类型、行数、前 3 行样本）
- 可选 `Tt`：目标表 manifest（仅 `match` 端点有）
- 可选 `user_hint`：用户自然语言提示

**输出写入 state**：
- `task_type` ∈ `{INTEGRATE, DISCOVER_ONLY, MATCH_ONLY}`
- `subtask` ∈ `{JOIN, UNION}`（仅当 task_type ≠ MATCH_ONLY 时）
- `plan`：见 §1.3

### 1.2 task_type 决策规则（不走 LLM，代码判断）

```python
def decide_task_type(task_source: str) -> TaskType:
    return {
        "match":     "MATCH_ONLY",
        "discover":  "DISCOVER_ONLY",
        "integrate": "INTEGRATE",
    }[task_source]
```

API 端点已经明确携带意图，这一步**不需要 LLM**。LLM 只用于下一步判断 `subtask`（JOIN/UNION）。

### 1.3 subtask（JOIN vs UNION）的 LLM 识别

**启发式快捷路径**（命中任何一条直接返回，不走 LLM）：
- 用户 hint 中显式出现 `"join"`/`"关联"`/`"连接"`/`"扩充属性"` → **JOIN**
- 用户 hint 中显式出现 `"union"`/`"合并"`/`"追加"`/`"并集"` → **UNION**
- 查询表有 ≥1 列 `distinct_ratio > 0.95` 且 `col_type ∈ {int, str}` → **JOIN**（疑似主键）

**LLM 路径**（上述都不命中时才调用）：

```text
[System]
你是数据集成领域的规划助手。你的任务是判断用户希望对一张查询表执行哪种数据发现任务。

[Task]
给定一张查询表的元数据与前几行样本，判断用户意图是：
- JOIN：横向扩充——从数据湖中找与本表存在连接键的表，以扩充属性
- UNION：纵向扩充——从数据湖中找描述同一类实体、结构兼容的表，以追加记录

[Query Table]
name: {Tq.name}
columns: [{col_name}:{col_type} for col in Tq.columns]
sample_rows: {Tq.sample_rows[:3]}
user_hint: {user_hint or "(none)"}

[Output, JSON only]
{"subtask": "JOIN" | "UNION", "reason": "<20字以内>"}
```

**响应用 JSON Schema 约束**（`PlannerDecision` Pydantic model），详见 §7。

### 1.4 plan 的生成（确定性映射，不走 LLM）

根据 `subtask` 查表生成 plan，**这些都是论文 §3 实验验证过的默认值，不要改**：

```python
DEFAULT_PLANS = {
    "JOIN": {
        # TLCF 各层阈值
        "theta_1": 0.20,   # 论文 §3.6.4 敏感性分析肘部
        "theta_2": 0.55,   # 向量余弦阈值，经验值
        "theta_3": 0.50,   # LLM 置信度阈值
        # 各层截断数
        "k_1":     120,    # 论文表 3-3
        "k_2":     40,     # 论文 §3.6.4 收益递减点
        # 聚合权重
        "w_1": 0.2, "w_2": 0.3, "w_3": 0.5,   # 论文公式 3-13
    },
    "UNION": {
        "theta_1": 0.20,
        "theta_2": 0.55,
        "theta_3": 0.50,
        "k_1":     120,
        "k_2":     40,
        "w_1": 0.4, "w_2": 0.4, "w_3": 0.2,   # UNION 更看重全局语义
    },
}
```

---

## 2. ProfilingAgent · 特征提取与持久化

ProfilingAgent 同时支持**离线入湖调用**（§3 的表格生命周期）与**在线任务内调用**（作为图节点被触发）。两条路径复用同一套特征提取代码。

### 2.1 特征画像 Φ(T) 的完整结构

对任一表 T，Profile 包含：

```python
@dataclass
class TableProfile:
    table_id: str
    # 文本层（供 L1）
    text_blob: str                      # 拼接"表名 + 每列 name + desc"
    tfidf_vec_ref: str                  # 稀疏向量 id，存 SQLite（BLOB）
    # 语义层（供 L2）
    table_emb_ref: str                  # Qdrant point id（tbl_embeddings collection）
    # 结构层（供 L1 + Matcher）
    type_multiset: list[str]            # 列类型多重集，如 ["int","str","str","float"]
    # 列级画像
    columns: list[ColumnProfile]

@dataclass
class ColumnProfile:
    col_id: str
    ordinal: int
    name: str
    dtype: Literal["int","float","str","date","bool"]
    description: str | None
    null_ratio: float
    distinct_ratio: float
    # 统计特征（供 Matcher SSD/SLD）
    numeric_stats: NumericStats | None   # 仅 int/float/date
    categorical_stats: CatStats | None   # 仅 str/bool
    # 列级语义向量（供 Matcher、L2 按列检索）
    col_emb_ref: str                     # Qdrant point id（col_embeddings collection）
    # 样本值（供 SSD LLM prompt）
    sample_values: list[str]             # 至多 5 条

@dataclass
class NumericStats:
    mean: float
    std: float
    q25: float
    q50: float
    q75: float

@dataclass
class CatStats:
    top_k: list[tuple[str, float]]       # [(value, freq_norm), ...]，k ≤ 20
    freq_vector_ref: str                  # 归一化后的频率向量（用于 Sim_dist, §4.2.3）
```

### 2.2 text_blob 拼接规则（供 TF-IDF）

```python
def build_text_blob(table: Table) -> str:
    parts = [table.name]
    for col in table.columns:
        parts.append(col.name)
        if col.description:
            parts.append(col.description)
    return " ".join(parts).lower()
```

**TF-IDF 的训练语料**：全库所有表的 text_blob。采用 `sklearn.feature_extraction.text.TfidfVectorizer`，参数：
```python
TfidfVectorizer(
    lowercase=True,
    token_pattern=r"(?u)\b\w+\b",
    ngram_range=(1, 1),
    min_df=2,
    max_df=0.9,
    sublinear_tf=True,
)
```
**vocabulary 持久化**：vectorizer 训练后 pickle 到 `data/artifacts/tfidf.pkl`；新表入湖时**只 transform**，不重训。当累积入湖表数增长 ≥ 50% 时触发一次全量重训（由 `scripts/rebuild_tfidf.py` 执行）。

### 2.3 SBERT 编码的输入文本构造

**表级向量 e_T**（写入 `tbl_embeddings`）：
```python
table_input = f"Table: {table.name}. Columns: " + ", ".join(
    f"{c.name} ({c.dtype})" + (f" - {c.description}" if c.description else "")
    for c in table.columns
)
```

**列级向量 e_a**（写入 `col_embeddings`）：
```python
col_input = f"Column {col.name} of type {col.dtype}" + (
    f". Description: {col.description}" if col.description else ""
) + f". In table {table.name}."
```

**GPU 批处理**：用 `SentenceTransformer.encode(texts, batch_size=256, device="cuda:0", normalize_embeddings=True)`，归一化后存入 Qdrant（Qdrant 配置 Cosine 距离与归一化向量等价于内积，速度更快）。

### 2.4 统计特征计算公式

**数值型列**（论文 §2.1.1）：
- 均值：μ = (1/k) · Σvᵢ
- 标准差：σ = √((1/k) · Σ(vᵢ-μ)²)
- 分位数：q₂₅, q₅₀, q₇₅ 用 `numpy.percentile(v, [25, 50, 75], method='linear')`

**日期列**：转 Unix 时间戳后按数值型处理。

**类别/字符串列**：
- top_k：value_counts().head(20)，归一化除以总行数
- freq_vector：与全库 top-K 词汇表对齐的稀疏频率向量（供 §4.2.3 `Sim_dist` 余弦相似度）。词汇表固定为出现次数 ≥ 5 的 token，持久化到 `data/artifacts/cat_vocab.pkl`

**采样策略**：表行数 > 10,000 时采样 10,000 行计算统计（`df.sample(10000, random_state=42)`），以保证延迟上限。

---

## 3. RetrievalAgent · 三层级联过滤（TLCF）

### 3.1 整体伪代码（论文算法 3-1）

```
Input: Tq, D={T1,...,TN}, τ∈{JOIN,UNION}, θ1,θ2,θ3, k1,k2, (w1,w2,w3)
Output: Ranked candidate list M sorted by S_final desc

# ---- Layer 1: 元数据粗筛 ----
C1_pool ← []
for each Tc in D where Tc.status='READY' and tenant_id matches:
    S1 ← 0.7 · Sim_TFIDF(Tq, Tc) + 0.3 · Sim_Jaccard(Type(Aq), Type(Ac))
    if S1 > θ1:
        C1_pool.append((Tc, S1))
C1 ← TopK(C1_pool, k1) by S1                         # |C1| ≤ k1 = 120

# ---- Layer 2: 稠密向量召回 ----
W ← Qdrant.search(e_Tq, top_k=k2,
                  filter={tenant_id, status=READY})   # |W| = k2 = 40
C2 ← {Tc ∈ C1 ∩ W | S2(Tq, Tc) > θ2}                 # 交集约束

# ---- Layer 3: LLM 批处理验证 ----
C3_pool ← []
for each Tc in C2:
    S3 ← LLM_verify(Tq, Tc, τ)                       # 返回 [0,1]
    if S3 > θ3:
        C3_pool.append((Tc, S3))
C3 ← C3_pool

# ---- 归一化 + 加权聚合 ----
for l in {1, 2, 3}:
    Ŝ_l ← min_max_norm({S_l(Tc) for Tc in C3})
for each Tc in C3:
    S_final(Tc) ← w1·Ŝ1 + w2·Ŝ2 + w3·Ŝ3
M ← sort(C3, key=S_final, desc)
return M
```

### 3.2 Layer 1 公式细节

**S₁ 计算**（论文公式 3-3）：
```
S1(Tq, Tc) = ω1 · Sim_TFIDF(Tq, Tc) + ω2 · Sim_Jaccard(Type(Aq), Type(Ac))
```
**默认权重**：ω₁ = 0.7，ω₂ = 0.3（论文固定值）。

**Sim_TFIDF**（论文公式 3-4）：
```python
sim_tfidf = cosine_similarity(v_tfidf(Tq), v_tfidf(Tc))  # scipy.sparse 余弦
```

**Sim_Jaccard on type multiset**（论文公式 3-5）：
```python
def type_jaccard(types_q: list[str], types_c: list[str]) -> float:
    # 注意是"多重集合" Jaccard：用 Counter
    cq, cc = Counter(types_q), Counter(types_c)
    inter = sum((cq & cc).values())
    union = sum((cq | cc).values())
    return inter / union if union else 0.0
```

**C₁ 构造**（论文公式 3-6）：
```
C1 = TopK({Tc ∈ D | S1(Tq,Tc) > θ1}, k1)
```
实现时可**边扫边维护小顶堆**，避免对全湖排序。

### 3.3 Layer 2 公式细节

**S₂ 计算**（论文公式 3-7）：
```
S2(Tq, Tc) = cosine(e_Tq, e_Tc)
```
因 Qdrant 用 Cosine 距离返回 `distance`，需转换：`S2 = 1 - distance`（**当向量已归一化时**，等价于内积）。

**C₂ 构造**（论文公式 3-9）：**交集约束是核心**，不能用 Qdrant 结果直接代替。
```python
W = set(qdrant.search(e_Tq, top_k=k2, filter=...).ids)     # k2 = 40
C2 = {Tc for Tc in C1 if Tc.id in W and S2(Tc) > theta_2}
```
若 |C₂| < 3，触发**回退策略**：放宽到 W ∪ C₁ 的 top-3，标记 state.degraded=True。

### 3.4 Layer 3：LLM 批处理验证

**批处理打包**：把 C₂ 中所有候选表的元数据打包到**同一个** prompt，一次 LLM 调用返回多个 S₃，显著降低延迟。

**单次 Prompt 模板**：
```text
[System]
You are a data integration expert. Given a query table and several candidate tables,
score each candidate's {task_type} compatibility with the query table.

Task definition:
- JOIN: candidate must share a column that can serve as a JOIN key with the query
        (high value overlap on some column).
- UNION: candidate must describe the same type of entity as the query
         (compatible schema, mergeable rows).

[Query Table]
name: {Tq.name}
columns: [{name:type} for col in Tq.columns[:20]]   # 最多展示 20 列

[Candidates]
(1) name: {Tc1.name}, columns: [...]
(2) name: {Tc2.name}, columns: [...]
...
(N) name: {TcN.name}, columns: [...]

[Instruction]
For each candidate, output a compatibility score in [0,1].
1.0 = perfect match, 0.0 = completely unrelated.

[Output, JSON only, schema enforced]
{"scores": [
  {"candidate_idx": 1, "score": 0.xx, "reason": "<15 字内>"},
  ...
]}
```

**批大小**：单批 ≤ 10 个候选（防止 8K 上下文超限）。若 |C₂| = 40，拆分为 4 批并行（通过 `asyncio.gather`）。

**幻觉防护**：
- `temperature=0.0`
- `enable_thinking=False`
- JSON Schema 强约束（Pydantic `L3BatchResult`）
- 若 LLM 返回的 `candidate_idx` 超出范围或缺项，视作 S₃=0.0，继续下游

### 3.5 归一化与聚合（论文公式 3-12 / 3-13）

**Min-max 归一化**：
```python
def min_max_norm(scores: list[float], eps: float = 1e-8) -> list[float]:
    lo, hi = min(scores), max(scores)
    return [(s - lo) / (hi - lo + eps) for s in scores]
```
注意：归一化是**在候选集 C₃ 内**执行的，不是全库。

**最终聚合**：
```
S_final(Tc) = w1·Ŝ1(Tc) + w2·Ŝ2(Tc) + w3·Ŝ3(Tc)
```
w₁ + w₂ + w₃ = 1，按 §1.4 的 plan 取值。

### 3.6 输出

写入 state 的 `ranking` 字段（按 S_final 降序）：
```python
[
  {"table_id": "...", "score": 0.91,
   "layer_scores": {"s1": 0.42, "s2": 0.73, "s3": 0.93},
   "normalized": {"s1_hat": 0.85, "s2_hat": 0.77, "s3_hat": 0.99}},
  ...
]
```

### 3.7 性能指标（论文表 3-3，作为回归测试基准）

| Layer | 输入规模 | 输出规模 | 累计剪枝率 | 平均耗时 |
|---|---|---|---|---|
| Full | 500 | — | 0% | — |
| L1 | 500 | 120 | 76% | 18.5 ms |
| L2 | 120 ∩ 40 | 40 | 92% | 45.2 ms |
| L3 | 40 | 10 | 98% | 2374 ms |

**回归测试**：OpenData JOIN 子集上 R@10 ≥ 63.9%（±3%），端到端延迟 ≤ 2.5 s。

---

## 4. MatcherAgent · 多场景自适应模式匹配

### 4.1 场景识别

场景由**目标表 Tt（或 C₃ 中每张候选表）的实例数据可用性**决定：

```python
def detect_scenario(tt: TableProfile) -> Literal["SMD", "SSD", "SLD"]:
    # 无实例值（或全 null）
    if all(c.sample_values == [] or c.null_ratio > 0.99 for c in tt.columns):
        return "SMD"
    # 样本数很少（≤ 10 行）
    if tt.row_count is not None and tt.row_count <= 10:
        return "SSD"
    # 其余都视作全量
    return "SLD"
```

API 调用方也可通过 `options.scenario_hint` 强制指定。

### 4.2 混合相似度计算

给定源列 a_s ∈ A_s、目标列 a_t ∈ A_t，混合得分 M(a_s, a_t) 计算路径：

```
M(a_s, a_t) = λ_text · Sim_name + λ_struct · Sim_type + λ_stat · Sim_stat
```

λ 权重按场景取值（论文公式 4-14 ~ 4-16）：

| 场景 | λ_text | λ_struct | λ_stat |
|---|---|---|---|
| SMD | 0.6 | 0.4 | 0.0 |
| SSD | 0.5 | 0.3 | 0.2 |
| SLD | 0.4 | 0.2 | 0.4 |

#### 4.2.1 Sim_name（文本名称相似度，论文公式 4-2 ~ 4-5）

```
Sim_name(a_s, a_t) = α1·Sim_Lev + α2·Sim_seq + α3·Sim_JAC
```
α₁ = 0.4, α₂ = 0.3, α₃ = 0.3（论文默认）。

**Sim_Lev**（公式 4-2）：
```python
def sim_lev(s1: str, s2: str) -> float:
    d = Levenshtein.distance(s1, s2)          # python-Levenshtein
    return 1.0 - d / max(len(s1), len(s2), 1)
```

**Sim_seq**（最长公共子序列，公式 4-3）：
```python
def sim_seq(s1: str, s2: str) -> float:
    lcs = len(longest_common_subsequence(s1, s2))
    return 2.0 * lcs / (len(s1) + len(s2)) if (len(s1)+len(s2)) else 0.0
```

**Sim_JAC_token**（词元 Jaccard，公式 4-4）：
```python
def tokenize(name: str) -> set[str]:
    # snake_case / CamelCase / 混合命名
    import re
    tokens = re.split(r'[_\s]+|(?<=[a-z])(?=[A-Z])', name.lower())
    return {t for t in tokens if t}

def sim_jac_name(s1: str, s2: str) -> float:
    w1, w2 = tokenize(s1), tokenize(s2)
    if not (w1 | w2):
        return 0.0
    return len(w1 & w2) / len(w1 | w2)
```

#### 4.2.2 Sim_type（结构类型兼容性，论文公式 4-6）

```python
# 类型兼容图
COMPATIBLE = {
    ("int", "float"): 0.5,
    ("float", "int"): 0.5,
    ("int", "str"):   0.5,   # 数字可字符串化
    ("float", "str"): 0.5,
    ("date", "str"):  0.5,
    ("str", "date"):  0.5,
}

def sim_type(t1: str, t2: str, delta: float = 0.5) -> float:
    if t1 == t2:
        return 1.0
    return COMPATIBLE.get((t1, t2), 0.0)
```

#### 4.2.3 Sim_stat（统计分布相似度）

**类型派发**：
```python
def sim_stat(a_s: ColumnProfile, a_t: ColumnProfile) -> float:
    if a_s.dtype in {"int", "float", "date"} and a_t.dtype in {"int", "float", "date"}:
        return sim_num(a_s.numeric_stats, a_t.numeric_stats)
    if a_s.dtype in {"str", "bool"} and a_t.dtype in {"str", "bool"}:
        return sim_cat(a_s.categorical_stats, a_t.categorical_stats)
    return 0.0   # 类型不同，统计层无意义
```

**数值型 Sim_num**（公式 4-7 ~ 4-10）：
```
Sim_num = β1·Sim_mean + β2·Sim_std + β3·Sim_quantile
β1 = 0.4, β2 = 0.3, β3 = 0.3

Sim_mean(V1, V2)     = 1 - |μ1 - μ2| / (max(|μ1|,|μ2|) + ε)
Sim_std(V1, V2)      = 1 - |σ1 - σ2| / (max(σ1, σ2) + ε)
Sim_quantile(V1, V2) = (1/3) · Σ_{p∈{25,50,75}} 1 - |qp1-qp2| / (max(|qp1|,|qp2|) + ε)
```
ε = 1e-8（论文明确值）。

**类别型 Sim_cat**（公式 4-11、4-12）：
```
Sim_cat = γ1·Sim_JAC_vals + γ2·Sim_dist_freq
γ1 = γ2 = 0.5

Sim_JAC_vals  = |V(a_s) ∩ V(a_t)| / |V(a_s) ∪ V(a_t)|   # 取值集合
Sim_dist_freq = cosine(f_s, f_t)                         # 归一化频率向量余弦
```

### 4.3 候选列对过滤（论文公式 4-17）

```
C_pi = {(a_s, a_t) ∈ A_s × A_t | M(a_s, a_t) ≥ θ_cand}
```

**θ_cand 默认值**：**0.35**（较宽松，只剔除明显不相关的，保证召回）。

### 4.4 Top-N 截断（系统设计文档 §5.2 要求）

对单个源列 a_s，其候选集 `{(a_s, a_t) | a_t ∈ A_t, M ≥ θ_cand}` 可能很大。Matcher 在送 LLM 前**先按 M 降序取 top-10**，仅这 10 个进入 LLM 验证。

```python
MATCH_LLM_TOPN = 10

def truncate_per_source(c_pi: list[ColPair]) -> list[ColPair]:
    by_src = defaultdict(list)
    for pair in c_pi:
        by_src[pair.src_col_id].append(pair)
    result = []
    for src, pairs in by_src.items():
        pairs.sort(key=lambda p: p.m_score, reverse=True)
        result.extend(pairs[:MATCH_LLM_TOPN])
    return result
```

### 4.5 LLM 最终判定（论文公式 4-18、4-19）

对每对 (a_s, a_t) ∈ C_pi（经 Top-N 截断后）调用 LLM，得到 R_conf ∈ [0,1]，最终：
```
m(a_s, a_t) = (R_conf ≥ θ_match) ? True : False
```
**θ_match 默认值**：**0.70**。

### 4.6 四段式提示词模板（论文图 4-2）

**Block 1: System Message**（所有场景共用）：
```text
You are an AI assistant specialized in data integration and schema matching.
Your expertise lies in analyzing attribute similarities across different database tables.
Respond with strict JSON only, no markdown, no extra prose.
```

**Block 2: Task Description**（所有场景共用）：
```text
Your task is to determine if two attributes (columns) are semantically equivalent.
Each attribute has a name, data type, and (in some scenarios) a description, sample values,
or statistical summary. You must assess whether they capture the exact same concept.
```

**Block 3: Instance Content**（场景差异化注入）：

SMD 版：
```text
[Attribute A]
Name: {a_s.name}
Type: {a_s.dtype}
Description: {a_s.description or "(none)"}

[Attribute B]
Name: {a_t.name}
Type: {a_t.dtype}
Description: {a_t.description or "(none)"}

[Pre-computed Similarities]
Sim_name={sim_name:.3f}, Sim_type={sim_type:.3f}
```

SSD 版（在 SMD 基础上追加）：
```text
[Sample Values]
A: {a_s.sample_values[:5]}
B: {a_t.sample_values[:5]}
```

SLD 版（在 SSD 基础上追加）：
```text
[Statistical Summary]
A: mean={μ_s:.2f}, std={σ_s:.2f}, q25/50/75=[{q25_s:.2f}, {q50_s:.2f}, {q75_s:.2f}]
B: mean={μ_t:.2f}, std={σ_t:.2f}, q25/50/75=[{q25_t:.2f}, {q50_t:.2f}, {q75_t:.2f}]
Sim_stat={sim_stat:.3f}, M_mixed={m_score:.3f}
```

**Block 4: Reasoning Guide**（场景差异化）：
```text
Consider the following when judging (scenario = {SMD|SSD|SLD}):
{
  "SMD": "- Focus on column name semantics and description context.\n- Watch out for domain abbreviations.",
  "SSD": "- Check if sample value formats match (e.g. 'm/f' vs 'male/female' may still be equivalent).\n- Look beyond surface name similarity.",
  "SLD": "- Prioritize distributional evidence over name similarity.\n- A large mean shift (>20%) typically indicates different concepts even with identical types.",
}[scenario]
```

**Block 5: Conclusion Directive**（所有场景共用，JSON Schema 强约束）：
```text
Output JSON with the following fields only:
{
  "reasoning": "<one sentence, <=50 words>",
  "score": <float in [0, 1]>,
  "is_equivalent": <true|false based on score>=0.70>
}
```

### 4.7 MatcherAgent 伪代码（论文算法 4-1）

```
Input: A_s, A_t, TableProfile_s, TableProfile_t, scenario SC
Output: similarity_matrix Sim[n][m], final mappings m[][]

# Stage 1: 全量混合相似度计算
for i in 1..n:
    for j in 1..m:
        λ = SCENARIO_WEIGHTS[SC]
        Sim[i][j] = λ.text  * sim_name(A_s[i], A_t[j])
                  + λ.struct * sim_type(A_s[i].dtype, A_t[j].dtype)
                  + λ.stat  * sim_stat(A_s[i], A_t[j])    # 若 SMD，λ.stat=0 则本项为 0

# Stage 2: 候选过滤 + Top-N 截断
C_pi = [(i,j) for i,j if Sim[i][j] >= θ_cand]
C_pi = truncate_per_source(C_pi, top_n=10)

# Stage 3: LLM 批量判定
prompts = [build_prompt(A_s[i], A_t[j], TableProfile_s, TableProfile_t, SC)
           for (i,j) in C_pi]
responses = llm.batch_call(prompts, schema=MatchResult)
for (i,j), resp in zip(C_pi, responses):
    m[i][j] = resp.score >= θ_match
    confidence[i][j] = resp.score

# Stage 4: 1:1 约束（可选，仅 JOIN 场景启用）
if task_type == INTEGRATE and subtask == JOIN:
    m = hungarian_1to1(confidence, threshold=θ_match)   # 匈牙利算法

return Sim, m, confidence
```

### 4.8 1:1 约束（可选但推荐）

JOIN 场景的列映射理论上应是 1:1 的。实现：
```python
from scipy.optimize import linear_sum_assignment

def hungarian_1to1(confidence: np.ndarray, threshold: float) -> dict:
    """最大化总置信度的 1:1 匹配，低于阈值的强制 unmatched"""
    cost = -confidence   # 转最小化
    row_ind, col_ind = linear_sum_assignment(cost)
    result = {}
    for i, j in zip(row_ind, col_ind):
        if confidence[i][j] >= threshold:
            result[i] = j
    return result
```

### 4.9 性能指标（论文表 4-2，作为回归测试基准）

| 场景 | Valentine F1 | MIMIC-III F1 |
|---|---|---|
| SMD | ≥ 79.87% | ≥ 48.52% |
| SSD | ≥ 82.82% | — |
| SLD | ≥ 92.52% | — |

---

## 5. 完整默认超参速查表

开发时所有参数集中放 `configs/default.yaml`，下表为**论文实验验证值**，改动需有充分理由。

```yaml
# ============ TLCF（RetrievalAgent） ============
tlcf:
  # Layer 1
  omega_1: 0.7       # TF-IDF 权重
  omega_2: 0.3       # Jaccard 权重
  theta_1: 0.20      # L1 阈值（敏感性分析肘部）
  k_1:     120       # L1 候选截断数

  # Layer 2
  theta_2: 0.55      # L2 向量余弦阈值
  k_2:     40        # L2 HNSW top-k（也是 L3 输入上限）

  # Layer 3
  theta_3: 0.50      # L3 LLM 置信度阈值
  l3_batch_size: 10  # 单次 LLM 调用包含候选数

  # 聚合权重（按 subtask 切换）
  weights_join:  {w1: 0.2, w2: 0.3, w3: 0.5}
  weights_union: {w1: 0.4, w2: 0.4, w3: 0.2}

# ============ Matcher ============
matcher:
  # 名称相似度融合
  alpha_1: 0.4       # Sim_Lev
  alpha_2: 0.3       # Sim_seq
  alpha_3: 0.3       # Sim_JAC_token

  # 类型兼容
  delta_type_compat: 0.5

  # 数值统计
  beta_1: 0.4        # Sim_mean
  beta_2: 0.3        # Sim_std
  beta_3: 0.3        # Sim_quantile
  epsilon: 1e-8

  # 类别统计
  gamma_1: 0.5       # Sim_JAC_vals
  gamma_2: 0.5       # Sim_dist_freq

  # 场景权重
  scenario_weights:
    SMD: {text: 0.6, struct: 0.4, stat: 0.0}
    SSD: {text: 0.5, struct: 0.3, stat: 0.2}
    SLD: {text: 0.4, struct: 0.2, stat: 0.4}

  # 决策
  theta_cand:  0.35  # 候选召回阈值（较宽松）
  theta_match: 0.70  # 最终判定阈值

  # Top-N 截断（超宽表保护）
  llm_topn_per_source: 10

  # 1:1 约束
  enable_1to1: true  # 仅 INTEGRATE+JOIN 启用

# ============ Profiling ============
profiling:
  sbert_model:      "sentence-transformers/all-MiniLM-L6-v2"
  sbert_device:     "cuda:0"
  sbert_batch_size: 256
  sample_rows:      10000       # 超过即采样
  sample_values:    5           # 每列保留几条样本

  tfidf:
    min_df: 2
    max_df: 0.9
    ngram_range: [1, 1]
    sublinear_tf: true

  cat_vocab_min_freq: 5

# ============ LLM ============
llm:
  model:        "qwen3.5:9b"
  temperature:  0.0
  max_tokens:   512
  timeout_s:    30
  enable_thinking: false        # Qwen3 特有
  max_retries:  2
  cache_ttl_h:  168             # L3 LLM 结果缓存 7 天
```

---

## 6. 符号—公式—代码位置对照表

开发时的"查图索骥"表，方便 Claude Code 在实现某个公式时知道对应代码应该写在哪里。

| 符号/公式 | 论文编号 | 代码位置 | 测试用例 |
|---|---|---|---|
| S₁ 计算 | 3-3 | `retrieval/layer1.py::compute_s1` | `test_s1_known_pairs` |
| Sim_TFIDF | 3-4 | `retrieval/tfidf.py::cosine` | — |
| Sim_Jaccard(types) | 3-5 | `retrieval/layer1.py::type_jaccard` | `test_type_jaccard` |
| C₁ top-k | 3-6 | `retrieval/layer1.py::build_c1` | — |
| S₂ 向量余弦 | 3-7/3-8 | `retrieval/layer2.py::search` | — |
| C₂ 交集 | 3-9 | `retrieval/layer2.py::intersect` | `test_c2_intersection` |
| S₃ LLM 批处理 | 3-10 | `retrieval/layer3.py::batch_verify` | `test_l3_batch` |
| C₃ | 3-11 | `retrieval/layer3.py::filter` | — |
| min-max 归一化 | 3-12 | `retrieval/aggregate.py::normalize` | `test_minmax_edge` |
| S_final | 3-13 | `retrieval/aggregate.py::aggregate` | — |
| 模式匹配函数 m | 4-1 | `matcher/decision.py::decide` | — |
| Sim_Lev | 4-2 | `matcher/text_sim.py::sim_lev` | `test_name_sim` |
| Sim_seq (LCS) | 4-3 | `matcher/text_sim.py::sim_seq` | — |
| Sim_JAC_token | 4-4 | `matcher/text_sim.py::sim_jac_name` | — |
| Sim_name | 4-5 | `matcher/text_sim.py::sim_name` | — |
| Sim_type | 4-6 | `matcher/struct_sim.py::sim_type` | `test_type_compat` |
| Sim_mean / std / quantile | 4-7~4-9 | `matcher/stat_sim.py::sim_num_*` | `test_num_stat` |
| Sim_num | 4-10 | `matcher/stat_sim.py::sim_num` | — |
| Sim_dist (freq cos) | 4-11 | `matcher/stat_sim.py::sim_dist` | — |
| Sim_cat | 4-12 | `matcher/stat_sim.py::sim_cat` | `test_cat_stat` |
| M 混合相似度 | 4-13 | `matcher/mixed.py::mixed_score` | `test_scenario_weights` |
| λ 场景权重 | 4-14~4-16 | `configs/default.yaml::scenario_weights` | — |
| C_pi 候选过滤 | 4-17 | `matcher/candidates.py::filter` | — |
| R_conf LLM 推理 | 4-18 | `matcher/llm_verify.py::verify` | `test_llm_json_schema` |
| 布尔判定 | 4-19 | `matcher/decision.py::decide` | — |

---

## 7. LLM 输出 JSON Schema（Pydantic）

全部 LLM 交互的**强约束 schema**，用 `response_format={"type": "json_schema", ...}` 传递。

```python
# adacascade/llm_schemas.py
from pydantic import BaseModel, Field
from typing import Literal

class PlannerDecision(BaseModel):
    """Planner 的 subtask 决策"""
    subtask: Literal["JOIN", "UNION"]
    reason: str = Field(max_length=60)

class L3CandidateScore(BaseModel):
    """Retrieval L3 对单个候选的评分"""
    candidate_idx: int = Field(ge=1)
    score: float = Field(ge=0.0, le=1.0)
    reason: str = Field(max_length=60)

class L3BatchResult(BaseModel):
    """Retrieval L3 批处理返回"""
    scores: list[L3CandidateScore]

class MatchResult(BaseModel):
    """Matcher 对单个列对的判定"""
    reasoning: str = Field(max_length=300)
    score: float = Field(ge=0.0, le=1.0)
    is_equivalent: bool
```

调用时：
```python
resp = llm_client.chat(
    messages=[...],
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
result = MatchResult.model_validate_json(resp.choices[0].message.content)
```

---

## 8. 关键单元测试清单（最小回归集）

每个公式至少 1 个 unit test，每个 Agent 至少 1 个 integration test。

### 8.1 单元测试
- `test_type_jaccard`：Counter({int:2, str:1}) ↔ Counter({int:1, str:2}) → 2/4 = 0.5
- `test_minmax_edge`：所有分数相同 → 全部归一化为 0（除以 eps 不报错）
- `test_name_sim`：("user_id", "userId") 应 ≥ 0.8（snake vs camel 命名）
- `test_type_compat`：(int, float) → 0.5；(int, str) → 0.5；(date, int) → 0.0
- `test_scenario_weights`：SMD 下 λ_stat 必须为 0，测试确认 Sim_stat 再大也不影响 M
- `test_llm_json_schema`：mock 一个不合 schema 的 LLM 响应，验证 Pydantic 报错而不是静默通过

### 8.2 集成测试（小数据集）
构造一个 10 表的玩具数据湖（3 对人工标注 JOIN 匹配对、2 对 UNION 匹配对），放 `tests/fixtures/toy_lake/`。
- `test_tlcf_toy`：端到端运行 TLCF，断言已知的 3 对 JOIN 匹配全部进入 C₃
- `test_matcher_toy_smd`：用 toy 表跑 SMD 场景，断言已知列对 m=True
- `test_end2end_toy`：调 `/integrate` 端点，断言 ranking[0] 是人工标注的正确候选

### 8.3 论文复现测试（可选，论文答辩前跑）
- `test_opendata_join_r10`：OpenData JOIN 子集 R@10 ≥ 60%
- `test_valentine_sld_f1`：Valentine SLD 场景 F1 ≥ 90%

---

## 9. 开发顺序建议

对应系统设计文档 §11 的四个里程碑，把算法开发拆到每个阶段：

**M1 骨架（2 周）**
- 只实现 §2 Profiling 的完整链路（含 TF-IDF 训练 + SBERT GPU 编码 + Qdrant upsert）
- RetrievalAgent / MatcherAgent 用**占位桩**（返回 mock 数据）
- 目标：`POST /tables` → Profiling 落表 → `GET /tables/{id}` 看到 READY

**M2 算法（3 周）**—— 本文档的主战场
- Week 1：§3 TLCF 三层（L1 + L2 + L3 批处理 + 归一化 + 聚合），通过 §8.1、§8.2 全部测试
- Week 2：§4 Matcher 所有相似度公式 + 场景权重 + Top-N 截断 + 1:1 约束
- Week 3：§7 LLM JSON Schema 强约束、§4.6 五段式提示词完整实现，跑论文复现测试

**M3 集成（2 周）** / **M4 上线（1 周）**：与系统设计文档一致。

---

## 附录 · 论文章节 → 本文档章节映射

若论文读者需要对照：

| 论文章节 | 本文档章节 |
|---|---|
| §3.1 框架总体设计 | §1（PlannerAgent 职责） |
| §3.3 PlannerAgent | §1 |
| §3.4 ProfilingAgent | §2 |
| §3.5 TLCF 算法 | §3 |
| §4.2 场景定义 | §4.1 |
| §4.3 混合相似度 | §4.2 |
| §4.4 LLM 推理决策 | §4.3 ~ §4.6 |
| 算法 3-1 | §3.1 伪代码 |
| 算法 4-1 | §4.7 伪代码 |
