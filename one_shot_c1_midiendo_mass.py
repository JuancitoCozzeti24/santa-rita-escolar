from __future__ import annotations

from typing import Any


def enqueue_mass(classroom: Any, bridge_queue: Any) -> dict[str, Any]:
    from one_shot_c3_prob_5b_grade_feedback import execute
    return execute(classroom, bridge_queue)
