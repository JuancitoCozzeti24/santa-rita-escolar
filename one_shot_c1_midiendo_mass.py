from __future__ import annotations

import sys
from typing import Any


def enqueue_mass(classroom: Any, bridge_queue: Any) -> dict[str, Any]:
    main = sys.modules.get('__main__')
    ns = vars(main) if main is not None else {}
    sieweb = ns.get('sieweb')
    if sieweb is None:
        raise RuntimeError('C3_PROB_SIEWEB: cliente SIEWeb no disponible en startup.')

    from one_shot_c3_prob_5b_sieweb_write import execute as sync_sieweb
    result = sync_sieweb(classroom, sieweb)

    # El despliegue reinicia la cola en memoria. Reponer la retroalimentación C3 que
    # seguía pendiente evita perder los comentarios privados ya preparados.
    from one_shot_c3_prob_5b_grade_feedback import execute as restore_feedback
    feedback = restore_feedback(classroom, bridge_queue)
    result['feedback_queue_restored'] = feedback.get('count', 0)
    return result
