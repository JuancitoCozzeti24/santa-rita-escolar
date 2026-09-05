from __future__ import annotations

from typing import Any


def enqueue_once(classroom: Any, bridge_queue: Any) -> dict[str, Any]:
    # Fase segura: solo vuelve a escanear quiénes siguen con nota 0.
    # No encola ninguna escritura hasta revisar la evidencia disponible.
    from one_shot_zero_grade_inspect import inspect_zeroes

    payload = inspect_zeroes(classroom)
    return {
        "queued": False,
        "job_id": None,
        "course_name": "MATE 5TO - B",
        "student_name": f"ZERO_GRADE_RESCAN:{payload.get('count', 0)}",
    }
