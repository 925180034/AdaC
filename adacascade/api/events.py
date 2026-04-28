"""In-process task event bus and SSE stream helpers."""

from __future__ import annotations

import asyncio
import json
from collections import OrderedDict, defaultdict, deque
from collections.abc import AsyncIterator
from datetime import datetime, timezone
from typing import Any

TaskEvent = dict[str, Any]

_HISTORY_LIMIT = 200
_QUEUE_LIMIT = 200
_TASK_HISTORY_LIMIT = 512
_history: OrderedDict[str, deque[TaskEvent]] = OrderedDict()
_subscribers: dict[str, set[asyncio.Queue[TaskEvent]]] = defaultdict(set)
_lock = asyncio.Lock()


def _new_history() -> deque[TaskEvent]:
    return deque(maxlen=_HISTORY_LIMIT)


def _sse_frame(event: TaskEvent) -> str:
    event_type = str(event.get("type", "message"))
    payload = json.dumps(event, ensure_ascii=False, separators=(",", ":"))
    return f"event: {event_type}\ndata: {payload}\n\n"


def _timestamp() -> str:
    return datetime.now(timezone.utc).isoformat()


async def emit_task_event(task_id: str, event: TaskEvent) -> None:
    """Publish a task-scoped event to history and active SSE subscribers."""
    enriched = {**event, "task_id": task_id, "timestamp": _timestamp()}
    async with _lock:
        history = _history.setdefault(task_id, _new_history())
        history.append(enriched)
        _history.move_to_end(task_id)
        while len(_history) > _TASK_HISTORY_LIMIT:
            _history.popitem(last=False)
        subscribers = tuple(_subscribers.get(task_id, set()))

    for queue in subscribers:
        if queue.full():
            try:
                queue.get_nowait()
            except asyncio.QueueEmpty:
                pass
        queue.put_nowait(enriched)


async def stream_task_events(task_id: str) -> AsyncIterator[str]:
    """Yield task events as Server-Sent Events from history, then live updates."""
    queue: asyncio.Queue[TaskEvent] = asyncio.Queue(maxsize=_QUEUE_LIMIT)
    async with _lock:
        history = tuple(_history.get(task_id, ()))
        terminal_history = bool(history and history[-1].get("type") == "task_completed")
        if not terminal_history:
            _subscribers[task_id].add(queue)

    try:
        for event in history:
            yield _sse_frame(event)
        if terminal_history:
            return

        while True:
            try:
                event = await asyncio.wait_for(queue.get(), timeout=10.0)
            except TimeoutError:
                yield _sse_frame(
                    {"type": "heartbeat", "task_id": task_id, "timestamp": _timestamp()}
                )
                continue

            yield _sse_frame(event)
            if event.get("type") == "task_completed":
                return
    finally:
        async with _lock:
            subscribers = _subscribers.get(task_id)
            if subscribers is not None:
                subscribers.discard(queue)
                if not subscribers:
                    _subscribers.pop(task_id, None)
