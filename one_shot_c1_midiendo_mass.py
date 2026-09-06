from __future__ import annotations

from typing import Any


def enqueue_mass(classroom: Any, bridge_queue: Any) -> dict[str, Any]:
    # Seguridad: la cola anterior de C1 queda desactivada. Este arranque solo inspecciona
    # los cinco estudiantes que el docente indicó para C3: Evaluación semanal de matrices.
    from one_shot_c3_matrices_inspect import inspect

    result = inspect(classroom)
    return {
        "queued": False,
        "count": 0,
        "jobs": [],
        "course_name": result.get("course_name"),
        "work": result.get("course_work_title"),
        "inspection_count": result.get("count"),
    }
