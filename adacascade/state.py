"""IntegrationState TypedDict — shared across all LangGraph agents."""

from __future__ import annotations

from datetime import datetime
from typing import Literal, Optional

from typing_extensions import TypedDict


class IntegrationState(TypedDict, total=False):
    """Shared state object passed through the LangGraph pipeline.

    Large objects (similarity_matrix) are stored externally as .pkl files;
    only path references are kept here to control checkpoint size.
    """

    # ── 任务元信息 ─────────────────────────────────────────────────────────
    task_id: str
    tenant_id: str
    task_type: Literal["INTEGRATE", "DISCOVER_ONLY", "MATCH_ONLY"]
    subtask: Literal["JOIN", "UNION"]
    created_at: datetime

    # ── Planner 输出 ───────────────────────────────────────────────────────
    plan: dict[str, float | int]  # θ1/θ2/θ3, k1/k2, w1/w2/w3

    # ── Profiling 输出（句柄，不存真实数据） ────────────────────────────────
    query_profile: dict[str, object]  # Φq 句柄
    target_profile: dict[str, object]  # Φt（仅 MATCH_ONLY）
    candidate_profiles: dict[str, dict[str, object]]  # {table_id: Φi}

    # ── TLCF 三层中间结果（仅存 id 列表） ────────────────────────────────
    c1_meta: list[str]  # Layer 1 候选 table_id
    c2_vec: list[str]  # Layer 2 候选 table_id
    c3_llm: list[str]  # Layer 3 候选 table_id

    # ── 最终输出 ──────────────────────────────────────────────────────────
    ranking: list[dict[str, object]]  # 候选排名（含 layer_scores）
    # 大对象外置：只存路径，矩阵在 data/artifacts/{task_id}/sim.pkl
    similarity_matrix_path: Optional[str]
    final_mappings: list[dict[str, object]]

    # ── 执行状态 ──────────────────────────────────────────────────────────
    trace: list[dict[str, object]]
    status: Literal["RUNNING", "SUCCESS", "FAILED"]
    degraded: bool
    error_message: Optional[str]
