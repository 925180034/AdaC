"""PlannerAgent — task type routing and plan generation (Algorithm Spec §1)."""

from __future__ import annotations

from typing import Any, Literal

import structlog

from adacascade.config import settings
from adacascade.llm_client import chat
from adacascade.llm_schemas import PlannerDecision, json_schema_format
from adacascade.state import IntegrationState

log = structlog.get_logger(__name__)

_DEFAULT_PLANS: dict[str, dict[str, float | int]] = {
    "JOIN": {
        "theta_1": 0.20,
        "theta_2": 0.55,
        "theta_3": 0.50,
        "k_1": 120,
        "k_2": 40,
        "w_1": 0.2,
        "w_2": 0.3,
        "w_3": 0.5,
    },
    "UNION": {
        "theta_1": 0.20,
        "theta_2": 0.55,
        "theta_3": 0.50,
        "k_1": 120,
        "k_2": 40,
        "w_1": 0.4,
        "w_2": 0.4,
        "w_3": 0.2,
    },
}


def _detect_subtask_heuristic(
    col_names: list[str],
    col_types: list[str],
    distinct_ratios: list[float],
    user_hint: str,
) -> str | None:
    """Fast heuristic subtask detection without LLM (Algorithm Spec §1.3)."""
    hint_lower = user_hint.lower()
    if any(kw in hint_lower for kw in ("join", "关联", "连接", "扩充属性")):
        return "JOIN"
    if any(kw in hint_lower for kw in ("union", "合并", "追加", "并集")):
        return "UNION"
    # Suspicious primary key → likely JOIN
    for dr, ct in zip(distinct_ratios, col_types):
        if dr > 0.95 and ct in ("int", "str"):
            return "JOIN"
    return None


def _call_llm_subtask(
    table_name: str,
    columns: list[dict[str, str]],
    sample_rows: list[dict[str, Any]],
    user_hint: str,
) -> str:
    """Ask LLM to classify JOIN vs UNION (Algorithm Spec §1.3)."""
    col_repr = [f"{c['name']}:{c['type']}" for c in columns]
    messages = [
        {
            "role": "system",
            "content": (
                "你是数据集成领域的规划助手。你的任务是判断用户希望对一张查询表执行哪种数据发现任务。\n\n"
                "给定一张查询表的元数据与前几行样本，判断用户意图是：\n"
                "- JOIN：横向扩充——从数据湖中找与本表存在连接键的表，以扩充属性\n"
                "- UNION：纵向扩充——从数据湖中找描述同一类实体、结构兼容的表，以追加记录"
            ),
        },
        {
            "role": "user",
            "content": (
                f"[Query Table]\n"
                f"name: {table_name}\n"
                f"columns: {col_repr}\n"
                f"sample_rows: {sample_rows[:3]}\n"
                f"user_hint: {user_hint or '(none)'}\n\n"
                "Output JSON only."
            ),
        },
    ]
    resp = chat(messages, response_format=json_schema_format(PlannerDecision))
    content = resp.choices[0].message.content or ""
    decision = PlannerDecision.model_validate_json(content)
    log.info("planner.llm_decision", subtask=decision.subtask, reason=decision.reason)
    return decision.subtask


async def run(state: IntegrationState) -> IntegrationState:
    """LangGraph node: determine task_type (code) and subtask (heuristic/LLM)."""
    task_id = state.get("task_id", "")
    bound_log = log.bind(task_id=task_id)

    # task_type is set by the API route — Planner only validates
    task_type = state.get("task_type", "INTEGRATE")

    subtask = "JOIN"  # default
    if task_type != "MATCH_ONLY":
        query_profile: dict[str, Any] = state.get("query_profile", {})
        plan_raw = state.get("plan", {}) or {}
        user_hint: str = str(plan_raw.get("user_hint", ""))
        if query_profile:
            col_names: list[str] = [c["name"] for c in query_profile.get("columns", [])]
            col_types: list[str] = [
                c["dtype"] for c in query_profile.get("columns", [])
            ]
            distinct_ratios: list[float] = [
                c.get("distinct_ratio", 0.0) for c in query_profile.get("columns", [])
            ]

            heuristic = _detect_subtask_heuristic(
                col_names, col_types, distinct_ratios, user_hint
            )
            if heuristic:
                subtask = heuristic
                bound_log.info("planner.heuristic", subtask=subtask)
            else:
                subtask = _call_llm_subtask(
                    table_name=query_profile.get("table_name", ""),
                    columns=[
                        {"name": n, "type": t} for n, t in zip(col_names, col_types)
                    ],
                    sample_rows=query_profile.get("sample_rows", []),
                    user_hint=user_hint,
                )

    raw_plans = settings.planner_cfg.get("default_plans") or {}
    plan_cfg: dict[str, float | int] = dict(
        raw_plans.get(subtask, _DEFAULT_PLANS[subtask])
    )
    task_subtask: Literal["JOIN", "UNION"] = "JOIN" if subtask == "JOIN" else "UNION"
    return {
        **state,
        "subtask": task_subtask,
        "plan": plan_cfg,
    }
