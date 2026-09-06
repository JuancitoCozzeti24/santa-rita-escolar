from __future__ import annotations

import json
import unicodedata
from collections import Counter
from typing import Any

TARGET_TITLE = "C1: Tarea de Operaciones con Matrices"
EXPECTED_CONTEXT = {
    "idAmbito": 525,
    "idClase": 2126,
    "idClasePeriodo": 6593,
    "idContenido": 119886,
    "idPeriodoAnt": 6592,
}
# Auditoría previa: estos cuatro desempeños C1 FICHA existen, uno por cada capacidad
# de Regularidad/Equivalencia/Cambio, y estaban vacíos para los 26 alumnos.
TARGET_HEADERS = [134904, 134906, 134908, 134910]
EXPECTED_PARENTS = {
    134904: 134872,
    134906: 134874,
    134908: 134876,
    134910: 134878,
}


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
    # 1) Classroom: actividad exacta y calificación actual de los 26 alumnos.
    course = None
    work = None
    wanted = _norm(TARGET_TITLE)
    for c in classroom.list_courses(active_only=True):
        hay = _norm(f"{c.get('name') or ''} {c.get('section') or ''}")
        if "MATE 5TO" not in hay or ("5TO - B" not in hay and "5TO B" not in hay):
            continue
        exact = [
            w for w in classroom.list_coursework(str(c.get("id") or ""), include_drafts=True)
            if _norm(w.get("title")) == wanted
        ]
        if len(exact) == 1:
            course, work = c, exact[0]
            break
    if not course or not work:
        raise RuntimeError("C1_OPS_WRITE_BLOCKED: no se encontró de forma única la actividad exacta en 5B.")

    course_id = str(course.get("id") or "")
    work_id = str(work.get("id") or "")
    by_user = {
        str(s.get("userId") or ""): s
        for s in classroom.list_students(course_id)
    }
    grade_map: dict[str, str] = {}
    classroom_rows = []
    for sub in classroom.list_submissions(course_id, work_id):
        st = by_user.get(str(sub.get("userId") or "")) or {}
        code = str(st.get("email") or "").split("@", 1)[0].strip()
        grade = sub.get("assignedGrade") if sub.get("assignedGrade") is not None else sub.get("draftGrade")
        qualitative = _qual(grade)
        if not code or qualitative not in {"A", "B", "C"}:
            raise RuntimeError(
                "C1_OPS_WRITE_BLOCKED: alumno sin código o nota válida: "
                + json.dumps({"name": st.get("name"), "code": code, "grade": grade}, ensure_ascii=False)
            )
        grade_map[code] = qualitative
        classroom_rows.append({
            "code": code,
            "name": st.get("name"),
            "numeric": grade,
            "qualitative": qualitative,
            "state": sub.get("state"),
        })
    classroom_rows.sort(key=lambda x: _norm(x.get("name")))
    if len(classroom_rows) != 26 or len(grade_map) != 26:
        raise RuntimeError(
            f"C1_OPS_WRITE_BLOCKED: se esperaban 26 alumnos y se obtuvieron {len(classroom_rows)} filas / {len(grade_map)} códigos."
        )
    print("C1_OPS_CLASSROOM_FINAL=" + json.dumps(classroom_rows, ensure_ascii=False), flush=True)
    print("C1_OPS_GRADE_COUNTS=" + json.dumps(dict(Counter(grade_map.values())), ensure_ascii=False), flush=True)

    # 2) SIEWeb: contexto exacto 5B Matemática, periodo 2.
    ctx = sieweb.resolve_class_context(section="5B", period=2, course_code="05", id_ambito=525)
    observed = {
        "idAmbito": int(ctx.get("idAmbito") or 525),
        "idClase": int(ctx.get("idClase") or 0),
        "idClasePeriodo": int(ctx.get("idClasePeriodo") or 0),
        "idContenido": int(ctx.get("idContenido") or 0),
        "idPeriodoAnt": int(ctx.get("idPeriodoAnt") or 0),
    }
    if observed != EXPECTED_CONTEXT:
        raise RuntimeError(
            "C1_OPS_WRITE_BLOCKED: contexto SIEWeb cambió. "
            + json.dumps({"expected": EXPECTED_CONTEXT, "observed": observed}, ensure_ascii=False)
        )

    extra = {"idPeriodoAnt": EXPECTED_CONTEXT["idPeriodoAnt"]}
    before = sieweb.get_gradebook_summary(
        class_period_id=EXPECTED_CONTEXT["idClasePeriodo"],
        root_content_id=EXPECTED_CONTEXT["idContenido"],
        extra_params=extra,
    )
    criteria = before.get("criteria") or []
    criteria_by_id = {int(c.get("id") or 0): c for c in criteria}

    # 3) Los cuatro desempeños ya existen; se usan y NO se crean duplicados.
    for header_id in TARGET_HEADERS:
        item = criteria_by_id.get(header_id)
        if not item:
            raise RuntimeError(f"C1_OPS_WRITE_BLOCKED: falta el desempeño existente {header_id}; no se creará otro automáticamente.")
        if int(item.get("nivelEva") or 0) != 3:
            raise RuntimeError(f"C1_OPS_WRITE_BLOCKED: {header_id} dejó de ser desempeño nivel 3.")
        if int(item.get("idpadre") or 0) != EXPECTED_PARENTS[header_id]:
            raise RuntimeError(f"C1_OPS_WRITE_BLOCKED: cambió el padre del desempeño {header_id}.")
        if _norm(item.get("abreviatura")) != "C1 FICHA":
            raise RuntimeError(f"C1_OPS_WRITE_BLOCKED: cambió la abreviatura del desempeño {header_id}.")
        sieweb.assert_performance_target(before, header_id=header_id, performance_level=3)

    students_before = {
        str(s.get("alucod") or "").strip(): s
        for s in (before.get("students") or [])
    }
    if len(students_before) != 26 or set(students_before) != set(grade_map):
        raise RuntimeError(
            "C1_OPS_WRITE_BLOCKED: la nómina de Classroom y SIEWeb no coincide exactamente. "
            + json.dumps({
                "classroom_only": sorted(set(grade_map) - set(students_before)),
                "sieweb_only": sorted(set(students_before) - set(grade_map)),
            }, ensure_ascii=False)
        )

    conflicts = []
    all_already = True
    for code, desired in grade_map.items():
        student = students_before[code]
        for header_id in TARGET_HEADERS:
            current = _cell(student, header_id)
            if current != desired:
                all_already = False
            if current not in ("", desired):
                conflicts.append({
                    "code": code,
                    "header": header_id,
                    "current": current,
                    "desired": desired,
                })
    if conflicts:
        raise RuntimeError(
            "C1_OPS_WRITE_BLOCKED: hay valores previos distintos en los desempeños C1 FICHA; no se sobrescribió nada. "
            + json.dumps(conflicts, ensure_ascii=False)
        )

    # Congelar todos los demás desempeños nivel 3 para auditar que no cambien.
    other_performance_ids = [
        int(c.get("id") or 0)
        for c in criteria
        if int(c.get("nivelEva") or 0) == 3 and int(c.get("id") or 0) not in TARGET_HEADERS
    ]
    untouched_snapshot = {
        code: {str(h): _cell(student, h) for h in other_performance_ids}
        for code, student in students_before.items()
    }

    # 4) Un solo lote para los cuatro desempeños, con verificación posterior obligatoria.
    write_result = None
    if not all_already:
        native_scope = (before.get("class") or {}).get("arrNivelGrado")
        write_result = sieweb.save_grades_multi_verified(
            year="2026",
            course_code="05",
            class_period_id=EXPECTED_CONTEXT["idClasePeriodo"],
            root_content_id=EXPECTED_CONTEXT["idContenido"],
            period=2,
            section_ng=native_scope,
            header_ids=TARGET_HEADERS,
            grades_by_student_code=grade_map,
            class_name=None,
            extra_params=extra,
            notify=False,
            verification_attempts=3,
            performance_level=3,
        )
        print("C1_OPS_SIEWEB_WRITE_RESULT=" + json.dumps(write_result, ensure_ascii=False, default=str), flush=True)

    # 5) Relectura independiente: 104 celdas objetivo exactas y cero cambios laterales.
    after = sieweb.get_gradebook_summary(
        class_period_id=EXPECTED_CONTEXT["idClasePeriodo"],
        root_content_id=EXPECTED_CONTEXT["idContenido"],
        extra_params=extra,
    )
    students_after = {
        str(s.get("alucod") or "").strip(): s
        for s in (after.get("students") or [])
    }

    target_failures = []
    final_rows = []
    for code, desired in grade_map.items():
        student = students_after.get(code) or {}
        observed_cells = {str(h): _cell(student, h) for h in TARGET_HEADERS}
        for h, value in observed_cells.items():
            if value != desired:
                target_failures.append({"code": code, "header": h, "expected": desired, "observed": value})
        final_rows.append({
            "code": code,
            "name": next((r["name"] for r in classroom_rows if r["code"] == code), None),
            "qualitative": desired,
            "cells": observed_cells,
        })

    untouched_changes = []
    for code, before_cells in untouched_snapshot.items():
        student = students_after.get(code) or {}
        after_cells = {str(h): _cell(student, h) for h in other_performance_ids}
        if after_cells != before_cells:
            untouched_changes.append({"code": code})

    final_rows.sort(key=lambda x: _norm(x.get("name")))
    print("C1_OPS_SIEWEB_FINAL=" + json.dumps(final_rows, ensure_ascii=False), flush=True)
    print("C1_OPS_UNTOUCHED_AUDIT=" + json.dumps({"student_count": len(untouched_snapshot), "changes": untouched_changes}, ensure_ascii=False), flush=True)

    if target_failures or untouched_changes:
        raise RuntimeError(
            "C1_OPS_FINAL_VERIFY_FAILED: "
            + json.dumps({"target_failures": target_failures, "untouched_changes": untouched_changes}, ensure_ascii=False)
        )

    print(
        "C1_OPS_SIEWEB_UPDATE_SUCCESS: 26 estudiantes; 4 desempeños existentes C1 FICHA; "
        "104 celdas verificadas; no se crearon desempeños nuevos; demás desempeños intactos.",
        flush=True,
    )
    return {
        "queued": False,
        "course_name": course.get("name"),
        "work": work.get("title"),
        "count": 26,
        "header_ids": TARGET_HEADERS,
        "verified_cells": 104,
        "created_criteria": 0,
        "already_present": all_already,
        "write": write_result,
    }
