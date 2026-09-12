from __future__ import annotations

from datetime import datetime

import main as legacy
import launcher_v091 as prev
import launcher_v093 as v093
from editor_component_probe import inspect_editor_component

APP_VERSION = "0.9.6"


def _print_result(result, evidence_path) -> None:
    print("\n--- COMPONENTE REAL DEL EDITOR (CDP, SOLO LECTURA) ---")
    print(f"CDP disponible: {'sí' if result.cdp_supported else 'no'}")
    print(f"Editor activo detectado: {'sí' if result.editor_detected else 'no'}")
    print(f"Objetos de componente capturados: {result.component_objects_found}")
    print(f"Tiempo de análisis: {result.elapsed_ms} ms")

    if result.component_summaries:
        for idx, summary in enumerate(result.component_summaries, 1):
            print(f"\nComponente {idx}: {summary.get('label','')}")
            if summary.get('error'):
                print(f"  error: {summary.get('error')}")
                continue
            if summary.get('tag'):
                print(f"  tag: {summary.get('tag')}")
            items = summary.get('items') or []
            if not items:
                print("  Sin propiedades objetivo visibles en este objeto.")
                continue
            for item in items[:50]:
                name = str(item.get('name') or '')
                typ = str(item.get('type') or '')
                depth = item.get('depth')
                text = str(item.get('text') or '').replace('\n', ' ')
                err = str(item.get('error') or '')
                print(f"  depth={depth} | {name} | {typ}")
                if text:
                    print(f"     {text[:900]}")
                if err:
                    print(f"     error={err[:300]}")
    else:
        print("No se pudo aislar todavía el objeto de componente capturado por los handlers.")

    print(f"\nEscape enviado: {'sí' if result.escape_sent else 'no'}")
    print(f"Editor cerrado tras Escape: {'sí' if result.editor_closed_after_escape else 'no'}")
    if result.error:
        print(f"Detalle: {result.error}")
    print(f"Evidencia JSON: {evidence_path}")
    if result.editor_detected and result.editor_closed_after_escape:
        print("OK: componente del editor inspeccionado sin escribir ni guardar ninguna calificación.")
    else:
        print("AVISO: no realizar pruebas de escritura todavía.")


def maybe_run_component_probe(probe) -> None:
    page = getattr(probe, '_page', None)
    cell_map = getattr(probe, '_cell_map', None)
    if page is None or cell_map is None or not getattr(cell_map, 'students', None):
        return

    print("\n--- SIGUIENTE PRUEBA OPCIONAL ---")
    print("E = abrir UNA celda y aislar el objeto real que contiene nota/blur/keydown. NO escribe nada.")
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

    print("Abriendo editor de prueba...")
    if not v093._open_editor_readonly(page, cell_map, order, column):
        print("No se pudo abrir el editor. No se escribió nada.")
        try:
            page.keyboard.press('Escape')
        except Exception:
            pass
        return

    print("Editor abierto. Buscando únicamente nota/blur/keydown/save en el componente...")
    result = inspect_editor_component(page, budget_seconds=8.0)
    evidence_dir = legacy.app_data_root() / 'evidence'
    evidence_dir.mkdir(parents=True, exist_ok=True)
    stamp = datetime.now().strftime('%Y%m%d_%H%M%S')
    path = legacy.save_json(evidence_dir, f"{stamp}_sieweb_editor_component_contract.json", result.as_dict())
    _print_result(result, path)


legacy.APP_VERSION = APP_VERSION
legacy.map_grade_cells = prev.map_grade_cells_normalized
legacy.probe_grade_cells = prev.probe_grade_cells_with_framework


def print_grade_cell_probe_v096(probe) -> None:
    prev.original_print(probe)
    prev.print_event_report(getattr(probe, 'event_listener_report', None))
    prev.print_vue_report(getattr(probe, 'vue_event_report', None))
    maybe_run_component_probe(probe)


legacy.print_grade_cell_probe = print_grade_cell_probe_v096

if __name__ == '__main__':
    legacy.main()
