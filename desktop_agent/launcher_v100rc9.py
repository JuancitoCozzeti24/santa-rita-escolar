from __future__ import annotations

from datetime import datetime
import uuid

import main as legacy
import launcher_v100rc1 as rc1
import launcher_v100rc3 as rc3
import launcher_v100rc7 as rc7  # instala auth real + verificación DOM sin perder contexto

from verified_writer_bridge import (
    VerifiedWriterBridgeError,
    execute_one_cell_verified,
    prepare_one_cell_write,
)


APP_VERSION = "1.0.0-rc9"
MAX_BATCH = 6


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
    print(" SIEROOM 1.0 RC9 — LOTE SECUENCIAL VERIFICADO")
    print("============================================================")
    print("RC9 puede escribir un lote pequeño, pero SOLO después de validar")
    print("TODO el lote por DOM + API y exigir una confirmación exacta.")
    print("Cada celda se revalida justo antes de ejecutarse. Después de cada")
    print("operación exige verificación API + navegador. Si una falla, se detiene.")
    print("IMPORTANTE: no hace rollback automático de las celdas ya verificadas;")
    print("un rollback ciego sería más riesgoso que detener el lote.")

    print(f"\nMatrícula detectada: {cell_map.student_count} estudiantes")
    print(f"Columnas de nota detectadas: {probe.column_count}")
    print("\nCompetencias/columnas:")
    for col in probe.columns:
        idx = int(col.get("index") or 0) + 1
        label = col.get("semantic_header") or col.get("header") or ""
        print(f"  {idx}. {rc1._short_label(label)}")

    choice = legacy.prompt("\nB = preparar lote real verificado | ENTER = terminar: ").strip().lower()
    if choice not in {"b", "batch", "lote"}:
        return []

    raw_count = legacy.prompt(f"¿Cuántas celdas deseas incluir? [1-{MAX_BATCH}] (ENTER=2): ") or "2"
    try:
        count = int(raw_count)
    except ValueError:
        print("Cantidad inválida. Lote cancelado.")
        return []
    if count < 1 or count > MAX_BATCH:
        print(f"RC9 admite entre 1 y {MAX_BATCH} celdas por lote. Lote cancelado.")
        return []

    max_order = max([int(str(s.get("order") or 0)) for s in cell_map.students] or [1])
    items = []
    seen = set()

    print("\nIngresa cada celda. AÚN no se escribirá nada; primero se hará el preflight completo.")
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
            "code": code,
            "name": str(student.get("name") or "").strip(),
            "dom_current": current,
            "label": label,
        })

    return items


def _remap_current_cell(page, *, code: str, column: int) -> tuple[str, str, bool]:
    mapped = rc3.map_grade_cells_normalized_rc3(page)
    matches = [
        s for s in (mapped.students or [])
        if str(s.get("code") or "").strip() == str(code).strip()
    ]
    if len(matches) != 1:
        raise VerifiedWriterBridgeError(
            f"El alumno {code} aparece {len(matches)} veces en el DOM actual."
        )
    cell = rc1._target_cell(matches[0], int(column) - 1)
    if not cell:
        raise VerifiedWriterBridgeError("No se localizó la celda objetivo en el DOM actual.")
    text = str(cell.get("text") or "").strip().upper()
    state = str(cell.get("value_state") or "unreadable")
    confident = bool(cell.get("value_confident"))
    if not confident or state not in {"blank", "grade"}:
        raise VerifiedWriterBridgeError(
            f"La lectura DOM actual no es confiable (estado={state}, confiable={confident})."
        )
    return text, state, confident


def _batch_preflight_and_execute(probe) -> None:
    page = probe._page
    cell_map = probe._cell_map
    items = _collect_batch(probe)
    if not items:
        return

    dom_codes = [str(s.get("code") or "").strip() for s in cell_map.students]
    prepared_rows = []
    errors = []

    print("\nRevalidando TODO el lote contra la sesión real de SIEweb (solo lectura)...")
    for idx, item in enumerate(items, start=1):
        print(f"  Preflight {idx}/{len(items)}: {item['code']} | columna {item['column']} | {item['grade']}...")
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
            prepared_rows.append((item, prepared))
        except VerifiedWriterBridgeError as exc:
            errors.append({
                "student_code": item["code"],
                "student_name": item["name"],
                "column": item["column"],
                "proposed": item["grade"],
                "error": str(exc),
            })
            print(f"    BLOQUEADO: {exc}")

    batch_id = f"SIEWEB-RC9-{datetime.now().strftime('%Y%m%d-%H%M%S')}-{uuid.uuid4().hex[:8]}"
    evidence_dir = legacy.app_data_root() / "evidence"

    public_items = []
    for item, prepared in prepared_rows:
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
        })

    preflight_ok = bool(len(prepared_rows) == len(items) and not errors)
    preflight_payload = {
        "batch_id": batch_id,
        "created_at": datetime.now().isoformat(timespec="seconds"),
        "mode": "SEQUENTIAL_VERIFIED_BATCH_RC9",
        "write_enabled": True,
        "requested_count": len(items),
        "approved_count": len(prepared_rows),
        "blocked_count": len(errors),
        "preflight_ok": preflight_ok,
        "items": public_items,
        "errors": errors,
    }
    preflight_path = legacy.save_json(
        evidence_dir,
        f"{batch_id}_batch_preflight.json",
        preflight_payload,
    )

    print("\n============================================================")
    print(" PREFLIGHT FINAL DEL LOTE RC9")
    print("============================================================")
    for i, row in enumerate(public_items, start=1):
        action = "ESCRIBIR" if row["would_write"] else "YA PRESENTE / SIN PUT"
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

    print(f"\nEvidencia preflight: {preflight_path}")
    if not preflight_ok:
        print("\n❌ LOTE BLOQUEADO. No se escribió ninguna nota.")
        legacy.prompt("Presiona ENTER para cerrar el agente...")
        raise SystemExit(0)

    phrase = f"ESCRIBIR LOTE {len(items)}"
    print("\nATENCIÓN: a partir de la confirmación RC9 puede modificar varias celdas.")
    print("Cada una se ejecutará y verificará por separado. Ante el primer fallo, se detiene.")
    typed = legacy.prompt(f"Para autorizar el lote escribe exactamente: {phrase}\n> ").strip().upper()
    if typed != phrase:
        print("\nCANCELADO: la frase no coincide. No se escribió ninguna nota.")
        legacy.prompt("Presiona ENTER para cerrar el agente...")
        raise SystemExit(0)

    execution_rows = []
    stopped = False
    stop_reason = ""

    print("\n============================================================")
    print(" EJECUCIÓN SECUENCIAL RC9")
    print("============================================================")

    for idx, original in enumerate(items, start=1):
        print(
            f"\n[{idx}/{len(items)}] {original['code']} | {original['name']} | "
            f"columna {original['column']} | {original['grade']}"
        )
        try:
            # Releer DOM actual DESPUÉS de todas las celdas previas ya verificadas.
            dom_current, _, _ = _remap_current_cell(
                page,
                code=original["code"],
                column=int(original["column"]),
            )
            current_map = rc3.map_grade_cells_normalized_rc3(page)
            current_codes = [
                str(s.get("code") or "").strip()
                for s in (current_map.students or [])
                if str(s.get("code") or "").strip()
            ]

            # Re-preparar justo antes de escribir para que el snapshot API incluya
            # todas las operaciones anteriores ya verificadas del mismo lote.
            prepared = prepare_one_cell_write(
                page,
                dom_student_codes=current_codes,
                student_code=original["code"],
                student_name=original["name"],
                column_number=int(original["column"]),
                column_label=original["label"],
                dom_current=dom_current,
                proposed=original["grade"],
            )
            print(
                f"  Revalidado: API {_fmt(prepared.api_current)} → {prepared.proposed} | "
                f"{prepared.target_kind}"
            )

            result = execute_one_cell_verified(prepared)
            if not bool(result.get("verified")):
                raise VerifiedWriterBridgeError(
                    f"La relectura API no verificó la celda (observado={_fmt(str(result.get('observed') or ''))})."
                )

            dom_check = rc7._verify_dom_after_write_rc7(
                page,
                student_code=prepared.student_code,
                column=int(original["column"]),
                expected=prepared.proposed,
            )
            if not bool(dom_check.get("ok")):
                raise VerifiedWriterBridgeError(
                    "La API confirmó la operación pero el navegador no confirmó la misma celda: "
                    + str(dom_check.get("error") or "sin detalle")
                )

            execution_rows.append({
                "index": idx,
                "student_code": prepared.student_code,
                "student_name": prepared.student_name,
                "column": int(original["column"]),
                "target_kind": prepared.target_kind,
                "header_id": prepared.header_id,
                "before": prepared.api_current,
                "proposed": prepared.proposed,
                "observed_api": str(result.get("observed") or ""),
                "observed_dom": str(dom_check.get("observed") or ""),
                "write_sent": bool(result.get("write_sent")),
                "already_present": bool(result.get("already_present")),
                "verified_api": True,
                "verified_dom": True,
                "verified": True,
                "unexpected_grade_changes": result.get("unexpected_grade_changes") or [],
            })
            mode = "YA PRESENTE" if result.get("already_present") else "ESCRITA"
            print(f"  ✅ {mode} Y VERIFICADA POR API + NAVEGADOR")

        except VerifiedWriterBridgeError as exc:
            stopped = True
            stop_reason = str(exc)
            execution_rows.append({
                "index": idx,
                "student_code": original["code"],
                "student_name": original["name"],
                "column": int(original["column"]),
                "proposed": original["grade"],
                "verified": False,
                "error": str(exc),
            })
            print(f"  ❌ DETENIDO: {exc}")
            print("  RC9 no continuará con ninguna celda posterior.")
            break
        except Exception as exc:
            stopped = True
            stop_reason = f"Error inesperado: {exc}"
            execution_rows.append({
                "index": idx,
                "student_code": original["code"],
                "student_name": original["name"],
                "column": int(original["column"]),
                "proposed": original["grade"],
                "verified": False,
                "error": stop_reason,
            })
            print(f"  ❌ DETENIDO: {stop_reason}")
            print("  RC9 no continuará con ninguna celda posterior.")
            break

    fully_verified = bool(not stopped and len(execution_rows) == len(items) and all(r.get("verified") for r in execution_rows))
    final_payload = {
        **preflight_payload,
        "execution_started_at": datetime.now().isoformat(timespec="seconds"),
        "execution_results": execution_rows,
        "fully_verified": fully_verified,
        "stopped": stopped,
        "stop_reason": stop_reason,
        "verified_count": sum(1 for r in execution_rows if r.get("verified")),
        "written_count": sum(1 for r in execution_rows if r.get("verified") and r.get("write_sent")),
        "already_present_count": sum(1 for r in execution_rows if r.get("verified") and r.get("already_present")),
    }
    result_path = legacy.save_json(
        evidence_dir,
        f"{batch_id}_batch_result.json",
        final_payload,
    )

    print("\n============================================================")
    print(" RESULTADO FINAL RC9")
    print("============================================================")
    if fully_verified:
        print(f"✅ LOTE COMPLETO VERIFICADO: {len(items)}/{len(items)} celdas.")
        print(f"Escrituras reales enviadas: {final_payload['written_count']}")
        print(f"Ya estaban presentes: {final_payload['already_present_count']}")
        print("Todas las celdas fueron confirmadas por API + navegador.")
    else:
        print("⚠️ LOTE DETENIDO ANTES DE COMPLETARSE.")
        print(f"Celdas verificadas antes/durante la parada: {final_payload['verified_count']}/{len(items)}")
        print(f"Motivo: {stop_reason or 'sin detalle'}")
        print("Las celdas anteriores que ya quedaron verificadas NO fueron revertidas automáticamente.")
    print(f"Evidencia final: {result_path}")
    legacy.prompt("\nPresiona ENTER cuando quieras cerrar el agente...")
    raise SystemExit(0)


def print_grade_cell_probe_rc9(probe) -> None:
    print("\n--- PRECHECK DE LIBRETA ---")
    print(f"Estudiantes: {probe._cell_map.student_count}")
    print(f"Estudiantes con celdas asociadas: {probe._cell_map.mapped_student_count}")
    print(f"Columnas: {probe.column_count}")
    for col in probe.columns:
        idx = int(col.get("index") or 0) + 1
        label = col.get("semantic_header") or col.get("header") or ""
        print(f"  {idx}. {rc1._short_label(label)}")
    _batch_preflight_and_execute(probe)


legacy.APP_VERSION = APP_VERSION
legacy.map_grade_cells = rc3.map_grade_cells_normalized_rc3
legacy.probe_grade_cells = rc1.probe_grade_cells_preview
legacy.print_grade_cell_probe = print_grade_cell_probe_rc9


if __name__ == "__main__":
    legacy.main()
