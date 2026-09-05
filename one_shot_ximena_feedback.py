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
    """Encola únicamente alumnos sin evidencia cuyo 0 ya está asignado en Classroom.

    Estas entregas están en estado CREATED: el alumno nunca entregó trabajo, por lo
    que Classroom no ofrece botón Devolver/Enviar. El 0 ya figura tanto como
    draftGrade como assignedGrade. En consecuencia el Bridge solo publica el
    comentario formativo y deja intacta la calificación final 0/C; no intenta
    volver a escribir la nota ni devolver una entrega inexistente.
    """
    from one_shot_zero_grade_inspect import inspect_zeroes

    payload = inspect_zeroes(classroom)
    rows = []
    for row in payload.get("rows", []):
        if row.get("attachments") or []:
            continue
        if str(row.get("state") or "").upper() != "CREATED":
            continue
        try:
            draft = float(row.get("draftGrade"))
            assigned = float(row.get("assignedGrade"))
        except (TypeError, ValueError):
            continue
        if draft != 0.0 or assigned != 0.0:
            continue
        rows.append(row)

    queued = []
    for row in rows:
        submission_id = str(row.get("submission_id") or "")
        course_id = str(row.get("course_id") or "")
        course_work_id = str(row.get("course_work_id") or "")
        submission_url = str(row.get("submission_url") or "")
        if not all((submission_id, course_id, course_work_id, submission_url)):
            continue

        prior = [
            j for j in bridge_queue.matching(
                course_id=course_id,
                course_work_id=course_work_id,
                submission_id=submission_id,
                operation="post_private_comment",
            )
            if str(getattr(j, "comment", "") or "").strip() == COMMENT
            and getattr(j, "grade", None) is None
            and not getattr(j, "return_after_comment", False)
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
            grade=None,
            return_after_comment=False,
            operation="post_private_comment",
        )
        queued.append({"student_name": row.get("student_name"), "job_id": job.id, "guard_job_id": job.guard_job_id})
        print(
            f"ZERO_EVIDENCE_COMMENT_ONLY_ENQUEUED: {row.get('student_name')} assignedGrade=0 state=CREATED job={job.id} guard={job.guard_job_id}",
            flush=True,
        )

    print(f"ZERO_EVIDENCE_COMMENT_ONLY_READY: {len(queued)} trabajo(s) encolado(s).", flush=True)
    return {
        "queued": bool(queued),
        "job_id": queued[0]["job_id"] if queued else None,
        "course_name": "MATE 5TO - B",
        "student_name": f"ZERO_EVIDENCE_COMMENT_ONLY:{len(queued)}",
        "count": len(queued),
        "jobs": queued,
    }
