from __future__ import annotations

from typing import Any


def enqueue_mass(classroom: Any, bridge_queue: Any) -> dict[str, Any]:
    # Las colas Classroom quedan desactivadas. Este arranque solo inspecciona C3 y SIEWeb.
    import sys
    main = sys.modules.get('__main__')
    namespace = vars(main) if main is not None else {}
    sieweb = namespace.get('sieweb')
    if sieweb is None:
        raise RuntimeError('C3_SIEWEB_INSPECT: cliente SIEWeb no disponible.')
    from one_shot_c3_sieweb_inspect import inspect
    result = inspect(classroom, sieweb)
    return {
        'queued': False,
        'count': 0,
        'jobs': [],
        'course_name': result.get('course_name'),
        'work': result.get('work'),
        'inspection_count': result.get('count'),
    }
