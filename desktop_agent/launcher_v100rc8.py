from __future__ import annotations

from datetime import datetime
import uuid

import main as legacy
import launcher_v100rc1 as rc1
import launcher_v100rc3 as rc3
import launcher_v100rc7 as rc7  # carga las correcciones RC7 y autenticación real

from verified_writer_bridge import VerifiedWriterBridgeError, prepare_one_cell_write


APP_VERSION = "1.0.0-rc8"
MAX_BATCH = 12


def _fmt(value: str) -> str:
    return value if value else "(vacío)"


def _collect_batch(probe):
    cell_map = probe._cell_map
    if not cell_map.students or cell_map.student_count <= 0:
        print("No se pudo aislar la matrícula. Lote bloqueado.")
        return []
    if cell_map.mapped_student_count != cell_map.student_count:
        print("No todas las filas están asociadas a celdas. Lote bloqueado.")
        return []
    if probe.column_count <= 0:
        print("No se detectaron columnas de nota. Lote bloqueado.")
        return []

    print("\n============================================================")
    print(" SIEROOM 1.0 RC8 — PREFLIGHT DE LOTE (NO ESCRIBE)")
    print("============================================================")
    print("RC8 prepara varias notas y valida cada destino por DOM + API.")
    print("NO ejecuta escrituras. El objetivo es aprobar un lote completo")
    print("antes de habilitar la ejecución secuencial en la siguiente etapa.")

    print(f"\nMatrícula detectada: {cell_map.student_count} estudiantes")
    print(f"Columnas de nota detectadas: {probe.column_count}")
    print("\nCompetencias/columnas:")
    for col in probe.columns:
        idx = int(col.get("index") or 0) + 1
        label = col.get("semantic_header") or col.get("header") or ""
        print(f"  {idx}. {rc1._short_label(label)}")

    choice = legacy.prompt("\nB = preparar un lote | ENTER = terminar: ").strip().lower()
    if choice not in {"b", "batch", "lote"}:
        return []

    raw_count = legacy.prompt(f"¿Cuántas celdas deseas preparar? [1-{MAX_BATCH}] (ENTER=2): ") or "2"
    try:
        count = int(raw_count)
    except ValueError:
        print("Cantidad inválida. Lote cancelado.")
        return []
    if count < 1 or count > MAX_BATCH:
        print(f"RC8 admite entre 1 y {MAX_BATCH} celdas por lote. Lote cancelado.")
        return []

    max_order = max([int(str(s.get("order") or 0)) for s in cell_map.students] or [1])
    items = []
    seen = set()

    print("\nIngresa cada celda. Nada se escribirá en esta RC8.")
    for i in range(1, count + 1):
        print(f"\n--- Celda {i} de {count} ---")
        raw_order = legacy.prompt(f"Alumno por número de orden [1-{max_order}]: ")
        raw_col = legacy.prompt(f"Columna [1-{probe.column_count}]: ")
        grade = legacy.prompt("Nota propuesta [A/B/C]: ").strip().upper()
        try:
            order = int(raw_order)
            column = int(raw_col)
        except ValueError:
            print("Entrada inválida. Lote cancelado completo.")
            return []
        if order < 1 or order > max_order or column < 1 or column > probe.column_count:
            print("Alumno/columna fuera de rango. Lote cancelado completo.")
            return []
        if grade not in {"A", "B", "C"}:
            print("Solo se admite A, B o C. Lote cancelado completo.")
            return []

        student = rc1._find_student(cell_map, order)
        if not student:
            print("No se encontró exactamente al estudiante. Lote cancelado completo.")
            return []
        cell = rc1._target_cell(student, column - 1)
        if not cell:
            print("No se encontró exactamente la celda. Lote cancelado completo.")
            return []

        code = str(student.get("code") or "").strip()
        key = (code, column)
        if key in seen:
            print("La misma celda fue incluida dos veces. Lote cancelado completo.")
            return []
        seen.add(key)

        current = str(cell.get("text") or "").strip().upper()
        state = str(cell.get("value_state") or "unreadable")
        confident = bool(cell.get("value_confident"))
        if not confident or state not in {"blank", "grade"}:
            print("La lectura DOM de una celda no es confiable. Lote cancelado completo.")
            return []

        label = str(
            probe.columns[column - 1].get("semantic_header")
            or probe.columns[column - 1].get("header")
            or ""
        )
        items.append({
            "order": order,
            "column": column,
            "grade": grade,
            "student": student,
            "cell": cell,
            "code": code,
            "name": str(student.get("name") or "").strip(),
            "dom_current": current,
            "label": label,
        })

    return items


def _batch_preflight(probe) -> None:
    page = probe._page
    cell_map = probe._cell_map
    items = _collect_batch(probe)
    if not items:
        return

    dom_codes = [str(s.get("code") or "").strip() for s in cell_map.students]
    prepared_items = []
    errors = []

    print("\nRevalidando el lote contra la sesión real de SIEweb (solo lectura)...")
    for idx, item in enumerate(items, start=1):
        print(f"  Validando {idx}/{len(items)}: {item['code']} | columna {item['column']} | {item['grade']}...")
        try:
            prepared = prepare_one_cell_write(
                page,
                dom_student_codes=dom_codes,
                student_code=item["code"],
                student_name=item["name"],
                column_number=int(item["column"]),
                column_label=item["label"],
                dom_current=item["dom_current"],
                proposed=item["grade"],
            )
            prepared_items.append((item, prepared))
        except VerifiedWriterBridgeError as exc:
            errors.append({
                "student_code": item["code"],
                "student_name": item["name"],
                "column": item["column"],
                "proposed": item["grade"],
                "error": str(exc),
            })
            print(f"    BLOQUEADO: {exc}")

    batch_id = f"SIEWEB-RC8-{datetime.now().strftime('%Y%m%d-%H%M%S')}-{uuid.uuid4().hex[:8]}"
    evidence_dir = legacy.app_data_root() / "evidence"

    public_items = []
    for item, prepared in prepared_items:
        public_items.append({
            "student_order": item["order"],
            "student_code": prepared.student_code,
            "student_name": prepared.student_name,
            "column": item["column"],
            "column_label": prepared.column_label,
            "header_id": prepared.header_id,
            "criterion_level": prepared.criterion_level,
            "target_kind": prepared.target_kind,
            "criterion_text": prepared.criterion_text,
            "criterion_match_score": prepared.criterion_match_score,
            "dom_current": prepared.dom_current,
            "api_current": prepared.api_current,
            "proposed": prepared.proposed,
            "would_write": prepared.api_current != prepared.proposed,
            "confirmation_phrase": prepared.confirmation_phrase,
        })

    payload = {
        "batch_id": batch_id,
        "created_at": datetime.now().isoformat(timespec="seconds"),
        "mode": "BATCH_PREFLIGHT_ONLY_RC8",
        "write_enabled": False,
        "requested_count": len(items),
        "approved_count": len(prepared_items),
        "blocked_count": len(errors),
        "preflight_ok": bool(len(prepared_items) == len(items) and not errors),
        "items": public_items,
        "errors": errors,
    }
    path = legacy.save_json(evidence_dir, f"{batch_id}_batch_preflight.json", payload)

    print("\n============================================================")
    print(" RESULTADO DEL PREFLIGHT DE LOTE")
    print("============================================================")
    for i, row in enumerate(public_items, start=1):
        action = "ESCRIBIRÍA" if row["would_write"] else "YA PRESENTE / SIN PUT"
        print(
            f"{i}. {row['student_code']} | {row['student_name']} | "
            f"col {row['column']} | {row['target_kind']} | "
            f"DOM {_fmt(row['dom_current'])} | API {_fmt(row['api_current'])} | "
            f"nuevo {row['proposed']} | {action}"
        )
    if errors:
        print("\nCeldas bloqueadas:")
        for err in errors:
            print(
                f"- {err['student_code']} | {err['student_name']} | "
                f"col {err['column']} | {err['proposed']} | {err['error']}"
            )

    if payload["preflight_ok"]:
        print(f"\n✅ PREFLIGHT DE LOTE OK: {len(prepared_items)} celdas aprobadas.")
        print("RC8 NO escribió ninguna nota.")
        print("Este lote ya está listo para el siguiente paso: ejecución secuencial")
        print("con parada inmediata ante cualquier fallo de verificación.")
    else:
        print("\n❌ PREFLIGHT DE LOTE BLOQUEADO.")
        print("RC8 no escribió ninguna nota y el lote completo queda sin autorizar.")
    print(f"Evidencia: {path}")
    legacy.prompt("\nPresiona ENTER cuando quieras cerrar el agente...")
    raise SystemExit(0)


def print_grade_cell_probe_rc8(probe) -> None:
    print("\n--- PRECHECK DE LIBRETA ---")
    print(f"Estudiantes: {probe._cell_map.student_count}")
    print(f"Estudiantes con celdas asociadas: {probe._cell_map.mapped_student_count}")
    print(f"Columnas: {probe.column_count}")
    for col in probe.columns:
        idx = int(col.get("index") or 0) + 1
        label = col.get("semantic_header") or col.get("header") or ""
        print(f"  {idx}. {rc1._short_label(label)}")
    _batch_preflight(probe)


legacy.APP_VERSION = APP_VERSION
legacy.map_grade_cells = rc3.map_grade_cells_normalized_rc3
legacy.probe_grade_cells = rc1.probe_grade_cells_preview
legacy.print_grade_cell_probe = print_grade_cell_probe_rc8


if __name__ == "__main__":
    legacy.main()
