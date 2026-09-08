from __future__ import annotations

from datetime import datetime

import main as legacy
import launcher_v091 as prev
import launcher_v093 as v093
from editor_component_probe_v2 import inspect_editor_component_v2

APP_VERSION = "0.9.8"


def _print_result(result, evidence_path) -> None:
    print("\n--- COMPONENTE VUE REAL DESDE Symbol(_assign) (CDP, SOLO LECTURA) ---")
    print(f"CDP disponible: {'sí' if result.cdp_supported else 'no'}")
    print(f"Editor activo detectado: {'sí' if result.editor_detected else 'no'}")
    print(f"Symbol(_assign) localizado: {'sí' if result.assign_function_found else 'no'}")
    print(f"Componente capturado detrás de e.nota=a: {'sí' if result.component_found else 'no'}")
    if result.component_label:
        print(f"Ruta del componente: {result.component_label}")
    if result.component_description:
        print(f"Descripción remota: {result.component_description}")
    print(f"Tiempo de análisis: {result.elapsed_ms} ms")

    if result.properties:
        print("\nPropiedades/funciones relevantes del componente:")
        for item in result.properties[:60]:
            depth = item.get('depth')
            name = str(item.get('name') or '')
            typ = str(item.get('type') or '-')
            desc = str(item.get('description') or '').replace('\n', ' ')
            getter = str(item.get('getter') or '').replace('\n', ' ')
            setter = str(item.get('setter') or '').replace('\n', ' ')
            print(f"  depth={depth} | {name} | {typ}")
            if desc:
                print(f"     value/function -> {desc[:1000]}")
            if getter:
                print(f"     getter -> {getter[:900]}")
            if setter:
                print(f"     setter -> {setter[:900]}")
    else:
        print("No se encontraron todavía propiedades de persistencia en el componente capturado.")

    print(f"\nEscape enviado: {'sí' if result.escape_sent else 'no'}")
    print(f"Editor cerrado tras Escape: {'sí' if result.editor_closed_after_escape else 'no'}")
    if result.error:
        print(f"Detalle: {result.error}")
    print(f"Evidencia JSON: {evidence_path}")
    if result.editor_detected and result.editor_closed_after_escape:
        print("OK: inspección terminada sin escribir ni guardar ninguna calificación.")
    else:
        print("AVISO: no realizar pruebas de escritura todavía.")


def maybe_run_component_probe_v2(probe) -> None:
    page = getattr(probe, '_page', None)
    cell_map = getattr(probe, '_cell_map', None)
    if page is None or cell_map is None or not getattr(cell_map, 'students', None):
        return

    print("\n--- SIGUIENTE PRUEBA OPCIONAL ---")
    print("E = abrir UNA celda y seguir Symbol(_assign) hasta el componente que contiene e.nota. NO escribe nada.")
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
        legacy.prompt("\nPresiona ENTER para cerrar...")
        raise SystemExit(0)
    if order < 1 or order > max_order or column < 1 or column > cell_map.column_count:
        print("Orden/columna fuera de rango. No se realizó ningún clic.")
        legacy.prompt("\nPresiona ENTER para cerrar...")
        raise SystemExit(0)

    print("Abriendo editor de prueba...")
    if not v093._open_editor_readonly(page, cell_map, order, column):
        print("No se pudo abrir el editor. No se escribió nada.")
        try:
            page.keyboard.press('Escape')
        except Exception:
            pass
        legacy.prompt("\nPresiona ENTER para cerrar...")
        raise SystemExit(0)

    print("Editor abierto. Siguiendo Symbol(_assign) -> closure -> componente Vue...")
    result = inspect_editor_component_v2(page, budget_seconds=8.0)
    evidence_dir = legacy.app_data_root() / 'evidence'
    evidence_dir.mkdir(parents=True, exist_ok=True)
    stamp = datetime.now().strftime('%Y%m%d_%H%M%S')
    path = legacy.save_json(evidence_dir, f"{stamp}_sieweb_editor_component_v2.json", result.as_dict())
    _print_result(result, path)

    print("\nPRUEBA TERMINADA. La ventana se quedará abierta para que puedas leer y tomar captura.")
    legacy.prompt("Presiona ENTER cuando quieras cerrar el agente...")
    raise SystemExit(0)


legacy.APP_VERSION = APP_VERSION
legacy.map_grade_cells = prev.map_grade_cells_normalized
legacy.probe_grade_cells = prev.probe_grade_cells_with_framework


def print_grade_cell_probe_v098(probe) -> None:
    prev.original_print(probe)
    prev.print_event_report(getattr(probe, 'event_listener_report', None))
    prev.print_vue_report(getattr(probe, 'vue_event_report', None))
    maybe_run_component_probe_v2(probe)


legacy.print_grade_cell_probe = print_grade_cell_probe_v098

if __name__ == '__main__':
    legacy.main()
