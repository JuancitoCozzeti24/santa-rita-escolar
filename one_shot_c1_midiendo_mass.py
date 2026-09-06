from __future__ import annotations

from typing import Any


def enqueue_mass(classroom: Any, bridge_queue: Any) -> dict[str, Any]:
    from one_shot_c2_classroom_api_finalize import execute
    return execute(classroom, bridge_queue)
