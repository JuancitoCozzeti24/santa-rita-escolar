from __future__ import annotations

import unicodedata
from typing import Any


TARGET_ASSIGNMENT = "SUBIR AQUÍ FICHA INTRO MATRICES"
TARGET_STUDENT_TOKENS = ("FATIMA", "MUJICA")

FEEDBACK = """Fátima,
He revisado tu trabajo de manera detallada, y he podido observar lo siguiente:

LO QUE HICISTE BIEN:
Resolviste correctamente los ejercicios 1 al 7: orden, elementos, diagonales, clasificación y trazas. En el ejercicio 8 identificaste correctamente que los incisos c y d eran falsos.

LO QUE DEBES MEJORAR:
Ejercicio 8 – inciso c:
Tu respuesta/procedimiento: marcaste F, correctamente, pero no escribiste la corrección.
Error detectado: la respuesta quedó incompleta porque faltó corregir la afirmación sobre la traza.
Procedimiento correcto: la traza solo se define en matrices cuadradas y se obtiene sumando los elementos de la diagonal principal.
Resultado correcto: la traza se define solo para matrices cuadradas.

Ejercicio 8 – inciso d:
Tu respuesta/procedimiento: marcaste F, correctamente, pero no escribiste la corrección.
Error detectado: la respuesta quedó incompleta porque faltó interpretar el orden 3×4.
Procedimiento correcto: en m×n, el primer número indica filas y el segundo, columnas.
Resultado correcto: una matriz 3×4 tiene 3 filas y 4 columnas.

SUGERENCIAS:
Cuando marques F, escribe también la afirmación correcta para demostrar completamente tu comprensión.

Tu calificación es 18 - (A)""".strip()


def _norm(value: Any) -> str:
    text = unicodedata.normalize("NFD", str(value or ""))
    text = "".join(ch for ch in text if unicodedata.category(ch) != "Mn")
    return " ".join(text.upper().split())


def enqueue_once(classroom: Any, bridge_queue: Any) -> dict[str, Any]:
    """Encola SOLO el comentario real de Fátima Mujica para la ficha intro matrices.

    No cambia nota ni devuelve la entrega: esos dos pasos ya fueron confirmados previamente
    mediante la API de Classroom. Esta función existe únicamente para probar el tramo pendiente
    del Bridge: lectura del panel privado -> publicación del comentario estructurado.
    """
    target_assignment_norm = _norm(TARGET_ASSIGNMENT)
    candidates: list[dict[str, Any]] = []

    for course in classroom.list_courses(active_only=True):
        course_id = str(course.get("id") or "")
        if not course_id:
            continue
        try:
            works = classroom.list_coursework(course_id, include_drafts=True)
        except Exception:
            continue
        work_matches = [w for w in works if _norm(w.get("title")) == target_assignment_norm]
        if not work_matches:
            continue

        try:
            students = classroom.list_students(course_id)
        except Exception:
            continue
        student_matches = []
        for student in students:
            haystack = _norm(f"{student.get('name') or ''} {student.get('email') or ''}")
            if all(token in haystack for token in TARGET_STUDENT_TOKENS):
                student_matches.append(student)
        if len(student_matches) != 1:
            continue

        student = student_matches[0]
        user_id = str(student.get("userId") or "")
        if not user_id:
            continue

        for work in work_matches:
            work_id = str(work.get("id") or "")
            if not work_id:
                continue
            submissions = classroom.list_submissions(course_id, work_id)
            sub_matches = [s for s in submissions if str(s.get("userId") or "") == user_id]
            if len(sub_matches) != 1:
                continue
            sub = sub_matches[0]
            submission_id = str(sub.get("id") or "")
            url = str(sub.get("alternateLink") or "")
            if submission_id and url:
                candidates.append({
                    "course_id": course_id,
                    "course_name": course.get("name"),
                    "course_section": course.get("section"),
                    "course_work_id": work_id,
                    "submission_id": submission_id,
                    "submission_url": url,
                    "student_name": student.get("name"),
                })

    # Seguridad: nunca adivinar entre varios destinos.
    unique = {(c["course_id"], c["course_work_id"], c["submission_id"]): c for c in candidates}
    candidates = list(unique.values())
    if len(candidates) != 1:
        raise RuntimeError(
            "FATIMA_TEST_TARGET_NOT_UNIQUE: se esperaba exactamente una entrega de Fátima Mujica "
            f"para '{TARGET_ASSIGNMENT}' y se encontraron {len(candidates)}."
        )

    target = candidates[0]
    existing = [
        j for j in bridge_queue.recent(100)
        if j.operation == "post_private_comment"
        and j.course_id == target["course_id"]
        and j.course_work_id == target["course_work_id"]
        and j.submission_id == target["submission_id"]
        and str(j.comment or "").strip() == FEEDBACK
    ]
    if existing:
        print(
            f"FATIMA_BRIDGE_TEST: ya existe job {existing[0].id} estado={existing[0].status}; no se duplica.",
            flush=True,
        )
        return {"queued": False, "job_id": existing[0].id, "status": existing[0].status, **target}

    job = bridge_queue.enqueue(
        course_id=target["course_id"],
        course_work_id=target["course_work_id"],
        submission_id=target["submission_id"],
        submission_url=target["submission_url"],
        comment=FEEDBACK,
        grade=None,
        return_after_comment=False,
        operation="post_private_comment",
    )
    print(
        "FATIMA_BRIDGE_TEST: comentario encolado SOLO para "
        f"{target['student_name']} | {target['course_name']} {target['course_section'] or ''} | "
        f"job={job.id} guard={job.guard_job_id} estado={job.status}",
        flush=True,
    )
    return {"queued": True, "job_id": job.id, "guard_job_id": job.guard_job_id, **target}
