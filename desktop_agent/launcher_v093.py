from __future__ import annotations

from datetime import datetime

import main as legacy
import launcher_v091 as prev
from editor_handler_probe import inspect_editor_handlers

APP_VERSION = "0.9.3"


def _print_handler_details(details, indent="     ") -> None:
    if not details:
        return
    desc = str(details.get("description") or "").replace("\n", " ")
    if desc:
        print(f"{indent}función: {desc[:320]}")
    for prop in (details.get("properties") or [])[:12]:
        pdesc = str(prop.get("description") or "").replace("\n", " ")
        if pdesc:
            print(f"{indent}{prop.get('name')} -> {pdesc[:260]}")
    for nested in (details.get("nested") or [])[:8]:
        nd = nested.get("details") or {}
        desc2 = str(nd.get("description") or "").replace("\n", " ")
        if desc2:
            print(f"{indent}{nested.get('property')} => {desc2[:320]}")
        for prop in (nd.get("properties") or [])[:8]:
            pdesc = str(prop.get("description") or "").replace("\n", " ")
            if pdesc:
                print(f"{indent}  {prop.get('name')} -> {pdesc[:240]}")


def _print_result(result, evidence_path) -> None:
    print("\n--- CONTRATO DE GUARDADO DEL EDITOR (CDP, SOLO LECTURA) ---")
    print(f"CDP disponible: {'sí' if result.cdp_supported else 'no'}")
    print(f"Editor activo detectado: {'sí' if result.editor_detected else 'no'}")
    print(f"Listeners relevantes encontrados: {result.handlers_found}")
    print("Tipos: " + (", ".join(result.event_types) if result.event_types else "ninguno"))
    print("Pistas de callbacks: " + (", ".join(result.callback_hints) if result.callback_hints else "ninguna todavía"))

    if result.listeners:
        print("\nCallbacks por evento (muestra):")
        for item in result.listeners[:20]:
            src = item.get("source_url") or f"scriptId={item.get('script_id','')}"
            print(f"  {item.get('type')} | ancestro={item.get('depth')} | línea={item.get('line_number')} | {src[:150]}")
            _print_handler_details(item.get("handler"))
            if item.get("original_handler"):
                print("     original:")
                _print_handler_details(item.get("original_handler"), indent="       ")

    print(f"\nEscape enviado: {'sí' if result.escape_sent else 'no'}")
    print(f"Editor cerrado tras Escape: {'sí' if result.editor_closed_after_escape else 'no'}")
    if result.error:
        print(f"Detalle: {result.error}")
    print(f"Evidencia JSON: {evidence_path}")
    if result.cdp_supported and result.editor_detected and result.editor_closed_after_escape:
        print("OK: handlers del editor inspeccionados sin escribir ni guardar ninguna calificación.")
    else:
        print("AVISO: no realizar pruebas de escritura todavía.")


def _open_editor_readonly(page, cell_map, order: int, column: int) -> bool:
    student = next((s for s in cell_map.students if int(str(s.get('order') or 0)) == order), None)
    if not student:
        return False
    cell = next((c for c in (student.get('grade_cells') or []) if int(c.get('column_index', -1)) == column - 1), None)
    if not cell:
        return False
    rr = student.get('row_rect') or {}
    row_x = float(rr.get('x', 0)) + max(10.0, float(rr.get('width', 0)) * 0.72)
    row_y = float(rr.get('y', 0)) + float(rr.get('height', 0)) / 2
    cx = float(cell.get('x', 0)) + float(cell.get('width', 0)) / 2
    cy = float(cell.get('y', 0)) + float(cell.get('height', 0)) / 2
    page.mouse.click(row_x, row_y)
    page.wait_for_timeout(500)
    page.mouse.click(cx, cy)
    page.wait_for_timeout(600)
    tag = page.evaluate("() => { const e=document.activeElement; return e ? String(e.tagName||'').toLowerCase() : ''; }")
    return tag in {'input', 'textarea', 'select'}


def maybe_run_handler_probe(probe) -> None:
    page = getattr(probe, '_page', None)
    cell_map = getattr(probe, '_cell_map', None)
    if page is None or cell_map is None or not getattr(cell_map, 'students', None):
        return

    print("\n--- SIGUIENTE PRUEBA OPCIONAL ---")
    print("E = abrir UNA celda y leer los handlers input/change/blur/keydown. NO escribe nada.")
    print("ENTER = omitir.")
    choice = legacy.prompt("Elige E o ENTER: ").lower()
    if choice not in {'e', 'editor'}:
        return

    max_order = max([int(str(s.get('order') or 0)) for s in cell_map.students] or [1])
    raw_order = legacy.prompt(f"Número de orden del estudiante [1-{max_order}] (ENTER=1): ") or '1'
    raw_col = legacy.prompt(f"Columna [1-{cell_map.column_count}] (ENTER=1): ") or '1'
    try:
        order = int(raw_order)
        column = int(raw_col)
    except ValueError:
        print("Entrada inválida. No se realizó ningún clic.")
        return
    if order < 1 or order > max_order or column < 1 or column > cell_map.column_count:
        print("Orden/columna fuera de rango. No se realizó ningún clic.")
        return

    if not _open_editor_readonly(page, cell_map, order, column):
        print("No se pudo abrir el editor. No se escribió nada.")
        try:
            page.keyboard.press('Escape')
        except Exception:
            pass
        return

    result = inspect_editor_handlers(page)
    evidence_dir = legacy.app_data_root() / 'evidence'
    evidence_dir.mkdir(parents=True, exist_ok=True)
    stamp = datetime.now().strftime('%Y%m%d_%H%M%S')
    path = legacy.save_json(evidence_dir, f"{stamp}_sieweb_editor_handler_contract.json", result.as_dict())
    _print_result(result, path)


legacy.APP_VERSION = APP_VERSION
legacy.map_grade_cells = prev.map_grade_cells_normalized
legacy.probe_grade_cells = prev.probe_grade_cells_with_framework


def print_grade_cell_probe_v093(probe) -> None:
    prev.original_print(probe)
    prev.print_event_report(getattr(probe, 'event_listener_report', None))
    prev.print_vue_report(getattr(probe, 'vue_event_report', None))
    maybe_run_handler_probe(probe)


legacy.print_grade_cell_probe = print_grade_cell_probe_v093

if __name__ == '__main__':
    legacy.main()
