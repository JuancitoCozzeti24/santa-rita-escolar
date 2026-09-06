from __future__ import annotations

import unicodedata
from typing import Any

TARGET_TITLE = "C1: Tarea de Operaciones con Matrices"


def _norm(value: Any) -> str:
    text = unicodedata.normalize("NFD", str(value or ""))
    text = "".join(ch for ch in text if unicodedata.category(ch) != "Mn")
    return " ".join(text.upper().split())


def _first_name(full_name: Any) -> str:
    parts = str(full_name or "Estudiante").strip().split()
    if not parts:
        return "Estudiante"
    # En Classroom los nombres de 5B suelen venir Nombre(s) + apellidos.
    return parts[0].title()


def _comment(full_name: str) -> str:
    name = _first_name(full_name)
    return f"""{name},
He revisado tu estado de entrega en la actividad C1: Tarea de Operaciones con Matrices.

LO QUE HICISTE BIEN:
En esta oportunidad no se cuenta con una evidencia presentada que permita reconocer logros específicos de aprendizaje en esta actividad.

LO QUE DEBES MEJORAR:
No presentaste evidencia de la tarea de Operaciones con Matrices, por lo que no es posible valorar tu procedimiento ni verificar el desarrollo de los aprendizajes propuestos. Estás cursando quinto año de secundaria, una etapa en la que asumir con mayor autonomía tus responsabilidades académicas es especialmente importante. Cumplir con los compromisos, organizar tus tiempos y atender los plazos establecidos son hábitos que trascienden el colegio y serán valiosos en tus estudios posteriores, en el trabajo y en distintos aspectos de tu vida adulta.

SUGERENCIAS:
Toma esta situación como una oportunidad para fortalecer tu organización, constancia y responsabilidad personal. En adelante procura revisar oportunamente las indicaciones de Classroom, organizar tus tiempos y presentar las evidencias dentro de los plazos establecidos.

Tu calificación es 0/20 - (C).""".strip()


def enqueue_zero_evidence(classroom: Any, bridge_queue: Any) -> dict[str, Any]:
    course = work = None
    wanted = _norm(TARGET_TITLE)
    for c in classroom.list_courses(active_only=True):
        hay = _norm(f"{c.get('name') or ''} {c.get('section') or ''}")
        if "MATE 5TO" not in hay or ("5TO - B" not in hay and "5TO B" not in hay):
            continue
        matches = [
            w for w in classroom.list_coursework(str(c.get("id") or ""), include_drafts=True)
            if _norm(w.get("title")) == wanted
        ]
        if len(matches) == 1:
            course, work = c, matches[0]
            break
    if not course or not work:
        raise RuntimeError("C1_OPS_ZERO: no se encontró de forma única la actividad exacta en 5B.")

    course_id = str(course.get("id") or "")
    work_id = str(work.get("id") or "")
    roster = classroom.list_students(course_id)
    by_user = {str(s.get("userId") or ""): s for s in roster}

    eligible = []
    jobs = []
    skipped = []

    for sub in classroom.list_submissions(course_id, work_id):
        st = by_user.get(str(sub.get("userId") or "")) or {}
        grade = sub.get("assignedGrade") if sub.get("assignedGrade") is not None else sub.get("draftGrade")
        attachments = sub.get("attachments") or []
        if grade is None:
            continue
        try:
            is_zero = float(grade) == 0.0
        except Exception:
            is_zero = False
        if not is_zero:
            continue
        if attachments:
            skipped.append({"name": st.get("name"), "reason": "grade_zero_but_has_attachments", "count": len(attachments)})
            continue

        submission_id = str(sub.get("id") or "")
        submission_url = str(sub.get("alternateLink") or "")
        if not submission_id or not submission_url:
            skipped.append({"name": st.get("name"), "reason": "missing_submission_id_or_url"})
            continue

        full_name = str(st.get("name") or "Estudiante")
        comment = _comment(full_name)
        state = str(sub.get("state") or "")
        eligible.append({"name": full_name, "state": state, "grade": grade})

        prior = [
            j for j in bridge_queue.matching(
                course_id=course_id,
                course_work_id=work_id,
                submission_id=submission_id,
                operation="post_private_comment",
            )
            if str(getattr(j, "comment", "") or "").strip() == comment
            and getattr(j, "status", "") not in {"failed", "cancelled"}
        ]
        if prior:
            print(f"C1_OPS_ZERO_ALREADY_QUEUED: {full_name} job={prior[0].id} status={prior[0].status}", flush=True)
            continue

        # El 0 ya está registrado en Classroom. Para CREATED no existe entrega que devolver;
        # para RETURNED ya fue devuelta. R6.9.8 publica el comentario y conserva el cero.
        job = bridge_queue.enqueue(
            course_id=course_id,
            course_work_id=work_id,
            submission_id=submission_id,
            submission_url=submission_url,
            comment=comment,
            grade=None,
            return_after_comment=False,
            operation="post_private_comment",
        )
        jobs.append({
            "student": full_name,
            "state": state,
            "job_id": job.id,
            "guard_job_id": job.guard_job_id,
        })
        print(f"C1_OPS_ZERO_ENQUEUED: {full_name} state={state} grade=0 job={job.id} guard={job.guard_job_id}", flush=True)

    print(f"C1_OPS_ZERO_ELIGIBLE={eligible}", flush=True)
    print(f"C1_OPS_ZERO_SKIPPED={skipped}", flush=True)
    print(f"C1_OPS_ZERO_READY: {len(jobs)} comentario(s) encolado(s) para alumnos con 0 y sin evidencia.", flush=True)
    return {
        "queued": bool(jobs),
        "count": len(jobs),
        "jobs": jobs,
        "eligible": eligible,
        "skipped": skipped,
        "course_name": course.get("name"),
        "work": work.get("title"),
    }
