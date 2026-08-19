from __future__ import annotations

from dataclasses import dataclass, field, asdict
from datetime import datetime, timezone, timedelta
from threading import RLock
from typing import Any
from uuid import uuid4


def _now() -> datetime:
    return datetime.now(timezone.utc)


@dataclass
class BridgeJob:
    id: str
    course_id: str
    course_work_id: str
    submission_id: str
    submission_url: str
    comment: str
    grade: float | None = None
    return_after_comment: bool = False
    status: str = "queued"
    created_at: datetime = field(default_factory=_now)
    updated_at: datetime = field(default_factory=_now)
    claimed_until: datetime | None = None
    bridge_result: dict[str, Any] | None = None
    classroom_result: dict[str, Any] | None = None
    error: str | None = None

    def public(self) -> dict[str, Any]:
        raw = asdict(self)
        for key in ("created_at", "updated_at", "claimed_until"):
            value = raw.get(key)
            raw[key] = value.isoformat() if value else None
        return raw


class ClassroomBridgeQueue:
    """Cola en memoria para el puente local del navegador.

    Render Free usa un único proceso en este proyecto. La cola está pensada para
    trabajos inmediatos y deliberadamente no persiste secretos/cookies de Google.
    """

    def __init__(self) -> None:
        self._lock = RLock()
        self._jobs: dict[str, BridgeJob] = {}

    def enqueue(
        self,
        *,
        course_id: str,
        course_work_id: str,
        submission_id: str,
        submission_url: str,
        comment: str,
        grade: float | None = None,
        return_after_comment: bool = False,
    ) -> BridgeJob:
        comment = str(comment or "").strip()
        if not comment:
            raise ValueError("El comentario privado no puede estar vacío.")
        job = BridgeJob(
            id=str(uuid4()),
            course_id=str(course_id),
            course_work_id=str(course_work_id),
            submission_id=str(submission_id),
            submission_url=str(submission_url),
            comment=comment,
            grade=float(grade) if grade is not None else None,
            return_after_comment=bool(return_after_comment),
        )
        with self._lock:
            self._jobs[job.id] = job
        return job

    def get(self, job_id: str) -> BridgeJob | None:
        with self._lock:
            return self._jobs.get(str(job_id))

    def recent(self, limit: int = 30) -> list[BridgeJob]:
        with self._lock:
            return sorted(self._jobs.values(), key=lambda j: j.created_at, reverse=True)[: max(1, min(limit, 100))]

    def stats(self) -> dict[str, int]:
        counts: dict[str, int] = {}
        with self._lock:
            for job in self._jobs.values():
                counts[job.status] = counts.get(job.status, 0) + 1
        # Compatibilidad: conservamos los contadores por estado, pero añadimos
        # un resumen explícito para que la extensión no confunda el historial
        # (completed/failed/cancelled) con trabajos que siguen realmente en cola.
        queued = counts.get("queued", 0)
        claimed = counts.get("claimed", 0)
        counts["work_remaining"] = queued + claimed
        counts["active_total"] = queued + claimed
        counts["history_total"] = sum(
            counts.get(k, 0) for k in (
                "completed", "failed", "cancelled",
                "comment_posted", "comment_posted_followup_failed",
            )
        )
        return counts

    def reset_active(self, *, retry_failed: bool = False) -> dict[str, Any]:
        """Desatasca la cola sin borrar trabajos pendientes válidos.

        - Todo trabajo `claimed` vuelve inmediatamente a `queued`, sin esperar
          a que venza el lease de 90 s.
        - Los trabajos ya `queued` se conservan tal cual.
        - Por defecto NO reintenta `failed`, para evitar bucles de errores
          permanentes. Puede pedirse explícitamente con retry_failed=True.
        - No toca completed/cancelled ni borra el historial.

        La publicación DOM del puente es idempotente por texto: content.js
        comprueba si el comentario ya aparece antes de volver a enviarlo.
        """
        now = _now()
        released_claimed: list[str] = []
        retried_failed: list[str] = []
        with self._lock:
            for job in self._jobs.values():
                if job.status == "claimed":
                    job.status = "queued"
                    job.claimed_until = None
                    job.error = None
                    job.updated_at = now
                    released_claimed.append(job.id)
                elif retry_failed and job.status == "failed":
                    job.status = "queued"
                    job.claimed_until = None
                    job.error = None
                    job.updated_at = now
                    retried_failed.append(job.id)
        return {
            "ok": True,
            "released_claimed": released_claimed,
            "retried_failed": retried_failed,
            "released_count": len(released_claimed),
            "retried_failed_count": len(retried_failed),
            "queue": self.stats(),
        }

    def next_job(self, claim_seconds: int = 90) -> BridgeJob | None:
        now = _now()
        with self._lock:
            # Recupera claims vencidos para tolerar pestañas cerradas o recargas.
            for job in self._jobs.values():
                if job.status == "claimed" and job.claimed_until and job.claimed_until < now:
                    job.status = "queued"
                    job.claimed_until = None
                    job.updated_at = now
            candidates = [j for j in self._jobs.values() if j.status == "queued"]
            if not candidates:
                return None
            job = sorted(candidates, key=lambda j: j.created_at)[0]
            job.status = "claimed"
            job.claimed_until = now + timedelta(seconds=claim_seconds)
            job.updated_at = now
            return job

    def mark_comment_posted(self, job_id: str, bridge_result: dict[str, Any] | None = None) -> BridgeJob:
        with self._lock:
            job = self._jobs[str(job_id)]
            job.status = "comment_posted"
            job.bridge_result = bridge_result or {}
            job.claimed_until = None
            job.updated_at = _now()
            return job

    def mark_completed(self, job_id: str, classroom_result: dict[str, Any] | None = None) -> BridgeJob:
        with self._lock:
            job = self._jobs[str(job_id)]
            job.status = "completed"
            job.classroom_result = classroom_result or {}
            job.error = None
            job.claimed_until = None
            job.updated_at = _now()
            return job

    def mark_partial_failure(self, job_id: str, error: str, classroom_result: dict[str, Any] | None = None) -> BridgeJob:
        with self._lock:
            job = self._jobs[str(job_id)]
            job.status = "comment_posted_followup_failed"
            job.error = str(error)
            job.classroom_result = classroom_result or {}
            job.claimed_until = None
            job.updated_at = _now()
            return job

    def mark_failed(self, job_id: str, error: str, bridge_result: dict[str, Any] | None = None) -> BridgeJob:
        with self._lock:
            job = self._jobs[str(job_id)]
            job.status = "failed"
            job.error = str(error)
            job.bridge_result = bridge_result or {}
            job.claimed_until = None
            job.updated_at = _now()
            return job

    def retry(self, job_id: str) -> BridgeJob:
        with self._lock:
            job = self._jobs[str(job_id)]
            job.status = "queued"
            job.error = None
            job.claimed_until = None
            job.updated_at = _now()
            return job

    def cancel(self, job_id: str) -> BridgeJob:
        with self._lock:
            job = self._jobs[str(job_id)]
            if job.status in {"completed", "comment_posted"}:
                raise ValueError("Ese trabajo ya fue procesado y no puede cancelarse.")
            job.status = "cancelled"
            job.claimed_until = None
            job.updated_at = _now()
            return job
