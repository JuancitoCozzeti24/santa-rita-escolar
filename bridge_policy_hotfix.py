from __future__ import annotations

from typing import Any


def install() -> None:
    """Endurece el contrato del Bridge sin reescribir la cola histórica.

    Reglas:
    - Toda nota cuantitativa enviada al Bridge exige comentario privado.
    - Toda nota cuantitativa fuerza devolución de la entrega.
    - Una lectura-guardia válida ya no bloquea una retroalimentación nueva solo
      porque existan comentarios privados anteriores. La deduplicación exacta la
      realiza el content script antes de pulsar Enviar/Publicar.
    - Los fallos del navegador se registran con su mensaje exacto para no volver
      a diagnosticar a ciegas cuando Classroom cambie su DOM.
    """
    try:
        from bridge import ClassroomBridgeQueue
    except Exception:
        return

    if getattr(ClassroomBridgeQueue, "_sieroom_triple_contract_r62", False):
        return

    original_enqueue = ClassroomBridgeQueue.enqueue
    original_mark_completed = ClassroomBridgeQueue.mark_completed
    original_mark_failed = ClassroomBridgeQueue.mark_failed

    def enqueue_hardened(self: Any, *args: Any, **kwargs: Any):
        operation = str(kwargs.get("operation") or "post_private_comment").strip().lower()
        grade = kwargs.get("grade")
        comment = str(kwargs.get("comment") or "").strip()

        if operation == "post_private_comment" and grade is not None:
            if not comment:
                raise ValueError(
                    "Contrato SieRoom: toda nota cuantitativa requiere comentario privado; "
                    "el trabajo no fue encolado."
                )
            kwargs["return_after_comment"] = True

        return original_enqueue(self, *args, **kwargs)

    def mark_completed_hardened(
        self: Any,
        job_id: str,
        classroom_result: dict[str, Any] | None = None,
        bridge_result: dict[str, Any] | None = None,
    ):
        before = self.get(job_id)
        guard_for_job_id = getattr(before, "guard_for_job_id", None) if before else None

        result = original_mark_completed(
            self,
            job_id,
            classroom_result=classroom_result,
            bridge_result=bridge_result,
        )

        # El servidor ya validó que la lectura corresponde al alumno/entrega.
        # Si había comentarios previos, permitimos continuar: puede tratarse de
        # una reentrega corregida. El content script evita publicar dos veces el
        # MISMO comentario mediante comparación normalizada/fingerprints.
        if guard_for_job_id:
            with self._lock:
                target = self._jobs.get(guard_for_job_id)
                if target and target.status == "blocked_existing_comment":
                    target.status = "queued"
                    target.error = None
                    target.guard_result = bridge_result or {}
                    target.updated_at = result.updated_at

        return result

    def mark_failed_hardened(
        self: Any,
        job_id: str,
        error: str,
        bridge_result: dict[str, Any] | None = None,
    ):
        before = self.get(job_id)
        print(
            "SIEROOM_BRIDGE_EXACT_FAILURE: "
            f"job={job_id} operation={getattr(before, 'operation', None)} "
            f"error={error!r} result={bridge_result!r}",
            flush=True,
        )
        return original_mark_failed(
            self,
            job_id,
            error,
            bridge_result=bridge_result,
        )

    ClassroomBridgeQueue.enqueue = enqueue_hardened
    ClassroomBridgeQueue.mark_completed = mark_completed_hardened
    ClassroomBridgeQueue.mark_failed = mark_failed_hardened
    setattr(ClassroomBridgeQueue, "_sieroom_triple_contract_r62", True)


install()
