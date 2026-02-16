"""In-memory background job queue for API-triggered research workflows."""

from __future__ import annotations

import traceback
from collections.abc import Callable
from concurrent.futures import ThreadPoolExecutor
from dataclasses import dataclass
from datetime import UTC, datetime
from threading import Lock
from typing import Any, Literal

from alphalab.core.utils.errors import AlphaLabError

JobTask = Callable[[], dict[str, Any]]


@dataclass(frozen=True)
class JobRecord:
    """Snapshot payload for one background job."""

    job_id: str
    job_type: Literal["run", "robustness"]
    status: Literal["queued", "running", "succeeded", "failed"]
    submitted_at: datetime
    started_at: datetime | None
    finished_at: datetime | None
    request: dict[str, Any]
    result: dict[str, Any] | None
    error_code: str | None
    error_message: str | None
    error_traceback: str | None


@dataclass
class _MutableJob:
    """Internal mutable job state."""

    job_id: str
    job_type: Literal["run", "robustness"]
    status: Literal["queued", "running", "succeeded", "failed"]
    submitted_at: datetime
    started_at: datetime | None
    finished_at: datetime | None
    request: dict[str, Any]
    result: dict[str, Any] | None
    error_code: str | None
    error_message: str | None
    error_traceback: str | None

    def to_record(self) -> JobRecord:
        """Create immutable record snapshot from mutable state."""
        return JobRecord(
            job_id=self.job_id,
            job_type=self.job_type,
            status=self.status,
            submitted_at=self.submitted_at,
            started_at=self.started_at,
            finished_at=self.finished_at,
            request=dict(self.request),
            result=None if self.result is None else dict(self.result),
            error_code=self.error_code,
            error_message=self.error_message,
            error_traceback=self.error_traceback,
        )


class InMemoryJobQueue:
    """Thread-safe FIFO-ish in-memory job queue backed by a thread pool."""

    def __init__(self, max_workers: int = 2) -> None:
        """
        Initialize queue state.

        Args:
            max_workers: Maximum background workers.
        """
        safe_workers = max(1, int(max_workers))
        self._executor = ThreadPoolExecutor(
            max_workers=safe_workers, thread_name_prefix="alphalab-job"
        )
        self._lock = Lock()
        self._jobs: dict[str, _MutableJob] = {}
        self._counter = 0

    def submit(
        self,
        job_type: Literal["run", "robustness"],
        request: dict[str, Any],
        task: JobTask,
    ) -> JobRecord:
        """
        Submit a new background job.

        Args:
            job_type: Semantic job type label.
            request: Request payload snapshot.
            task: Work function returning serialized result payload.

        Returns:
            Snapshot of queued job.
        """
        now = datetime.now(tz=UTC)
        with self._lock:
            self._counter += 1
            job_id = f"job_{self._counter:06d}"
            job = _MutableJob(
                job_id=job_id,
                job_type=job_type,
                status="queued",
                submitted_at=now,
                started_at=None,
                finished_at=None,
                request=dict(request),
                result=None,
                error_code=None,
                error_message=None,
                error_traceback=None,
            )
            self._jobs[job_id] = job

        self._executor.submit(self._run_job, job_id, task)
        return job.to_record()

    def get(self, job_id: str) -> JobRecord | None:
        """
        Get one job by id.

        Args:
            job_id: Job identifier.

        Returns:
            Job snapshot or ``None``.
        """
        with self._lock:
            job = self._jobs.get(job_id)
            return None if job is None else job.to_record()

    def list(self, limit: int = 100) -> list[JobRecord]:
        """
        List jobs in reverse submission order.

        Args:
            limit: Maximum number of jobs.

        Returns:
            Job snapshots.
        """
        safe_limit = max(1, int(limit))
        with self._lock:
            ordered = sorted(
                self._jobs.values(),
                key=lambda job: (job.submitted_at, job.job_id),
                reverse=True,
            )
            return [job.to_record() for job in ordered[:safe_limit]]

    def _run_job(self, job_id: str, task: JobTask) -> None:
        """Execute job task and persist final state."""
        self._mark_running(job_id)
        try:
            result = task()
            self._mark_succeeded(job_id, result=result)
        except Exception as exc:  # pragma: no cover - exercised via integration tests.
            self._mark_failed(job_id, exc)

    def _mark_running(self, job_id: str) -> None:
        """Transition a job to running state."""
        now = datetime.now(tz=UTC)
        with self._lock:
            job = self._jobs.get(job_id)
            if job is None:
                return
            job.status = "running"
            job.started_at = now
            job.finished_at = None

    def _mark_succeeded(self, job_id: str, result: dict[str, Any]) -> None:
        """Transition a job to succeeded state."""
        now = datetime.now(tz=UTC)
        with self._lock:
            job = self._jobs.get(job_id)
            if job is None:
                return
            job.status = "succeeded"
            job.finished_at = now
            job.result = dict(result)
            job.error_code = None
            job.error_message = None
            job.error_traceback = None

    def _mark_failed(self, job_id: str, exc: Exception) -> None:
        """Transition a job to failed state and store diagnostics."""
        now = datetime.now(tz=UTC)
        error_code = getattr(exc, "error_code", "internal_error")
        if not isinstance(exc, AlphaLabError):
            error_code = "internal_error"
        with self._lock:
            job = self._jobs.get(job_id)
            if job is None:
                return
            job.status = "failed"
            job.finished_at = now
            job.result = None
            job.error_code = str(error_code)
            job.error_message = str(exc)
            job.error_traceback = "".join(
                traceback.format_exception(type(exc), exc, exc.__traceback__)
            )
