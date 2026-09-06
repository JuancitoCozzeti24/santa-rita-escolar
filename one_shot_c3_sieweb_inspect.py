from __future__ import annotations

import json
from typing import Any

HEADERS = [135935, 135936, 135937, 135938]
EXPECTED_CONTEXT = {
    "idAmbito": 525,
    "idClase": 2126,
    "idClasePeriodo": 6593,
    "idContenido": 119886,
    "idPeriodoAnt": 6592,
}

# Solo estos seis alumnos tienen las cuatro celdas C3 pendientes en SIEWeb.
# Los otros 20 ya tienen evaluación diferenciada por capacidad y se auditan sin sobrescribirlos.
TARGETS_BY_HEADER = {
    # Traduce datos y condiciones / representa situaciones con matrices.
    135935: {
        "20150044": "C",  # Diego Linares: sin evidencia
        "20150043": "B",  # Fátima G. Mujica
        "20150001": "A",  # Matías Aliaga
        "20150035": "C",  # Renzo Vega: sin evidencia
        "20150030": "A",  # Rodrigo Rodríguez
        "20150006": "C",  # Sebastián Corado: sin evidencia
    },
    # Comunica su comprensión.
    135936: {
        "20150044": "C",
        "20150043": "B",
        "20150001": "B",
        "20150035": "C",
        "20150030": "A",
        "20150006": "C",
    },
    # Usa estrategias y procedimientos.
    135937: {
        "20150044": "C",
        "20150043": "A",
        "20150001": "A",
        "20150035": "C",
        "20150030": "A",
        "20150006": "C",
    },
    # Argumenta / justifica resultados.
    135938: {
        "20150044": "C",
        "20150043": "B",
        "20150001": "B",
        "20150035": "C",
        "20150030": "A",
        "20150006": "C",
    },
}


def _cell_value(student: dict[str, Any], header_id: int) -> str:
    notes = student.get("notas") or {}
    cell = notes.get(str(header_id)) or notes.get(header_id) or {}
    value = cell.get("notaReg")
    if value in (None, ""):
        value = cell.get("notaIni")
    return str(value or "").strip().upper()


def _students_by_code(summary: dict[str, Any]) -> dict[str, dict[str, Any]]:
    return {str(s.get("alucod") or "").strip(): s for s in (summary.get("students") or [])}


def inspect(classroom: Any, sieweb: Any) -> dict[str, Any]:
    # 1) Contexto exacto de 5.º B Matemática, periodo 2.
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
            "C3_SIEWEB_WRITE_BLOCKED: el contexto cambió; no se escribió nada. "
            + json.dumps({"expected": EXPECTED_CONTEXT, "observed": observed}, ensure_ascii=False)
        )

    extra = {"idPeriodoAnt": EXPECTED_CONTEXT["idPeriodoAnt"]}
    before = sieweb.get_gradebook_summary(
        class_period_id=EXPECTED_CONTEXT["idClasePeriodo"],
        root_content_id=EXPECTED_CONTEXT["idContenido"],
        extra_params=extra,
    )

    # 2) Protección: los cuatro destinos deben seguir siendo desempeños nivel 3.
    for header_id in HEADERS:
        sieweb.assert_performance_target(before, header_id=header_id, performance_level=3)

    students_before = _students_by_code(before)
    if len(students_before) != 26:
        raise RuntimeError(
            f"C3_SIEWEB_WRITE_BLOCKED: se esperaban 26 estudiantes en 5B y se leyeron {len(students_before)}."
        )

    target_codes = set(next(iter(TARGETS_BY_HEADER.values())).keys())
    for mapping in TARGETS_BY_HEADER.values():
        if set(mapping) != target_codes:
            raise RuntimeError("C3_SIEWEB_WRITE_BLOCKED: mapas de alumnos inconsistentes.")

    # 3) Auditoría previa de las 26 filas. Las 20 ya calificadas se congelan y no se tocan.
    untouched_snapshot: dict[str, list[str]] = {}
    for code, student in students_before.items():
        values = [_cell_value(student, h) for h in HEADERS]
        if code not in target_codes:
            untouched_snapshot[code] = values

    if len(untouched_snapshot) != 20:
        raise RuntimeError(
            f"C3_SIEWEB_WRITE_BLOCKED: se esperaban 20 estudiantes ya evaluados y se hallaron {len(untouched_snapshot)}."
        )

    # Para los seis pendientes se permite únicamente celda vacía o el valor exacto deseado
    # (esto hace el proceso idempotente si un despliegue anterior alcanzó a guardar una parte).
    preflight_targets = []
    conflicts = []
    for code in sorted(target_codes):
        student = students_before.get(code)
        if not student:
            conflicts.append({"code": code, "reason": "student_not_found"})
            continue
        row = {"code": code, "name": student.get("nomcomp"), "current": {}, "target": {}}
        for h in HEADERS:
            current = _cell_value(student, h)
            desired = TARGETS_BY_HEADER[h][code]
            row["current"][str(h)] = current
            row["target"][str(h)] = desired
            if current not in ("", desired):
                conflicts.append({"code": code, "header": h, "current": current, "desired": desired})
        preflight_targets.append(row)
    print("C3_SIEWEB_WRITE_PREFLIGHT=" + json.dumps(preflight_targets, ensure_ascii=False), flush=True)
    if conflicts:
        raise RuntimeError(
            "C3_SIEWEB_WRITE_BLOCKED: hay celdas pendientes con un valor distinto al esperado; no se escribió nada. "
            + json.dumps(conflicts, ensure_ascii=False)
        )

    # Si las 24 celdas ya coinciden, no se repite ningún PUT.
    all_already = all(
        _cell_value(students_before[code], h) == TARGETS_BY_HEADER[h][code]
        for code in target_codes for h in HEADERS
    )

    writes = []
    if not all_already:
        native_scope = (before.get("class") or {}).get("arrNivelGrado")
        for header_id in HEADERS:
            result = sieweb.save_grades_verified(
                year="2026",
                course_code="05",
                class_period_id=EXPECTED_CONTEXT["idClasePeriodo"],
                root_content_id=EXPECTED_CONTEXT["idContenido"],
                period=2,
                section_ng=native_scope,
                header_id=header_id,
                grades_by_student_code=TARGETS_BY_HEADER[header_id],
                class_name=None,
                extra_params=extra,
                notify=False,
                verification_attempts=3,
                protect_achievement_level=True,
                performance_level=3,
            )
            writes.append({
                "header_id": header_id,
                "saved": result.get("saved"),
                "requested_count": result.get("requested_count"),
                "verification": result.get("verification"),
            })
            print("C3_SIEWEB_HEADER_SAVED=" + json.dumps(writes[-1], ensure_ascii=False, default=str), flush=True)

    # 4) Relectura final: 24 celdas objetivo exactas y cero alteraciones en las otras 80 celdas C3.
    after = sieweb.get_gradebook_summary(
        class_period_id=EXPECTED_CONTEXT["idClasePeriodo"],
        root_content_id=EXPECTED_CONTEXT["idContenido"],
        extra_params=extra,
    )
    students_after = _students_by_code(after)
    target_failures = []
    for code in sorted(target_codes):
        student = students_after.get(code) or {}
        for h in HEADERS:
            observed_value = _cell_value(student, h)
            desired = TARGETS_BY_HEADER[h][code]
            if observed_value != desired:
                target_failures.append({"code": code, "header": h, "expected": desired, "observed": observed_value})

    untouched_changes = []
    for code, before_values in untouched_snapshot.items():
        student = students_after.get(code)
        after_values = [_cell_value(student or {}, h) for h in HEADERS]
        if after_values != before_values:
            untouched_changes.append({"code": code, "before": before_values, "after": after_values})

    final_targets = []
    for code in sorted(target_codes):
        s = students_after.get(code) or {}
        final_targets.append({
            "code": code,
            "name": s.get("nomcomp"),
            "C3": {str(h): _cell_value(s, h) for h in HEADERS},
        })
    print("C3_SIEWEB_FINAL_TARGETS=" + json.dumps(final_targets, ensure_ascii=False), flush=True)
    print("C3_SIEWEB_UNTOUCHED_AUDIT=" + json.dumps({"count": len(untouched_snapshot), "changes": untouched_changes}, ensure_ascii=False), flush=True)

    if target_failures or untouched_changes:
        raise RuntimeError(
            "C3_SIEWEB_FINAL_VERIFY_FAILED: "
            + json.dumps({"target_failures": target_failures, "untouched_changes": untouched_changes}, ensure_ascii=False)
        )

    print(
        "C3_SIEWEB_UPDATE_SUCCESS: 26 estudiantes auditados; 6 pendientes actualizados/verificados; "
        "24 celdas C3 objetivo correctas; 20 estudiantes previamente calificados quedaron intactos.",
        flush=True,
    )
    return {
        "queued": False,
        "course_name": "MATE 5TO - B",
        "work": "C3: Evaluación semanal de matrices",
        "count": 26,
        "updated_students": 6,
        "verified_cells": 24,
        "untouched_students": 20,
        "already_present": all_already,
        "writes": writes,
    }
