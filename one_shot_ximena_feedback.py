from __future__ import annotations

from typing import Any


def enqueue_once(classroom: Any, bridge_queue: Any) -> dict[str, Any]:
    # Reutilizamos el hook puntual existente SOLO para descubrir las entregas que
    # actualmente tienen nota 0. No se encola ninguna escritura durante esta fase.
    from one_shot_zero_grade_inspect import inspect_zeroes

    payload = inspect_zeroes(classroom)
    return {
        "queued": False,
        "job_id": None,
        "course_name": "MATE 5TO - B",
        "student_name": f"ZERO_GRADE_SCAN:{payload.get('count', 0)}",
    }
