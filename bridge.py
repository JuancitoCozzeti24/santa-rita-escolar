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
    comment: str = ""
    operation: str = "post_private_comment"
    grade: float | None = None
    return_after_comment: bool = False
    status: str = "queued"
    created_at: datetime = field(default_factory=_now)
    updated_at: datetime = field(default_factory=_now)
    claimed_until: datetime | None = None
    bridge_result: dict[str, Any] | None = None
    classroom_result: dict[str, Any] | None = None
    error: str | None = None
    guard_for_job_id: str | None = None
    guard_job_id: str | None = None
    guard_result: dict[str, Any] | None = None

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

    Regla de seguridad de comentarios privados:
    cualquier trabajo que vaya a PUBLICAR un comentario se bloquea primero y
    encola una lectura real de la misma entrega. Solo si esa lectura devuelve
    exactamente cero comentarios privados se libera la publicación. Si ya existe
    uno o más comentarios, el trabajo queda bloqueado y no se escribe nada.
    """

    def __init__(self) -> None:
        self._lock = RLock()
        self._jobs: dict[str, BridgeJob] = {}

    def _new_comment_guard(self, target: BridgeJob) -> BridgeJob:
        return BridgeJob(
            id=str(uuid4()),
            course_id=target.course_id,
            course_work_id=target.course_work_id,
            submission_id=target.submission_id,
            submission_url=target.submission_url,
            operation="read_private_comments",
            status="queued",
            guard_for_job_id=target.id,
        )

    def enqueue(
        self,
        *,
        course_id: str,
        course_work_id: str,
        submission_id: str,
        submission_url: str,
        comment: str = "",
        operation: str = "post_private_comment",
        grade: float | None = None,
        return_after_comment: bool = False,
    ) -> BridgeJob:
        operation = str(operation or "post_private_comment").strip().lower()
        if operation not in {"post_private_comment", "read_private_comments", "cleanup_private_comment_duplicates"}:
            raise ValueError(f"Operación de Bridge no soportada: {operation}")
        comment = str(comment or "").strip()
        if (
            operation == "post_private_comment"
            and not comment
            and grade is None
            and not return_after_comment
        ):
            raise ValueError("El trabajo del puente necesita comentario, nota o devolución.")

        requires_comment_guard = operation == "post_private_comment" and bool(comment)
        job = BridgeJob(
            id=str(uuid4()),
            course_id=str(course_id),
            course_work_id=str(course_work_id),
            submission_id=str(submission_id),
            submission_url=str(submission_url),
            comment=comment,
            operation=operation,
            grade=float(grade) if grade is not None else None,
            return_after_comment=bool(return_after_comment),
            status="waiting_comment_guard" if requires_comment_guard else "queued",
        )

        with self._lock:
            self._jobs[job.id] = job
            if requires_comment_guard:
                guard = self._new_comment_guard(job)
                job.guard_job_id = guard.id
                job.updated_at = _now()
                self._jobs[guard.id] = guard
        return job

    def get(self, job_id: str) -> BridgeJob | None:
        with self._lock:
            return self._jobs.get(str(job_id))

    def recent(self, limit: int = 30) -> list[BridgeJob]:
        with self._lock:
            return sorted(self._jobs.values(), key=lambda j: j.created_at, reverse=True)[: max(1, min(limit, 100))]

    def matching(
        self,
        *,
        course_id: str | None = None,
        course_work_id: str | None = None,
        submission_id: str | None = None,
        operation: str | None = None,
        statuses: set[str] | None = None,
    ) -> list[BridgeJob]:
        """Devuelve todos los trabajos coincidentes, sin el límite de `recent`."""
        with self._lock:
            jobs = list(self._jobs.values())
        if course_id is not None:
            jobs = [j for j in jobs if j.course_id == str(course_id)]
        if course_work_id is not None:
            jobs = [j for j in jobs if j.course_work_id == str(course_work_id)]
        if submission_id is not None:
            jobs = [j for j in jobs if j.submission_id == str(submission_id)]
        if operation is not None:
            jobs = [j for j in jobs if j.operation == str(operation)]
        if statuses is not None:
            jobs = [j for j in jobs if j.status in statuses]
        return sorted(jobs, key=lambda j: (j.updated_at, j.created_at), reverse=True)

    def stats(self) -> dict[str, int]:
        counts: dict[str, int] = {}
        with self._lock:
            for job in self._jobs.values():
                counts[job.status] = counts.get(job.status, 0) + 1
        # Compatibilidad: conservamos los contadores por estado, pero añadimos
        # un resumen explícito para que la extensión no confunda el historial
        # con trabajos que siguen realmente pendientes.
        queued = counts.get("queued", 0)
        claimed = counts.get("claimed", 0)
        waiting_guard = counts.get("waiting_comment_guard", 0)
        counts["work_remaining"] = queued + claimed + waiting_guard
        counts["active_total"] = queued + claimed + waiting_guard
        counts["history_total"] = sum(
            counts.get(k, 0) for k in (
                "completed", "failed", "cancelled", "blocked_existing_comment",
                "comment_posted", "comment_posted_followup_failed",
            )
        )
        return counts

    def reset_active(self, *, retry_failed: bool = False) -> dict[str, Any]:
        """Desatasca la cola sin borrar trabajos pendientes válidos.

        - Todo trabajo `claimed` vuelve inmediatamente a `queued`, sin esperar
          a que venza el lease de 90 s.
        - Los trabajos `queued` y `waiting_comment_guard` se conservan.
        - Por defecto NO reintenta `failed`, para evitar bucles de errores
          permanentes. Puede pedirse explícitamente con retry_failed=True.
        - No toca completed/cancelled ni borra el historial.

        Los comentarios no dependen de idempotencia por texto: antes de cada
        publicación hay una lectura obligatoria de la entrega. Si existe cualquier
        comentario privado previo, la publicación queda bloqueada.
        """
        now = _now()
        released_claimed: list[str] = []
        retried_failed: list[str] = []
        with self._lock:
            for job in list(self._jobs.values()):
                if job.status == "claimed":
                    job.status = "queued"
                    job.claimed_until = None
                    job.error = None
                    job.updated_at = now
                    released_claimed.append(job.id)
                elif retry_failed and job.status == "failed":
                    # Las lecturas creadas como guardia pertenecen al comentario
                    # padre; no se reintentan aparte para evitar dos guardias en carrera.
                    if job.guard_for_job_id:
                        continue
                    if job.operation == "post_private_comment" and job.comment:
                        guard = self._new_comment_guard(job)
                        job.status = "waiting_comment_guard"
                        job.guard_job_id = guard.id
                        job.guard_result = None
                        self._jobs[guard.id] = guard
                    else:
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

    def next_job(
        self,
        claim_seconds: int = 300,
        allowed_operations: set[str] | None = None,
    ) -> BridgeJob | None:
        now = _now()
        with self._lock:
            # Recupera claims vencidos para tolerar pestañas cerradas o recargas.
            for job in self._jobs.values():
                if job.status == "claimed" and job.claimed_until and job.claimed_until < now:
                    job.status = "queued"
                    job.claimed_until = None
                    job.updated_at = now
            candidates = [j for j in self._jobs.values() if j.status == "queued"]
            if allowed_operations is not None:
                candidates = [j for j in candidates if j.operation in allowed_operations]
            if not candidates:
                return None
            job = sorted(candidates, key=lambda j: j.created_at)[0]
            job.status = "claimed"
            job.claimed_until = now + timedelta(seconds=claim_seconds)
            job.updated_at = now
            return job

    def has_queued_operation(self, operation: str) -> bool:
        operation = str(operation or "").strip().lower()
        with self._lock:
            return any(
                job.status == "queued" and job.operation == operation
                for job in self._jobs.values()
            )

    def mark_comment_posted(self, job_id: str, bridge_result: dict[str, Any] | None = None) -> BridgeJob:
        with self._lock:
            job = self._jobs[str(job_id)]
            job.status = "comment_posted"
            job.bridge_result = bridge_result or {}
            job.claimed_until = None
            job.updated_at = _now()
            return job

    def mark_completed(
        self,
        job_id: str,
        classroom_result: dict[str, Any] | None = None,
        bridge_result: dict[str, Any] | None = None,
    ) -> BridgeJob:
        with self._lock:
            job = self._jobs[str(job_id)]
            job.status = "completed"
            job.classroom_result = classroom_result or {}
            if bridge_result is not None:
                job.bridge_result = bridge_result
            job.error = None
            job.claimed_until = None
            job.updated_at = _now()

            # Si esta lectura fue creada como guardia de un comentario, decide
            # inmediatamente si la escritura puede salir de espera.
            if job.operation == "read_private_comments" and job.guard_for_job_id:
                target = self._jobs.get(job.guard_for_job_id)
                if target and target.status == "waiting_comment_guard":
                    result = bridge_result or {}
                    count = result.get("count")
                    comments = result.get("comments")
                    target.guard_result = result
                    target.updated_at = _now()
                    valid_zero = (
                        isinstance(count, int)
                        and not isinstance(count, bool)
                        and count == 0
                        and isinstance(comments, list)
                        and len(comments) == 0
                    )
                    if valid_zero:
                        target.status = "queued"
                        target.error = None
                    else:
                        detected = count if isinstance(count, int) and not isinstance(count, bool) else "uno o más"
                        target.status = "blocked_existing_comment"
                        target.error = (
                            "existing_private_comment_guard: se detectaron "
                            f"{detected} comentario(s) privado(s) previo(s) en esta entrega; "
                            "por política SieRoom no publicará otro comentario."
                        )
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

            # Un fallo de la lectura de guardia nunca libera el comentario.
            # El padre falla también y solo podrá reintentarse creando/verificando
            # una nueva lectura. Así el comportamiento es fail-closed.
            if job.operation == "read_private_comments" and job.guard_for_job_id:
                target = self._jobs.get(job.guard_for_job_id)
                if target and target.status == "waiting_comment_guard":
                    target.status = "failed"
                    target.error = f"comment_guard_failed: {error}"
                    target.guard_result = bridge_result or {}
                    target.updated_at = _now()
            return job

    def retry(self, job_id: str) -> BridgeJob:
        with self._lock:
            job = self._jobs[str(job_id)]
            job.error = None
            job.claimed_until = None
            job.updated_at = _now()

            # Si se reintenta directamente una lectura-guardia, volvemos a poner
            # al comentario padre en espera y reutilizamos esa misma guardia.
            if job.operation == "read_private_comments" and job.guard_for_job_id:
                target = self._jobs.get(job.guard_for_job_id)
                if target and target.operation == "post_private_comment" and target.comment:
                    target.status = "waiting_comment_guard"
                    target.guard_job_id = job.id
                    target.guard_result = None
                    target.error = None
                    target.updated_at = _now()
                job.status = "queued"
                return job

            if job.operation == "post_private_comment" and job.comment:
                guard = self._new_comment_guard(job)
                job.status = "waiting_comment_guard"
                job.guard_job_id = guard.id
                job.guard_result = None
                self._jobs[guard.id] = guard
            else:
                job.status = "queued"
            return job

    def cancel(self, job_id: str) -> BridgeJob:
        with self._lock:
            job = self._jobs[str(job_id)]
            if job.status in {"completed", "comment_posted"}:
                raise ValueError("Ese trabajo ya fue procesado y no puede cancelarse.")
            job.status = "cancelled"
            job.claimed_until = None
            job.updated_at = _now()

            # Si se cancela un comentario que aún espera su lectura de guardia,
            # cancelamos también esa lectura si todavía no se ha procesado.
            if job.guard_job_id:
                guard = self._jobs.get(job.guard_job_id)
                if guard and guard.status in {"queued", "waiting_comment_guard"}:
                    guard.status = "cancelled"
                    guard.claimed_until = None
                    guard.updated_at = _now()

            # Si se cancela directamente una lectura-guardia, su comentario padre
            # tampoco puede quedar esperando indefinidamente.
            if job.guard_for_job_id:
                target = self._jobs.get(job.guard_for_job_id)
                if target and target.status == "waiting_comment_guard":
                    target.status = "cancelled"
                    target.error = "comment_guard_cancelled"
                    target.updated_at = _now()
            return job