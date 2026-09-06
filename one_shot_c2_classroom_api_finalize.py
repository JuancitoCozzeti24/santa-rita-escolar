from __future__ import annotations

import json
import unicodedata
from typing import Any

TARGET_TITLE = "C2: Desarrollar tarea de determinantes"
TARGETS = {
    "MARCO POLO TIMOTEO ESPINOZA": 20.0,
    "DIEGO ALEJANDRO LINARES ARTETA": 0.0,
    "HANNA ELENA VALENZUELA CABALLERO": 0.0,
    "MATIAS ANTONIO ALIAGA MONTOYA": 0.0,
    "RENZO RYUJI VEGA OYANAGI": 0.0,
    "RODRIGO ALONSO RODRIGUEZ GAMONAL": 0.0,
}


def _norm(value: Any) -> str:
    text = unicodedata.normalize("NFD", str(value or ""))
    text = "".join(ch for ch in text if unicodedata.category(ch) != "Mn")
    return " ".join(text.upper().split())


def _zero_comment(name: str) -> str:
    first = str(name or "Estudiante").split()[0].title()
    return f"""{first},
He revisado tu estado de entrega en la actividad C2: Desarrollar tarea de determinantes.

LO QUE HICISTE BIEN:
En esta oportunidad no se cuenta con una evidencia presentada que permita reconocer logros específicos de aprendizaje en esta actividad.

LO QUE DEBES MEJORAR:
No presentaste evidencia de la tarea de determinantes, por lo que no es posible valorar tu procedimiento ni verificar el desarrollo de los aprendizajes propuestos. Estás cursando quinto año de secundaria, una etapa en la que asumir con mayor autonomía tus responsabilidades académicas es especialmente importante.

SUGERENCIAS:
Toma esta situación como una oportunidad para fortalecer tu organización, constancia y responsabilidad personal. En adelante procura revisar oportunamente las indicaciones de Classroom, organizar tus tiempos y presentar las evidencias dentro de los plazos establecidos.

Tu calificación es 0/20 - (C).""".strip()


def _marco_comment() -> str:
    return """Marco Polo,
He revisado tu trabajo de manera detallada en la actividad C2: Desarrollar tarea de determinantes.

LO QUE HICISTE BIEN:
Pregunta 1: calculaste correctamente el determinante mediante 3(4) - 5(2) = 12 - 10 = 2.
Pregunta 2: manejaste correctamente el signo negativo en 7(2) - (-1)(6), obteniendo 20.
Pregunta 3: desarrollaste correctamente -4(1) - 3(5) = -19.
Pregunta 4: planteaste correctamente 5x - 6 = 14 y despejaste x = 4.
Pregunta 5: obtuviste correctamente determinante igual a 0 y explicaste la proporcionalidad entre filas.
Pregunta 6: calculaste correctamente 12(6) - 8(9) = 0 y justificaste el resultado mediante proporcionalidad y dependencia lineal.

LO QUE DEBES MEJORAR:
No se identificaron errores matemáticos que requieran corrección en los seis ejercicios revisados. Como mejora de presentación, procura conservar siempre la matriz o los datos originales junto al procedimiento para que la solución pueda verificarse de manera todavía más directa y ordenada.

SUGERENCIAS:
Mantén el procedimiento paso a paso que has utilizado. Antes de entregar, revisa especialmente los signos en la regla ad - bc y, cuando el determinante sea cero, acompaña el cálculo con una breve justificación de la propiedad observada.

Tu calificación es 20/20 - (A).""".strip()


def execute(classroom: Any, bridge_queue: Any) -> dict[str, Any]:
    course = work = None
    wanted = _norm(TARGET_TITLE)
    for c in classroom.list_courses(active_only=True):
        hay = _norm(f"{c.get('name') or ''} {c.get('section') or ''}")
        if "MATE 5TO" not in hay or ("5TO - B" not in hay and "5TO B" not in hay):
            continue
        exact = [w for w in classroom.list_coursework(str(c.get("id") or ""), include_drafts=True) if _norm(w.get("title")) == wanted]
        if len(exact) == 1:
            course, work = c, exact[0]
            break
    if not course or not work:
        raise RuntimeError("C2_CLASSROOM_API: no se encontró de forma única la actividad exacta en 5B.")

    course_id = str(course.get("id") or "")
    work_id = str(work.get("id") or "")
    roster = classroom.list_students(course_id)
    by_user = {str(s.get("userId") or ""): s for s in roster}
    subs = classroom.list_submissions(course_id, work_id)
    selected = {}
    for sub in subs:
        st = by_user.get(str(sub.get("userId") or "")) or {}
        key = _norm(st.get("name"))
        if key in TARGETS:
            selected[key] = (st, sub)
    if set(selected) != set(TARGETS):
        raise RuntimeError("C2_CLASSROOM_API: faltan o sobran estudiantes objetivo: " + json.dumps({"expected": sorted(TARGETS), "observed": sorted(selected)}, ensure_ascii=False))

    api_results = []
    jobs = []
    for key, target_grade in TARGETS.items():
        st, sub = selected[key]
        sid = str(sub.get("id") or "")
        state_before = str(sub.get("state") or "")

        # La nota se escribe directamente por la API oficial de Classroom.
        # Solo Marco tiene una entrega real TURNED_IN para devolver; los CREATED no se pueden devolver.
        if key == "MARCO POLO TIMOTEO ESPINOZA":
            if state_before == "TURNED_IN":
                result = classroom.grade_submission(course_id, work_id, sid, grade=20.0, return_to_student=True)
            else:
                result = classroom.grade_submission(course_id, work_id, sid, grade=20.0, return_to_student=False)
        else:
            result = classroom.grade_submission(course_id, work_id, sid, grade=0.0, return_to_student=False)

        after = classroom.get_submission(course_id, work_id, sid)
        observed_draft = after.get("draftGrade")
        observed_assigned = after.get("assignedGrade")
        if float(observed_draft if observed_draft is not None else -999) != target_grade or float(observed_assigned if observed_assigned is not None else -999) != target_grade:
            raise RuntimeError(f"C2_CLASSROOM_API: verificación de nota falló para {st.get('name')}: draft={observed_draft} assigned={observed_assigned} esperado={target_grade}")
        if key == "MARCO POLO TIMOTEO ESPINOZA" and str(after.get("state") or "") != "RETURNED":
            raise RuntimeError(f"C2_CLASSROOM_API: Marco quedó con nota pero no RETURNED: state={after.get('state')}")

        api_results.append({
            "student": st.get("name"),
            "grade": target_grade,
            "state_before": state_before,
            "state_after": after.get("state"),
            "draftGrade": observed_draft,
            "assignedGrade": observed_assigned,
        })
        print("C2_CLASSROOM_API_GRADED=" + json.dumps(api_results[-1], ensure_ascii=False, default=str), flush=True)

        # El comentario privado sigue por Bridge, pero sin reescribir nota ni intentar una devolución.
        comment = _marco_comment() if key == "MARCO POLO TIMOTEO ESPINOZA" else _zero_comment(str(st.get("name") or ""))
        job = bridge_queue.enqueue(
            course_id=course_id,
            course_work_id=work_id,
            submission_id=sid,
            submission_url=str(sub.get("alternateLink") or ""),
            comment=comment,
            grade=None,
            return_after_comment=False,
            operation="post_private_comment",
        )
        jobs.append({"student": st.get("name"), "job": job.id, "guard": job.guard_job_id})
        print(f"C2_CLASSROOM_COMMENT_ONLY_ENQUEUED: {st.get('name')} job={job.id} guard={job.guard_job_id}", flush=True)

    print("C2_CLASSROOM_API_SUCCESS=" + json.dumps({"count": len(api_results), "results": api_results}, ensure_ascii=False, default=str), flush=True)
    return {
        "queued": True,
        "count": len(jobs),
        "course_name": course.get("name"),
        "work": work.get("title"),
        "api_results": api_results,
        "jobs": jobs,
    }
