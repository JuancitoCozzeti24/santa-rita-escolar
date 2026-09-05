from __future__ import annotations

from typing import Any


def enqueue_once(classroom: Any, bridge_queue: Any) -> dict[str, Any]:
    # Reutilizamos el hook puntual existente para la prueba masiva solicitada.
    # Solo encola entregas de 5.º B que siguen con nota 0 Y tienen evidencia adjunta.
    from one_shot_zero_grade_mass import enqueue_mass

    payload = enqueue_mass(classroom, bridge_queue)
    return {
        "queued": bool(payload.get("queued")),
        "job_id": None,
        "course_name": "MATE 5TO - B",
        "student_name": f"ZERO_GRADE_MASS:{payload.get('count', 0)}",
    }
