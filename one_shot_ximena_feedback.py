from __future__ import annotations

from typing import Any


COMMENT = """He revisado tu estado de entrega en esta actividad.

LO QUE HICISTE BIEN:
En esta oportunidad no se cuenta con una evidencia presentada que permita reconocer logros específicos de aprendizaje en la actividad.

LO QUE DEBES MEJORAR:
No se presentó evidencia de trabajo, por lo que no es posible valorar tu proceso ni verificar el desarrollo de los aprendizajes propuestos. Estás cursando quinto año de secundaria, una etapa en la que asumir con mayor autonomía tus responsabilidades académicas es especialmente importante. Cumplir con los compromisos, organizar tus tiempos y atender los plazos establecidos son hábitos que trascienden el colegio y serán valiosos en tus estudios posteriores, en el trabajo y en distintos aspectos de tu vida adulta.

SUGERENCIAS:
Toma esta situación como una oportunidad para fortalecer tu organización, constancia y responsabilidad personal frente a tus compromisos académicos. En las próximas actividades procura revisar oportunamente las indicaciones, organizar tus tiempos y presentar las evidencias dentro del plazo establecido.

Tu calificación es 0 - (C). Debido a que el sistema de registro ya se encuentra cerrado, esta calificación queda como definitiva para esta actividad.""".strip()


def enqueue_once(classroom: Any, bridge_queue: Any) -> dict[str, Any]:
    # Solo estudiantes de 5.º B que siguen con nota 0 Y no tienen evidencia adjunta.
    # Se mantiene 0/C, se publica retroalimentación formativa y se devuelve la entrega.
    from one_shot_zero_grade_inspect import inspect_zeroes

    payload = inspect_zeroes(classroom)
    rows = [r for r in payload.get("rows", []) if not (r.get("attachments") or [])]

    queued = []
    for row in rows:
        submission_id = str(row.get("submission_id") or "")
        course_id = str(row.get("course_id") or "")
        course_work_id = str(row.get("course_work_id") or "")
        submission_url = str(row.get("submission_url") or "")
        if not all((submission_id, course_id, course_work_id, submission_url)):
            continue

        # Evita volver a encolar exactamente el mismo comentario si ya existe un job equivalente.
        prior = [
            j for j in bridge_queue.matching(
                course_id=course_id,
                course_work_id=course_work_id,
                submission_id=submission_id,
                operation="post_private_comment",
            )
            if str(getattr(j, "comment", "") or "").strip() == COMMENT
            and getattr(j, "grade", None) == 0.0
            and getattr(j, "return_after_comment", False)
            and getattr(j, "status", "") not in {"failed", "cancelled"}
        ]
        if prior:
            print(
                f"ZERO_EVIDENCE_ALREADY_QUEUED: {row.get('student_name')} job={prior[0].id} status={prior[0].status}",
                flush=True,
            )
            continue

        job = bridge_queue.enqueue(
            course_id=course_id,
            course_work_id=course_work_id,
            submission_id=submission_id,
            submission_url=submission_url,
            comment=COMMENT,
            grade=0,
            return_after_comment=True,
            operation="post_private_comment",
        )
        queued.append({"student_name": row.get("student_name"), "job_id": job.id, "guard_job_id": job.guard_job_id})
        print(
            f"ZERO_EVIDENCE_ENQUEUED: {row.get('student_name')} grade=0 job={job.id} guard={job.guard_job_id}",
            flush=True,
        )

    print(f"ZERO_EVIDENCE_READY: {len(queued)} trabajo(s) encolado(s).", flush=True)
    return {
        "queued": bool(queued),
        "job_id": queued[0]["job_id"] if queued else None,
        "course_name": "MATE 5TO - B",
        "student_name": f"ZERO_EVIDENCE:{len(queued)}",
        "count": len(queued),
        "jobs": queued,
    }
