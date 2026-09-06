from __future__ import annotations

from typing import Any


def enqueue_mass(classroom: Any, bridge_queue: Any) -> dict[str, Any]:
    # Auditoría de pendientes con 0 de C2: Desarrollar tarea de determinantes (5B).
    # No encola todavía comentarios ni notas: primero identifica exactamente qué evidencias existen.
    from one_shot_c2_determinantes_audit import inspect
    return inspect(classroom)
