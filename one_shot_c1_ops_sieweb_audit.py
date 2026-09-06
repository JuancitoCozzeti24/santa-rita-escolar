from __future__ import annotations

import json
import unicodedata
from typing import Any

TARGET_TITLE = "C1: Tarea de Operaciones con Matrices"
EXPECTED_CONTEXT = {
    "idAmbito": 525,
    "idClase": 2126,
    "idClasePeriodo": 6593,
    "idContenido": 119886,
    "idPeriodoAnt": 6592,
}
CAPACITY_PARENTS = {134872, 134874, 134876, 134878}


def _norm(value: Any) -> str:
    text = unicodedata.normalize("NFD", str(value or ""))
    text = "".join(ch for ch in text if unicodedata.category(ch) != "Mn")
    return " ".join(text.upper().split())


def _qual(grade: Any) -> str | None:
    if grade is None or str(grade).strip() == "":
        return None
    value = float(grade)
    return "A" if value >= 15 else ("B" if value >= 11 else "C")


def _cell(student: dict[str, Any], header_id: int) -> str:
    notes = student.get("notas") or {}
    item = notes.get(str(header_id)) or notes.get(header_id) or {}
    value = item.get("notaReg")
    if value in (None, ""):
        value = item.get("notaIni")
    return str(value or "").strip().upper()


def inspect(classroom: Any, sieweb: Any) -> dict[str, Any]:
    # Classroom: localizar curso y actividad de forma única.
    course = None
    work = None
    wanted = _norm(TARGET_TITLE)
    for c in classroom.list_courses(active_only=True):
        hay = _norm(f"{c.get('name') or ''} {c.get('section') or ''}")
        if "MATE 5TO" not in hay or ("5TO - B" not in hay and "5TO B" not in hay):
            continue
        works = classroom.list_coursework(str(c.get("id") or ""), include_drafts=True)
        exact = [w for w in works if _norm(w.get("title")) == wanted]
        if len(exact) == 1:
            course, work = c, exact[0]
            break
    if not course or not work:
        raise RuntimeError("C1_OPS_AUDIT_BLOCKED: no se encontró de forma única la actividad exacta en 5B.")

    course_id = str(course.get("id") or "")
    work_id = str(work.get("id") or "")
    roster = classroom.list_students(course_id)
    by_user = {str(s.get("userId") or ""): s for s in roster}
    classroom_rows = []
    classroom_by_code: dict[str, dict[str, Any]] = {}
    for sub in classroom.list_submissions(course_id, work_id):
        st = by_user.get(str(sub.get("userId") or "")) or {}
        code = str(st.get("email") or "").split("@", 1)[0].strip()
        grade = sub.get("assignedGrade") if sub.get("assignedGrade") is not None else sub.get("draftGrade")
        row = {
            "code": code,
            "name": st.get("name"),
            "numeric": grade,
            "qualitative": _qual(grade),
            "state": sub.get("state"),
            "attachment_count": len(sub.get("attachments") or []),
        }
        classroom_rows.append(row)
        if code:
            classroom_by_code[code] = row
    classroom_rows.sort(key=lambda x: _norm(x.get("name")))
    print("C1_OPS_CLASSROOM=" + json.dumps(classroom_rows, ensure_ascii=False), flush=True)

    # SIEWeb: contexto exacto de Matemática 5B, periodo 2.
    ctx = sieweb.resolve_class_context(section="5B", period=2, course_code="05", id_ambito=525)
    observed = {
        "idAmbito": int(ctx.get("idAmbito") or 525),
        "idClase": int(ctx.get("idClase") or 0),
        "idClasePeriodo": int(ctx.get("idClasePeriodo") or 0),
        "idContenido": int(ctx.get("idContenido") or 0),
        "idPeriodoAnt": int(ctx.get("idPeriodoAnt") or 0),
    }
    if observed != EXPECTED_CONTEXT:
        raise RuntimeError("C1_OPS_AUDIT_BLOCKED: contexto SIEWeb inesperado: " + json.dumps(observed, ensure_ascii=False))

    extra = {"idPeriodoAnt": EXPECTED_CONTEXT["idPeriodoAnt"]}
    summary = sieweb.get_gradebook_summary(
        class_period_id=EXPECTED_CONTEXT["idClasePeriodo"],
        root_content_id=EXPECTED_CONTEXT["idContenido"],
        extra_params=extra,
    )
    criteria = summary.get("criteria") or []

    # Candidatos: solo desempeños de las cuatro capacidades de Regularidad/Equivalencia/Cambio.
    candidates = []
    for item in criteria:
        if int(item.get("nivelEva") or 0) != 3:
            continue
        parent = int(item.get("idpadre") or 0)
        if parent not in CAPACITY_PARENTS:
            continue
        text = _norm(" ".join([
            str(item.get("desc") or ""),
            str(item.get("abreviatura") or ""),
            str(item.get("descripcion") or ""),
        ]))
        if any(token in text for token in ("C1", "MATRIZ", "MATRICES", "OPERACION", "OPERACIONES", "TAREA")):
            candidates.append({
                "id": int(item.get("id") or 0),
                "parent": parent,
                "abbr": item.get("abreviatura"),
                "desc": item.get("desc"),
                "description": item.get("descripcion"),
            })
    candidates.sort(key=lambda x: (x["parent"], x["id"]))
    print("C1_OPS_SIEWEB_CANDIDATES=" + json.dumps(candidates, ensure_ascii=False), flush=True)

    # Mostrar celdas actuales de cada candidato para los mismos alumnos de Classroom.
    sieweb_students = {str(s.get("alucod") or "").strip(): s for s in (summary.get("students") or [])}
    comparison = []
    for code, cr in classroom_by_code.items():
        sw = sieweb_students.get(code) or {}
        comparison.append({
            "code": code,
            "name": cr.get("name"),
            "numeric": cr.get("numeric"),
            "qualitative": cr.get("qualitative"),
            "current": {str(c["id"]): _cell(sw, c["id"]) for c in candidates},
        })
    comparison.sort(key=lambda x: _norm(x.get("name")))
    print("C1_OPS_SIEWEB_COMPARISON=" + json.dumps(comparison, ensure_ascii=False), flush=True)

    print(
        f"C1_OPS_AUDIT_SUCCESS: activity={work.get('title')} classroom_rows={len(classroom_rows)} candidates={len(candidates)}",
        flush=True,
    )
    return {
        "queued": False,
        "course_name": course.get("name"),
        "work": work.get("title"),
        "count": len(classroom_rows),
        "candidate_count": len(candidates),
        "context": observed,
    }
