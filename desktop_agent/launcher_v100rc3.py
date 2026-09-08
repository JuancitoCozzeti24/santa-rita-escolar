from __future__ import annotations

from datetime import datetime
from typing import Any
import uuid

import main as legacy
import launcher_v100rc1 as rc1
from grade_cell_mapper_rc3 import map_grade_cells as safe_map_grade_cells

APP_VERSION = "1.0.0-rc3"


def map_grade_cells_normalized_rc3(page):
    changed = rc1.normalize_grade_view(page)
    if changed:
        page.wait_for_timeout(180)
    mapped = safe_map_grade_cells(page)
    setattr(mapped, "normalized_scroll_surfaces", changed)
    return mapped


def _create_preflight_plan_rc3(probe) -> None:
    page = probe._page
    cell_map = probe._cell_map

    print("\n============================================================")
    print(" SIEROOM 1.0 RC3 — PREVISUALIZAR ESCRITURA VERIFICADA")
    print("============================================================")
    print("Esta RC3 NO escribe notas. Además de validar alumno/competencia,")
    print("exige poder leer de forma confiable el valor actual de la celda.")

    if not cell_map.students or cell_map.student_count <= 0:
        print("No se pudo aislar la matrícula. Escritura bloqueada.")
        return
    if cell_map.mapped_student_count != cell_map.student_count:
        print("No todas las filas están asociadas a celdas. Escritura bloqueada.")
        return
    if probe.column_count <= 0:
        print("No se detectaron columnas de nota. Escritura bloqueada.")
        return

    print(f"\nMatrícula detectada: {cell_map.student_count} estudiantes")
    print(f"Columnas de nota detectadas: {probe.column_count}")
    print("\nCompetencias/columnas:")
    for col in probe.columns:
        idx = int(col.get("index") or 0) + 1
        label = col.get("semantic_header") or col.get("header") or ""
        print(f"  {idx}. {rc1._short_label(label)}")

    choice = legacy.prompt("\nP = preparar una escritura (NO ejecutarla) | ENTER = terminar: ").lower()
    if choice not in {"p", "plan", "previsualizar"}:
        return

    max_order = max([int(str(s.get("order") or 0)) for s in cell_map.students] or [1])
    raw_order = legacy.prompt(f"Número de orden del estudiante [1-{max_order}] (ENTER=1): ") or "1"
    raw_col = legacy.prompt(f"Columna [1-{probe.column_count}] (ENTER=1): ") or "1"
    proposed = legacy.prompt("Nota propuesta [A/B/C] (ENTER=A): ").strip().upper() or "A"

    try:
        order = int(raw_order)
        column = int(raw_col)
    except ValueError:
        print("Entrada inválida. Plan cancelado.")
        return

    if proposed not in {"A", "B", "C"}:
        print("Solo se admite A, B o C. Plan cancelado.")
        return
    if order < 1 or order > max_order or column < 1 or column > probe.column_count:
        print("Alumno/columna fuera de rango. Plan cancelado.")
        return

    student = rc1._find_student(cell_map, order)
    if not student:
        print("No se encontró exactamente al estudiante solicitado. Plan cancelado.")
        return
    cell = rc1._target_cell(student, column - 1)
    if not cell:
        print("No se encontró exactamente la celda solicitada. Plan cancelado.")
        return

    col = probe.columns[column - 1]
    label = col.get("semantic_header") or col.get("header") or ""
    context = rc1._selected_context(page)

    current_text = str(cell.get("text") or "").strip().upper()
    current_state = str(cell.get("value_state") or "unreadable")
    current_confident = bool(cell.get("value_confident"))
    current_source = str(cell.get("value_source") or "")
    raw_text = str(cell.get("raw_text") or "")
    sanitized_text = str(cell.get("sanitized_text") or "")

    plan_id = f"SIEWEB-{datetime.now().strftime('%Y%m%d-%H%M%S')}-{uuid.uuid4().hex[:8]}"
    safeguards = {
        "site_is_sieweb": "sieweb.com.pe" in str(context.get("url") or "").lower(),
        "gradebook_url": "registronotas" in str(context.get("url") or "").lower(),
        "roster_complete": cell_map.student_count == cell_map.mapped_student_count,
        "target_student_unique": True,
        "target_cell_found": True,
        "grade_allowed": proposed in {"A", "B", "C"},
        "current_value_confident": current_confident,
        "current_value_state_allowed": current_state in {"blank", "grade"},
        "write_enabled": False,
    }
    safe = all(v for k, v in safeguards.items() if k != "write_enabled")

    payload = {
        "plan_id": plan_id,
        "created_at": datetime.now().isoformat(timespec="seconds"),
        "mode": "PREVIEW_ONLY_RC3",
        "writer_contract": "sieweb.save_grades_verified",
        "write_enabled": False,
        "context": context,
        "roster_count": cell_map.student_count,
        "target": {
            "student_order": order,
            "student_code": str(student.get("code") or ""),
            "student_name": str(student.get("name") or ""),
            "column": column,
            "column_label": str(label or ""),
            "current_visible_value": current_text,
            "current_value_state": current_state,
            "current_value_confident": current_confident,
            "current_value_source": current_source,
            "raw_cell_text": raw_text,
            "sanitized_cell_text": sanitized_text,
            "proposed_value": proposed,
        },
        "safeguards": safeguards,
        "preflight_ok": safe,
        "next_required_step": "explicitly enable one-cell verified write only after RC3 preflight is clean",
    }

    evidence_dir = legacy.app_data_root() / "evidence"
    path = legacy.save_json(evidence_dir, f"{plan_id}_verified_write_preflight.json", payload)

    if current_state == "blank" and current_confident:
        visible_label = "(vacío)"
    elif current_state == "grade" and current_confident:
        visible_label = current_text
    else:
        visible_label = "NO CONFIABLE"

    print("\n--- PLAN DE ESCRITURA VERIFICADA ---")
    print(f"Plan: {plan_id}")
    print(f"Alumno: orden {order} | {student.get('code')} | {student.get('name')}")
    print(f"Competencia: columna {column} | {rc1._short_label(label)}")
    print(f"Valor visible actual: {visible_label}")
    print(f"Lectura del valor actual: {'CONFIABLE' if current_confident else 'NO CONFIABLE'} | estado={current_state} | fuente={current_source or '-'}")
    if not current_confident:
        print(f"Texto bruto detectado: {raw_text[:140] or '(vacío)'}")
        print(f"Texto saneado: {sanitized_text[:140] or '(vacío)'}")
    print(f"Nota propuesta: {proposed}")
    print(f"Preflight: {'OK' if safe else 'BLOQUEADO'}")
    print(f"Evidencia: {path}")
    print("\nESCRITURA BLOQUEADA EN RC3: no se modificó SIEweb.")
    if safe:
        print("El plan quedó limpio para conectar luego una sola escritura verificada.")
    else:
        print("No se habilitará ninguna escritura mientras falle una salvaguarda.")


def print_grade_cell_probe_rc3(probe) -> None:
    print("\n--- PRECHECK DE LIBRETA ---")
    print(f"Estudiantes: {probe._cell_map.student_count}")
    print(f"Estudiantes con celdas asociadas: {probe._cell_map.mapped_student_count}")
    print(f"Columnas: {probe.column_count}")
    for col in probe.columns:
        idx = int(col.get("index") or 0) + 1
        label = col.get("semantic_header") or col.get("header") or ""
        print(f"  {idx}. {rc1._short_label(label)}")
    _create_preflight_plan_rc3(probe)


legacy.APP_VERSION = APP_VERSION
legacy.map_grade_cells = map_grade_cells_normalized_rc3
legacy.probe_grade_cells = rc1.probe_grade_cells_preview
legacy.print_grade_cell_probe = print_grade_cell_probe_rc3


if __name__ == "__main__":
    legacy.main()
