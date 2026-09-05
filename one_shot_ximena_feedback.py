from __future__ import annotations

import unicodedata
from typing import Any

TARGET_ASSIGNMENT = "SUBIR AQUÍ FICHA INTRO MATRICES"
TARGET_STUDENT_TOKENS = ("XIMENA", "SUAREZ", "ARGOTE")
TARGET_GRADE = 18

FEEDBACK = """Ximena,
He revisado tu trabajo de manera detallada y se observa un buen dominio general de la ficha.

LO QUE HICISTE BIEN:
Resolviste correctamente los ejercicios 2, 3, 5, 6, 7 y 8. Identificaste bien las filas, columnas y elementos de una matriz; ubicaste correctamente elementos mediante la notación aij; clasificaste adecuadamente las matrices identidad, escalar, triangular superior y triangular inferior; reconociste la diagonal principal y el tipo de la matriz del ejercicio 6; calculaste correctamente las trazas 12, 17 y 25; y en el ejercicio 8 marcaste correctamente V/F y corregiste las afirmaciones falsas.

LO QUE DEBES MEJORAR:
Ejercicio 1 – orden de las matrices B y C:
Tu respuesta/procedimiento: escribiste B = 4×3 y C = 3×2.
Error detectado: invertiste el número de filas y columnas. El orden de una matriz siempre se expresa como filas × columnas.
Procedimiento correcto: primero cuenta las filas y después las columnas.
Resultado correcto: B tiene 3 filas y 4 columnas, por lo tanto B = 3×4. C tiene 2 filas y 3 columnas, por lo tanto C = 2×3.

Ejercicio 4 – diagonal secundaria:
Tu respuesta/procedimiento: escribiste 9, 4, 7.
Error detectado: reconociste los tres elementos que pertenecen a la diagonal secundaria, pero los anotaste en sentido inverso.
Procedimiento correcto: para escribir la diagonal secundaria se lee desde la esquina superior derecha hacia la esquina inferior izquierda.
Resultado correcto: 7, 4, 9.

SUGERENCIAS:
Antes de escribir el orden de una matriz, repite mentalmente “filas × columnas” para evitar invertir los valores. En las diagonales, usa siempre un sentido de lectura ordenado: diagonal principal de arriba-izquierda a abajo-derecha y diagonal secundaria de arriba-derecha a abajo-izquierda. Mantén el cuidado mostrado en el resto de la ficha, porque los demás procedimientos están correctamente desarrollados.

Tu calificación es 18 - (A)""".strip()


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
        works = classroom.list_coursework(course_id, include_drafts=True)
        work_matches = [w for w in works if _norm(w.get("title")) == target_assignment_norm]
        if len(work_matches) != 1:
            continue
        students = classroom.list_students(course_id)
        student_matches = []
        for student in students:
            hay = _norm(f"{student.get('name') or ''} {student.get('email') or ''}")
            if all(tok in hay for tok in TARGET_STUDENT_TOKENS):
                student_matches.append(student)
        if len(student_matches) != 1:
            continue
        student = student_matches[0]
        work = work_matches[0]
        submissions = classroom.list_submissions(course_id, str(work.get("id") or ""))
        sub_matches = [s for s in submissions if str(s.get("userId") or "") == str(student.get("userId") or "")]
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
                "course_work_id": str(work.get("id") or ""),
                "submission_id": submission_id,
                "submission_url": url,
                "student_name": student.get("name"),
            })

    unique = {(c["course_id"], c["course_work_id"], c["submission_id"]): c for c in candidates}
    candidates = list(unique.values())
    if len(candidates) != 1:
        raise RuntimeError(
            "XIMENA_FEEDBACK_TARGET_NOT_UNIQUE: se esperaba exactamente una entrega de Ximena Suárez Argote "
            f"para '{TARGET_ASSIGNMENT}' en 5.º B y se encontraron {len(candidates)}."
        )

    target = candidates[0]
    job = bridge_queue.enqueue(
        course_id=target["course_id"],
        course_work_id=target["course_work_id"],
        submission_id=target["submission_id"],
        submission_url=target["submission_url"],
        comment=FEEDBACK,
        grade=TARGET_GRADE,
        return_after_comment=True,
        operation="post_private_comment",
    )
    print(
        "XIMENA_FEEDBACK: encolado SOLO para "
        f"{target['student_name']} | {target['course_name']} {target['course_section'] or ''} | "
        f"grade={TARGET_GRADE} job={job.id} guard={job.guard_job_id} estado={job.status}",
        flush=True,
    )
    return {"queued": True, "job_id": job.id, "guard_job_id": job.guard_job_id, **target}
