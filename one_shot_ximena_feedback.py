from __future__ import annotations

from typing import Any


def enqueue_once(classroom: Any, bridge_queue: Any) -> dict[str, Any]:
    """Inspección temporal de C1: FICHA DE MIDIENDO NUESTRO AVANCE en 5.º B.

    No encola ni modifica Classroom. Solo deja en logs el estado, notas y adjuntos
    de todas las entregas para poder revisar evidencia y preparar retroalimentación
    individual antes de activar la cola masiva.
    """
    from one_shot_midiendo_inspect import inspect

    payload = inspect(classroom)
    rows = payload.get("rows") or []
    course = payload.get("course") or {}
    work = payload.get("coursework") or {}
    return {
        "queued": False,
        "job_id": None,
        "course_name": course.get("name"),
        "student_name": f"MIDIENDO_INSPECT:{len(rows)}",
        "count": len(rows),
        "course_work_title": work.get("title"),
    }
