from __future__ import annotations

from datetime import datetime
import uuid

import main as legacy
import launcher_v100rc1 as rc1
import launcher_v100rc3 as rc3
from browser_auth_rc5 import install as install_browser_auth

install_browser_auth()

from verified_writer_bridge import (
    VerifiedWriterBridgeError,
    execute_one_cell_verified,
    prepare_one_cell_write,
)


APP_VERSION = "1.0.0-rc5"


def _fmt_grade(value: str) -> str:
    return value if value else "(vacío)"


def _one_cell_verified_write_rc5(probe) -> None:
    page = probe._page
    cell_map = probe._cell_map

    print("\n============================================================")
    print(" SIEROOM 1.0 RC5 — UNA SOLA ESCRITURA REAL VERIFICADA")
    print("============================================================")
    print("RC5 corrige el traspaso de sesión: toma los headers reales de")
    print("una petición autenticada del navegador y valida la sesión con")
    print("una lectura inocua antes de permitir cualquier escritura.")
    print("RC5 puede modificar exactamente UNA celda y no sobrescribe una")
    print("nota distinta ya existente.")

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

    choice = legacy.prompt(
        "\nW = preparar UNA escritura real verificada | ENTER = terminar: "
    ).strip().lower()
    if choice not in {"w", "write", "escribir"}:
        return

    max_order = max([int(str(s.get("order") or 0)) for s in cell_map.students] or [1])
    raw_order = legacy.prompt(
        f"Número de orden del estudiante [1-{max_order}] (ENTER=1): "
    ) or "1"
    raw_col = legacy.prompt(
        f"Columna [1-{probe.column_count}] (ENTER=1): "
    ) or "1"
    proposed = legacy.prompt("Nota propuesta [A/B/C] (ENTER=A): ").strip().upper() or "A"

    try:
        order = int(raw_order)
        column = int(raw_col)
    except ValueError:
        print("Entrada inválida. Operación cancelada; no se escribió nada.")
        return

    if proposed not in {"A", "B", "C"}:
        print("Solo se admite A, B o C. Operación cancelada; no se escribió nada.")
        return
    if order < 1 or order > max_order or column < 1 or column > probe.column_count:
        print("Alumno/columna fuera de rango. Operación cancelada; no se escribió nada.")
        return

    student = rc1._find_student(cell_map, order)
    if not student:
        print("No se encontró exactamente al estudiante. No se escribió nada.")
        return
    cell = rc1._target_cell(student, column - 1)
    if not cell:
        print("No se encontró exactamente la celda. No se escribió nada.")
        return

    current_text = str(cell.get("text") or "").strip().upper()
    current_state = str(cell.get("value_state") or "unreadable")
    current_confident = bool(cell.get("value_confident"))
    label = str(
        probe.columns[column - 1].get("semantic_header")
        or probe.columns[column - 1].get("header")
        or ""
    )

    if not current_confident or current_state not in {"blank", "grade"}:
        print("La lectura DOM actual no es confiable. Escritura bloqueada.")
        return

    dom_codes = [str(s.get("code") or "").strip() for s in cell_map.students]
    print("\nRevalidando la misma libreta por el writer verificado de SIEweb...")
    print("RC5 está validando primero la sesión real del navegador (solo lectura)...")
    try:
        prepared = prepare_one_cell_write(
            page,
            dom_student_codes=dom_codes,
            student_code=str(student.get("code") or "").strip(),
            student_name=str(student.get("name") or "").strip(),
            column_number=column,
            column_label=label,
            dom_current=current_text,
            proposed=proposed,
        )
    except VerifiedWriterBridgeError as exc:
        print("\n❌ PREFLIGHT API BLOQUEADO")
        print(str(exc))
        print("No se escribió ninguna nota.")
        legacy.prompt("\nPresiona ENTER para cerrar esta prueba...")
        raise SystemExit(0)

    plan_id = f"SIEWEB-RC5-{datetime.now().strftime('%Y%m%d-%H%M%S')}-{uuid.uuid4().hex[:8]}"
    evidence_dir = legacy.app_data_root() / "evidence"
    preflight_payload = {
        "plan_id": plan_id,
        "created_at": datetime.now().isoformat(timespec="seconds"),
        "mode": "ONE_CELL_VERIFIED_WRITE_RC5",
        "write_sent": False,
        "prepared": prepared.public_dict(),
    }
    preflight_path = legacy.save_json(
        evidence_dir,
        f"{plan_id}_one_cell_write_preflight.json",
        preflight_payload,
    )

    print("\n--- CONFIRMACIÓN DE UNA SOLA ESCRITURA REAL ---")
    print(
        f"Contexto: {prepared.browser_context['section']} | "
        f"Matemática {prepared.browser_context['course_code']} | "
        f"Período {prepared.browser_context['period']} | {prepared.browser_context['year']}"
    )
    print(
        f"Alumno: orden {order} | {prepared.student_code} | {prepared.student_name}"
    )
    print(f"Columna visible: {column} | {rc1._short_label(prepared.column_label)}")
    print(
        f"Destino API: header_id={prepared.header_id} | "
        f"nivelEva={prepared.criterion_level} | {prepared.target_kind}"
    )
    print(f"Criterio API: {rc1._short_label(prepared.criterion_text)}")
    print(f"Coincidencia columna↔API: {prepared.criterion_match_score:.2f}")
    print(f"Valor actual DOM: {_fmt_grade(prepared.dom_current)}")
    print(f"Valor actual API: {_fmt_grade(prepared.api_current)}")
    print(f"Valor nuevo: {prepared.proposed}")
    print("Sesión navegador→writer: VERIFICADA por lectura API.")
    print("Alcance RC5: exactamente UNA celda; sin notificación masiva.")
    print(f"Evidencia preflight: {preflight_path}")

    if prepared.api_current == prepared.proposed:
        print("\nLa celda ya contiene el valor solicitado. No hace falta enviar un PUT.")
    else:
        print("\nATENCIÓN: la siguiente confirmación SÍ puede modificar SIEweb.")

    phrase = prepared.confirmation_phrase
    typed = legacy.prompt(
        f"Para autorizar ESTA única celda escribe exactamente: {phrase}\n> "
    ).strip().upper()
    if typed != phrase:
        print("\nCANCELADO: la frase no coincide. No se escribió nada.")
        legacy.prompt("Presiona ENTER para cerrar esta prueba...")
        raise SystemExit(0)

    print("\nEjecutando writer verificado para UNA celda...")
    try:
        result = execute_one_cell_verified(prepared)
    except VerifiedWriterBridgeError as exc:
        failure_payload = {
            **preflight_payload,
            "write_sent": True,
            "verified": False,
            "error": str(exc),
        }
        failure_path = legacy.save_json(
            evidence_dir,
            f"{plan_id}_one_cell_write_result.json",
            failure_payload,
        )
        print("\n❌ NO VERIFICADO")
        print(str(exc))
        print("El agente no continuará con ningún otro alumno.")
        print(f"Evidencia: {failure_path}")
        legacy.prompt("\nPresiona ENTER para cerrar esta prueba...")
        raise SystemExit(0)

    result_payload = {
        **preflight_payload,
        "write_sent": bool(result.get("write_sent")),
        "verified": bool(result.get("verified")),
        "result": result,
    }
    result_path = legacy.save_json(
        evidence_dir,
        f"{plan_id}_one_cell_write_result.json",
        result_payload,
    )

    if result.get("verified"):
        print("\n✅ VERIFICADO")
        if result.get("already_present"):
            print("La nota ya estaba presente; no se envió ninguna escritura nueva.")
        else:
            print("SIEweb confirmó la actualización y la relectura API confirmó la misma celda.")
        print(
            f"{prepared.student_code} | {prepared.student_name} | "
            f"{prepared.target_kind} | {_fmt_grade(prepared.api_current)} → {result.get('observed')}"
        )
        print("Cambios inesperados en otras celdas: 0")
    else:
        print("\n❌ NO VERIFICADO")
        print(f"Valor observado después: {_fmt_grade(str(result.get('observed') or ''))}")
        unexpected = result.get("unexpected_grade_changes") or []
        print(f"Cambios inesperados detectados: {len(unexpected)}")
        print("No se continuará con más escrituras.")

    print(f"Evidencia final: {result_path}")
    print("\nPRUEBA RC5 TERMINADA. La ventana queda abierta para revisar el resultado.")
    legacy.prompt("Presiona ENTER cuando quieras cerrar el agente...")
    raise SystemExit(0)


def print_grade_cell_probe_rc5(probe) -> None:
    print("\n--- PRECHECK DE LIBRETA ---")
    print(f"Estudiantes: {probe._cell_map.student_count}")
    print(f"Estudiantes con celdas asociadas: {probe._cell_map.mapped_student_count}")
    print(f"Columnas: {probe.column_count}")
    for col in probe.columns:
        idx = int(col.get("index") or 0) + 1
        label = col.get("semantic_header") or col.get("header") or ""
        print(f"  {idx}. {rc1._short_label(label)}")
    _one_cell_verified_write_rc5(probe)


legacy.APP_VERSION = APP_VERSION
legacy.map_grade_cells = rc3.map_grade_cells_normalized_rc3
legacy.probe_grade_cells = rc1.probe_grade_cells_preview
legacy.print_grade_cell_probe = print_grade_cell_probe_rc5


if __name__ == "__main__":
    legacy.main()
