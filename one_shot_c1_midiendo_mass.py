from __future__ import annotations

from typing import Any


def enqueue_mass(classroom: Any, bridge_queue: Any) -> dict[str, Any]:
    # La cola masiva anterior de C1 queda desactivada. Este arranque encola únicamente
    # los cinco estudiantes indicados por el docente para C3: Evaluación semanal de matrices.
    from one_shot_c3_matrices_mass import enqueue_mass as enqueue_c3_mass

    return enqueue_c3_mass(classroom, bridge_queue)
