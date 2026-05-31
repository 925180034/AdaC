"""PlannerAgent unit tests."""

from __future__ import annotations

from typing import Any

import pytest
import structlog
from structlog.testing import capture_logs

from adacascade.agents import planner
from adacascade.llm_schemas import PlannerDecision


@pytest.mark.anyio
async def test_planner_uses_async_llm_client_for_llm_subtask(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    calls: list[dict[str, Any]] = []

    class FakeMessage:
        content = PlannerDecision(subtask="UNION", reason="same entity rows").model_dump_json()

    class FakeChoice:
        message = FakeMessage()

    class FakeResponse:
        choices = [FakeChoice()]

    async def fake_chat_async(
        messages: list[dict[str, str]],
        **kwargs: Any,
    ) -> FakeResponse:
        calls.append({"messages": messages, "kwargs": kwargs})
        return FakeResponse()

    monkeypatch.setattr(planner, "chat_async", fake_chat_async)
    monkeypatch.setattr(
        planner,
        "_detect_subtask_heuristic",
        lambda *_args, **_kwargs: None,
    )

    state = {
        "task_id": "task-planner-async",
        "task_type": "INTEGRATE",
        "plan": {},
        "query_profile": {
            "table_name": "cities",
            "columns": [
                {"name": "city", "dtype": "str", "distinct_ratio": 0.5},
                {"name": "country", "dtype": "str", "distinct_ratio": 0.4},
            ],
            "sample_rows": [{"city": "Paris", "country": "France"}],
        },
    }

    with capture_logs() as captured_logs:
        result = await planner.run(state)

    assert result["subtask"] == "UNION"
    assert len(calls) == 1
    assert calls[0]["kwargs"]["response_format"] is not None
    decision_logs = [
        event for event in captured_logs if event["event"] == "planner.llm_decision"
    ]
    assert decision_logs == [
        {
            "event": "planner.llm_decision",
            "log_level": "info",
            "reason": "same entity rows",
            "subtask": "UNION",
            "task_id": "task-planner-async",
        }
    ]

    structlog.reset_defaults()
