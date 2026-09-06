from __future__ import annotations

from typing import Any


def enqueue_mass(classroom: Any, bridge_queue: Any) -> dict[str, Any]:
    # Encola únicamente a estudiantes con 0 y sin evidencia en
    # C1: Tarea de Operaciones con Matrices (5B).
    from one_shot_c1_ops_zero_feedback import enqueue_zero_evidence
    return enqueue_zero_evidence(classroom, bridge_queue)
