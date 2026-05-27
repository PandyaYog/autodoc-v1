"""
Task Store — in-memory registry for background documentation tasks.

Each task moves through these states:
    pending  →  processing  →  completed
                            ↘  failed

The store is a plain dict keyed by task_id (UUID string). It lives for the
lifetime of the process — results are lost on server restart (acceptable for
the current single-process deployment; migrate to Redis if you add workers).

Usage:
    from .services.task_store import task_store

    task_id = task_store.create()                       # returns str UUID
    task_store.mark_processing(task_id)
    task_store.mark_completed(task_id, docs, pdf_bytes) # stores both outputs
    task_store.mark_failed(task_id, "reason")
    record = task_store.get(task_id)                    # returns TaskRecord | None
    task_store.cleanup(max_age_seconds=3600)            # prune old tasks
"""

import logging
import uuid
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Dict, Literal, Optional

logger = logging.getLogger(__name__)

# All valid status values for a task
TaskStatus = Literal["pending", "processing", "completed", "failed"]


@dataclass
class TaskRecord:
    """
    Holds the full state of a single background documentation task.

    Attributes:
        task_id:       Unique identifier (UUID4 string).
        status:        Current lifecycle state.
        filename:      Original uploaded ZIP filename (for user context).
        documentation: Final Markdown output — set only when status='completed'.
        pdf_bytes:     Rendered PDF bytes — set only when status='completed'.
                       May be None if PDF rendering failed after successful assembly.
        error:         Human-readable failure reason — set only when status='failed'.
        created_at:    UTC timestamp when the task was created.
        updated_at:    UTC timestamp of the last status change.
    """
    task_id: str
    status: TaskStatus
    filename: str
    documentation: Optional[str] = None
    pdf_bytes: Optional[bytes] = None
    error: Optional[str] = None
    created_at: datetime = field(default_factory=lambda: datetime.now(timezone.utc))
    updated_at: datetime = field(default_factory=lambda: datetime.now(timezone.utc))


class TaskStore:
    """
    Thread-safe (asyncio-safe) in-memory store for background task records.

    All public methods are synchronous — they only mutate a plain dict, which
    is safe in a single-threaded asyncio event loop without any locks.
    """

    def __init__(self) -> None:
        self._store: Dict[str, TaskRecord] = {}

    # ── Write operations ──────────────────────────────────────────────────────

    def create(self, filename: str) -> str:
        """
        Registers a new task in 'pending' state and returns its task_id.

        Args:
            filename: The original uploaded filename (stored for user context).

        Returns:
            task_id: A UUID4 string that uniquely identifies this task.
        """
        task_id = str(uuid.uuid4())
        record = TaskRecord(
            task_id=task_id,
            status="pending",
            filename=filename,
        )
        self._store[task_id] = record
        logger.info(f"[TaskStore] Created task '{task_id}' for file '{filename}'.")
        return task_id

    def mark_processing(self, task_id: str) -> None:
        """Transitions task to 'processing'. Call this when the pipeline starts."""
        record = self._get_or_warn(task_id)
        if record:
            record.status = "processing"
            record.updated_at = datetime.now(timezone.utc)
            logger.info(f"[TaskStore] Task '{task_id}' → processing.")

    def mark_completed(self, task_id: str, documentation: str, pdf_bytes: Optional[bytes] = None) -> None:
        """
        Transitions task to 'completed' and stores the generated outputs.

        Args:
            task_id:       The task to update.
            documentation: The full Markdown documentation string.
            pdf_bytes:     Rendered PDF bytes. May be None if PDF rendering
                           failed after successful Markdown assembly — the
                           task is still marked completed, but the download
                           endpoint will return a 503 in that case.
        """
        record = self._get_or_warn(task_id)
        if record:
            record.status = "completed"
            record.documentation = documentation
            record.pdf_bytes = pdf_bytes
            record.updated_at = datetime.now(timezone.utc)
            pdf_status = f"{len(pdf_bytes):,} bytes" if pdf_bytes else "unavailable"
            logger.info(f"[TaskStore] Task '{task_id}' → completed (PDF: {pdf_status}).")

    def mark_failed(self, task_id: str, error: str) -> None:
        """
        Transitions task to 'failed' and stores the error reason.

        Args:
            task_id: The task to update.
            error:   Human-readable description of what went wrong.
        """
        record = self._get_or_warn(task_id)
        if record:
            record.status = "failed"
            record.error = error
            record.updated_at = datetime.now(timezone.utc)
            logger.warning(f"[TaskStore] Task '{task_id}' → failed: {error}")

    # ── Read operations ───────────────────────────────────────────────────────

    def get(self, task_id: str) -> Optional[TaskRecord]:
        """
        Returns the TaskRecord for the given task_id, or None if not found.

        Args:
            task_id: UUID string returned by create().

        Returns:
            TaskRecord if found, None otherwise.
        """
        return self._store.get(task_id)

    def exists(self, task_id: str) -> bool:
        """Returns True if the task_id is registered in the store."""
        return task_id in self._store

    # ── Maintenance ───────────────────────────────────────────────────────────

    def cleanup(self, max_age_seconds: int = 3600) -> int:
        """
        Removes tasks that completed or failed more than `max_age_seconds` ago.
        Pending and processing tasks are never removed.

        Args:
            max_age_seconds: Age threshold in seconds (default: 1 hour).

        Returns:
            Number of tasks removed.
        """
        now = datetime.now(timezone.utc)
        to_delete = [
            task_id
            for task_id, record in self._store.items()
            if record.status in ("completed", "failed")
            and (now - record.updated_at).total_seconds() > max_age_seconds
        ]
        for task_id in to_delete:
            del self._store[task_id]

        if to_delete:
            logger.info(f"[TaskStore] Cleanup removed {len(to_delete)} expired task(s).")
        return len(to_delete)

    def __len__(self) -> int:
        return len(self._store)

    # ── Internal helpers ──────────────────────────────────────────────────────

    def _get_or_warn(self, task_id: str) -> Optional[TaskRecord]:
        """Returns the record, or logs a warning if task_id is unknown."""
        record = self._store.get(task_id)
        if record is None:
            logger.warning(f"[TaskStore] Attempted to update unknown task '{task_id}'. Ignoring.")
        return record


# ── Module-level singleton (same pattern as `settings` in config.py) ─────────
task_store: TaskStore = TaskStore()
