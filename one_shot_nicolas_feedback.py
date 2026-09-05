from __future__ import annotations

import unicodedata
from typing import Any

TARGET_ASSIGNMENT = "SUBIR AQUÍ FICHA INTRO MATRICES"
TARGET_STUDENT_TOKENS = ("NICOLAS", "VARGAS")
TARGET_COURSE_TOKENS = ("MATE 5TO", "B")

FEEDBACK = """Nicolás,
He revisado tu trabajo de manera detallada, considerando las tres evidencias que subiste.

LO QUE HICISTE BIEN:
Resolviste correctamente casi toda la ficha. Reconociste el orden de las matrices A, B y C; identificaste correctamente filas, columnas y la fila 2 de la matriz M; determinaste las diagonales y el elemento q21; clasificaste correctamente las matrices identidad, escalar y triangular superior; identificaste bien los elementos de la matriz A; calculaste correctamente las trazas de B, C y D; y en el ejercicio 8 marcaste correctamente V/F y corregiste las proposiciones falsas.

LO QUE DEBES MEJORAR:
Ejercicio 3 – elemento p34:
Tu respuesta/procedimiento: escribiste p31 = 7.
Error detectado: el ejercicio pedía p34, no p31. Esto indica que se intercambió la lectura del índice solicitado.
Procedimiento correcto: en pij, el primer subíndice indica la fila y el segundo la columna. Para p34 debes ir a la fila 3 y columna 4 de la matriz P.
Resultado correcto: p34 = 3.

Ejercicio 5 – clasificación de la matriz R:
Tu respuesta/procedimiento: clasificaste R como matriz triangular superior.
Error detectado: R tiene ceros por encima de la diagonal principal, no por debajo.
Procedimiento correcto: una matriz triangular inferior tiene todos los elementos ubicados por encima de la diagonal principal iguales a cero.
Resultado correcto: R es una matriz triangular inferior.

SUGERENCIAS:
Antes de responder elementos del tipo pij, verifica siempre primero fila y luego columna. En la clasificación de matrices triangulares, observa dónde están los ceros respecto de la diagonal principal: si están debajo, es triangular superior; si están encima, es triangular inferior. Tu trabajo evidencia un buen dominio general del tema y los errores encontrados son puntuales.""".strip()


def _norm(value: Any) -> str:
    text = unicodedata.normalize("NFD", str(value or ""))
    text = "".join(ch for ch in text if unicodedata.category(ch) != "Mn")
    return " ".join(text.upper().split())


def enqueue_once(classroom: Any, bridge_queue: Any) -> dict[str, Any]:
    target_assignment_norm = _norm(TARGET_ASSIGNMENT)
    candidates: list[dict[str, Any]] = []

    for course in classroom.list_courses(active_only=True):
        course_id = str(course.get("id") or "")
        if not course_id:
            continue
        course_hay = _norm(f"{course.get('name') or ''} {course.get('section') or ''}")
        if "MATE 5TO" not in course_hay or ("5TO - B" not in course_hay and "5TO B" not in course_hay):
            continue

        try:
            works = classroom.list_coursework(course_id, include_drafts=True)
        except Exception:
            continue
        work_matches = [w for w in works if _norm(w.get("title")) == target_assignment_norm]
        if len(work_matches) != 1:
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
        work = work_matches[0]
        work_id = str(work.get("id") or "")
        if not user_id or not work_id:
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

    unique = {(c["course_id"], c["course_work_id"], c["submission_id"]): c for c in candidates}
    candidates = list(unique.values())
    if len(candidates) != 1:
        raise RuntimeError(
            "NICOLAS_FEEDBACK_TARGET_NOT_UNIQUE: se esperaba exactamente una entrega de Nicolás Vargas "
            f"para '{TARGET_ASSIGNMENT}' en 5.º B y se encontraron {len(candidates)}."
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
            f"NICOLAS_FEEDBACK: ya existe job {existing[0].id} estado={existing[0].status}; no se duplica.",
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
        "NICOLAS_FEEDBACK: comentario encolado SOLO para "
        f"{target['student_name']} | {target['course_name']} {target['course_section'] or ''} | "
        f"job={job.id} guard={job.guard_job_id} estado={job.status}",
        flush=True,
    )
    return {"queued": True, "job_id": job.id, "guard_job_id": job.guard_job_id, **target}
