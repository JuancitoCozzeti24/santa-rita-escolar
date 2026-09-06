from __future__ import annotations

import json
import sys
import unicodedata
from typing import Any

TARGET_TITLE = "C2: Desarrollar tarea de determinantes"
EXPECTED_ZERO = {
    "DIEGO ALEJANDRO LINARES ARTETA",
    "HANNA ELENA VALENZUELA CABALLERO",
    "MARCO POLO TIMOTEO ESPINOZA",
    "MATIAS ANTONIO ALIAGA MONTOYA",
    "RENZO RYUJI VEGA OYANAGI",
    "RODRIGO ALONSO RODRIGUEZ GAMONAL",
}
MARCO = "MARCO POLO TIMOTEO ESPINOZA"
MARCO_FILE_ID = "15rgPVAA1AJQ0X5zNp9s6nn_5ZOsbjv91"
EXPECTED_CONTEXT = {
    "idAmbito": 525,
    "idClase": 2126,
    "idClasePeriodo": 6593,
    "idContenido": 119886,
    "idPeriodoAnt": 6592,
}
EXPECTED_PARENTS = [134872, 134874, 134876, 134878]


def _norm(value: Any) -> str:
    text = unicodedata.normalize("NFD", str(value or ""))
    text = "".join(ch for ch in text if unicodedata.category(ch) != "Mn")
    return " ".join(text.upper().split())


def _attachments(sub: dict[str, Any]) -> list[dict[str, Any]]:
    return list(((sub.get("assignmentSubmission") or {}).get("attachments") or []))


def _drive_ids(sub: dict[str, Any]) -> list[str]:
    out = []
    for item in _attachments(sub):
        df = item.get("driveFile") if isinstance(item, dict) else None
        if isinstance(df, dict) and df.get("id"):
            out.append(str(df.get("id")))
    return out


def _zero_comment(name: str) -> str:
    first = str(name or "Estudiante").split()[0].title()
    return f"""{first},
He revisado tu estado de entrega en la actividad C2: Desarrollar tarea de determinantes.

LO QUE HICISTE BIEN:
En esta oportunidad no se cuenta con una evidencia presentada que permita reconocer logros específicos de aprendizaje en esta actividad.

LO QUE DEBES MEJORAR:
No presentaste evidencia de la tarea de determinantes, por lo que no es posible valorar tu procedimiento ni verificar el desarrollo de los aprendizajes propuestos. Estás cursando quinto año de secundaria, una etapa en la que asumir con mayor autonomía tus responsabilidades académicas es especialmente importante. Cumplir con los compromisos, organizar tus tiempos y atender los plazos establecidos son hábitos que trascienden el colegio y serán valiosos en tus estudios posteriores, en el trabajo y en distintos aspectos de tu vida adulta.

SUGERENCIAS:
Toma esta situación como una oportunidad para fortalecer tu organización, constancia y responsabilidad personal. En adelante procura revisar oportunamente las indicaciones de Classroom, organizar tus tiempos y presentar las evidencias dentro de los plazos establecidos.

Tu calificación es 0/20 - (C).""".strip()


def _marco_comment() -> str:
    return """Marco Polo,
He revisado tu trabajo de manera detallada en la actividad C2: Desarrollar tarea de determinantes.

LO QUE HICISTE BIEN:
Pregunta 1: calculaste correctamente el determinante mediante 3(4) - 5(2) = 12 - 10 = 2.
Pregunta 2: manejaste correctamente el signo negativo en 7(2) - (-1)(6), obteniendo 14 - (-6) = 20.
Pregunta 3: desarrollaste correctamente -4(1) - 3(5) = -4 - 15 = -19.
Pregunta 4: planteaste correctamente la ecuación del determinante 5x - 6 = 14 y despejaste x = 4.
Pregunta 5: obtuviste correctamente determinante igual a 0 y explicaste que este resultado se relaciona con la proporcionalidad entre filas.
Pregunta 6: calculaste correctamente 12(6) - 8(9) = 72 - 72 = 0 y justificaste el resultado mediante la proporcionalidad y la dependencia lineal.

LO QUE DEBES MEJORAR:
No se identificaron errores matemáticos que requieran corrección en los seis ejercicios revisados. Como mejora de presentación, procura conservar siempre la matriz o los datos originales junto al procedimiento para que la solución pueda verificarse de manera todavía más directa y ordenada.

SUGERENCIAS:
Mantén el procedimiento paso a paso que has utilizado. Antes de entregar, revisa especialmente los signos en la regla ad - bc y, cuando el determinante sea cero, acompaña el cálculo con una breve justificación de la propiedad observada, tal como hiciste en los ejercicios finales.

Tu calificación es 20/20 - (A).""".strip()


def _cell(student: dict[str, Any], header_id: int) -> str:
    notes = student.get("notas") or {}
    item = notes.get(str(header_id)) or notes.get(header_id) or {}
    value = item.get("notaReg")
    if value in (None, ""):
        value = item.get("notaIni")
    return str(value or "").strip().upper()


def execute(classroom: Any, bridge_queue: Any) -> dict[str, Any]:
    # 1) Ubicar actividad exacta.
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
        raise RuntimeError("C2_DET_EXEC: no se encontró de forma única la actividad exacta en 5B.")

    course_id = str(course.get("id") or "")
    work_id = str(work.get("id") or "")
    roster = classroom.list_students(course_id)
    by_user = {str(s.get("userId") or ""): s for s in roster}
    zero_rows = []
    sub_by_name: dict[str, dict[str, Any]] = {}
    code_by_name: dict[str, str] = {}

    for sub in classroom.list_submissions(course_id, work_id):
        st = by_user.get(str(sub.get("userId") or "")) or {}
        name = _norm(st.get("name"))
        grade = sub.get("assignedGrade") if sub.get("assignedGrade") is not None else sub.get("draftGrade")
        try:
            is_zero = grade is not None and float(grade) == 0.0
        except Exception:
            is_zero = False
        if not is_zero:
            continue
        code = str(st.get("email") or "").split("@", 1)[0].strip()
        row = {
            "name": st.get("name"), "norm": name, "code": code, "state": sub.get("state"),
            "submissionId": sub.get("id"), "alternateLink": sub.get("alternateLink"),
            "driveIds": _drive_ids(sub), "attachmentCount": len(_attachments(sub)),
        }
        zero_rows.append(row)
        sub_by_name[name] = sub
        code_by_name[name] = code

    observed = {r["norm"] for r in zero_rows}
    if observed != EXPECTED_ZERO:
        raise RuntimeError("C2_DET_EXEC: cambió el conjunto de alumnos con 0; se bloqueó el lote. " + json.dumps({"expected": sorted(EXPECTED_ZERO), "observed": sorted(observed)}, ensure_ascii=False))

    for row in zero_rows:
        if row["norm"] == MARCO:
            if row["driveIds"] != [MARCO_FILE_ID] or str(row["state"]) != "TURNED_IN":
                raise RuntimeError("C2_DET_EXEC: cambió la evidencia/estado de Marco Polo; se bloqueó el lote. " + json.dumps(row, ensure_ascii=False))
        elif row["attachmentCount"] != 0:
            raise RuntimeError("C2_DET_EXEC: apareció evidencia nueva en un alumno que estaba sin evidencia; se bloqueó para revisión. " + json.dumps(row, ensure_ascii=False))

    # 2) Encolar retroalimentación Classroom exclusivamente para estos seis.
    jobs = []
    for row in zero_rows:
        name = row["norm"]
        sub = sub_by_name[name]
        comment = _marco_comment() if name == MARCO else _zero_comment(str(row["name"]))
        grade_arg = 20.0 if name == MARCO else None
        return_after = bool(name == MARCO)
        prior = [
            j for j in bridge_queue.matching(
                course_id=course_id,
                course_work_id=work_id,
                submission_id=str(sub.get("id") or ""),
                operation="post_private_comment",
            )
            if str(getattr(j, "comment", "") or "").strip() == comment
            and getattr(j, "status", "") not in {"failed", "cancelled"}
        ]
        if prior:
            print(f"C2_DET_ALREADY_QUEUED: {row['name']} job={prior[0].id} status={prior[0].status}", flush=True)
            continue
        job = bridge_queue.enqueue(
            course_id=course_id,
            course_work_id=work_id,
            submission_id=str(sub.get("id") or ""),
            submission_url=str(sub.get("alternateLink") or ""),
            comment=comment,
            grade=grade_arg,
            return_after_comment=return_after,
            operation="post_private_comment",
        )
        jobs.append({"student": row["name"], "job": job.id, "guard": job.guard_job_id, "grade": 20 if name == MARCO else 0})
        print(f"C2_DET_ENQUEUED: {row['name']} grade={20 if name == MARCO else 0} job={job.id} guard={job.guard_job_id}", flush=True)

    # 3) Sincronizar SOLO estos seis a SIEWeb. Marco pasa a A; los cinco sin evidencia permanecen C.
    main = sys.modules.get("__main__")
    namespace = vars(main) if main is not None else {}
    sieweb = namespace.get("sieweb")
    if sieweb is None:
        raise RuntimeError("C2_DET_EXEC: cliente SIEWeb no disponible.")

    ctx = sieweb.resolve_class_context(section="5B", period=2, course_code="05", id_ambito=525)
    got_ctx = {
        "idAmbito": int(ctx.get("idAmbito") or 525),
        "idClase": int(ctx.get("idClase") or 0),
        "idClasePeriodo": int(ctx.get("idClasePeriodo") or 0),
        "idContenido": int(ctx.get("idContenido") or 0),
        "idPeriodoAnt": int(ctx.get("idPeriodoAnt") or 0),
    }
    if got_ctx != EXPECTED_CONTEXT:
        raise RuntimeError("C2_DET_EXEC: cambió el contexto SIEWeb. " + json.dumps({"expected": EXPECTED_CONTEXT, "observed": got_ctx}, ensure_ascii=False))

    extra = {"idPeriodoAnt": EXPECTED_CONTEXT["idPeriodoAnt"]}
    before = sieweb.get_gradebook_summary(
        class_period_id=EXPECTED_CONTEXT["idClasePeriodo"],
        root_content_id=EXPECTED_CONTEXT["idContenido"],
        extra_params=extra,
    )
    criteria = before.get("criteria") or []
    candidates = [
        c for c in criteria
        if int(c.get("nivelEva") or 0) == 3
        and _norm(c.get("abreviatura") or c.get("desc") or "").startswith("C2")
    ]
    print("C2_DET_SIEWEB_CANDIDATES=" + json.dumps(candidates, ensure_ascii=False, default=str), flush=True)

    per_parent: dict[int, list[dict[str, Any]]] = {p: [] for p in EXPECTED_PARENTS}
    for c in candidates:
        parent = int(c.get("idpadre") or 0)
        if parent in per_parent:
            per_parent[parent].append(c)
    if any(len(per_parent[p]) != 1 for p in EXPECTED_PARENTS):
        raise RuntimeError("C2_DET_EXEC: no hay exactamente un desempeño C2 existente por capacidad; no se crearon duplicados automáticamente. " + json.dumps({str(p): per_parent[p] for p in EXPECTED_PARENTS}, ensure_ascii=False, default=str))

    headers = [int(per_parent[p][0].get("id")) for p in EXPECTED_PARENTS]
    for h in headers:
        sieweb.assert_performance_target(before, header_id=h, performance_level=3)

    desired = {}
    for name in EXPECTED_ZERO:
        code = code_by_name.get(name)
        if not code:
            raise RuntimeError(f"C2_DET_EXEC: falta código SIEWeb para {name}")
        desired[code] = "A" if name == MARCO else "C"

    # Congelar todos los demás desempeños para detectar cualquier cambio lateral.
    students_before = {str(s.get("alucod") or "").strip(): s for s in (before.get("students") or [])}
    other_ids = [int(c.get("id") or 0) for c in criteria if int(c.get("nivelEva") or 0) == 3 and int(c.get("id") or 0) not in headers]
    untouched = {
        code: {str(h): _cell(student, h) for h in other_ids}
        for code, student in students_before.items()
    }

    native_scope = (before.get("class") or {}).get("arrNivelGrado")
    write = sieweb.save_grades_multi_verified(
        year="2026",
        course_code="05",
        class_period_id=EXPECTED_CONTEXT["idClasePeriodo"],
        root_content_id=EXPECTED_CONTEXT["idContenido"],
        period=2,
        section_ng=native_scope,
        header_ids=headers,
        grades_by_student_code=desired,
        class_name=None,
        extra_params=extra,
        notify=False,
        verification_attempts=3,
        performance_level=3,
    )
    print("C2_DET_SIEWEB_WRITE=" + json.dumps(write, ensure_ascii=False, default=str), flush=True)

    after = sieweb.get_gradebook_summary(
        class_period_id=EXPECTED_CONTEXT["idClasePeriodo"],
        root_content_id=EXPECTED_CONTEXT["idContenido"],
        extra_params=extra,
    )
    students_after = {str(s.get("alucod") or "").strip(): s for s in (after.get("students") or [])}
    failures = []
    for code, target in desired.items():
        student = students_after.get(code) or {}
        for h in headers:
            observed_cell = _cell(student, h)
            if observed_cell != target:
                failures.append({"code": code, "header": h, "expected": target, "observed": observed_cell})
    lateral = []
    for code, before_cells in untouched.items():
        st = students_after.get(code) or {}
        after_cells = {str(h): _cell(st, h) for h in other_ids}
        if after_cells != before_cells:
            lateral.append(code)
    if failures or lateral:
        raise RuntimeError("C2_DET_EXEC: falló verificación final SIEWeb. " + json.dumps({"failures": failures, "lateral": lateral}, ensure_ascii=False))

    print("C2_DET_SIEWEB_SUCCESS=" + json.dumps({"headers": headers, "grades": desired, "verified_cells": len(headers) * len(desired), "lateral_changes": 0}, ensure_ascii=False), flush=True)
    print("C2_DET_READY=" + json.dumps({"jobs": jobs, "zero_students": [r["name"] for r in zero_rows]}, ensure_ascii=False), flush=True)
    return {
        "queued": bool(jobs),
        "count": len(jobs),
        "jobs": jobs,
        "course_name": course.get("name"),
        "work": work.get("title"),
        "sieweb_headers": headers,
        "sieweb_verified_cells": len(headers) * len(desired),
    }
