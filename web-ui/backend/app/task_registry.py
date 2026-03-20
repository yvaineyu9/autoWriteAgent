from __future__ import annotations

import asyncio
from dataclasses import dataclass, field
from datetime import datetime
from typing import Any
from uuid import uuid4


@dataclass
class TaskRecord:
    task_id: str
    task_type: str
    content_id: str | None
    status: str = "queued"
    started_at: datetime | None = None
    ended_at: datetime | None = None
    events: list[dict[str, Any]] = field(default_factory=list)
    queue: asyncio.Queue[dict[str, Any] | None] = field(default_factory=asyncio.Queue)


class TaskRegistry:
    def __init__(self) -> None:
        self._tasks: dict[str, TaskRecord] = {}

    def create(self, task_type: str, content_id: str | None) -> TaskRecord:
        task = TaskRecord(task_id=str(uuid4()), task_type=task_type, content_id=content_id)
        self._tasks[task.task_id] = task
        return task

    def get(self, task_id: str) -> TaskRecord | None:
        return self._tasks.get(task_id)

    def find_active(self, *, content_id: str | None = None, task_type: str | None = None) -> TaskRecord | None:
        for task in self._tasks.values():
            if task.status not in {"queued", "running"}:
                continue
            if content_id is not None and task.content_id != content_id:
                continue
            if task_type is not None and task.task_type != task_type:
                continue
            return task
        return None

    async def emit(self, task: TaskRecord, event: str, payload: dict[str, Any] | None = None) -> None:
        envelope = {
            "event": event,
            "task_id": task.task_id,
            "content_id": task.content_id,
            "payload": payload or {},
            "created_at": datetime.utcnow().isoformat(),
        }
        task.events.append(envelope)
        await task.queue.put(envelope)

    async def finish(self, task: TaskRecord, status: str) -> None:
        task.status = status
        task.ended_at = datetime.utcnow()
        await self.emit(task, f"task.{status}", {"status": status})
        await task.queue.put(None)


registry = TaskRegistry()
