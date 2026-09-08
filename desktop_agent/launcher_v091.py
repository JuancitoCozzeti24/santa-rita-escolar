from __future__ import annotations

from datetime import datetime
from typing import Any

import main as legacy
from editor_open_probe import normalize_grade_view
from editor_open_probe_v2 import probe_editor_open_v2
from event_listener_probe import inspect_grade_cell_event_listeners
from grade_cell_mapper import map_grade_cells as base_map_grade_cells
from grade_cell_probe import probe_grade_cells as base_probe_grade_cells
from vue_event_probe import inspect_vue_event_handlers


APP_VERSION = "0.9.1"


class EnrichedProbe:
    def __init__(self, base: Any, event_report: Any, vue_report: Any, page: Any, cell_map: Any) -> None:
        self._base = base
        self._page = page
        self._cell_map = cell_map
        self.event_listener_report = event_report
        self.vue_event_report = vue_report
        self.column_count = base.column_count
        self.probed_cell_count = base.probed_cell_count
        self.columns = base.columns
        self.cell_signatures = base.cell_signatures

    def as_dict(self) -> dict[str, Any]:
        payload = self._base.as_dict()
        payload["event_listener_report"] = self.event_listener_report.as_dict()
        payload["vue_event_report"] = self.vue_event_report.as_dict()
        return payload


def map_grade_cells_normalized(page):
    changed = normalize_grade_view(page)
    if changed:
        page.wait_for_timeout(180)
    mapped = base_map_grade_cells(page)
    setattr(mapped, "normalized_scroll_surfaces", changed)
    return mapped


def probe_grade_cells_with_framework(page, grade_cell_map):
    base = base_probe_grade_cells(page, grade_cell_map)
    event_report = inspect_grade_cell_event_listeners(page, base)
    vue_report = inspect_vue_event_handlers(page, base)
    return EnrichedProbe(base, event_report, vue_report, page, grade_cell_map)


def _collect_handler_text(report) -> str:
    chunks: list[str] = []
    if report is None:
        return ""
    for sample in report.samples:
        for node in sample.get("chain") or []:
            for listener in node.get("click_listeners") or []:
                for key in ("handler", "original_handler"):
                    details = listener.get(key) or {}
                    chunks.append(str(details.get("description") or ""))
                    for prop in details.get("properties") or []:
                        chunks.append(str(prop.get("value") or ""))
                    for nested in details.get("nested") or []:
                        nd = nested.get("details") or {}
                        chunks.append(str(nd.get("description") or ""))
                        for prop in nd.get("properties") or []:
                            chunks.append(str(prop.get("value") or ""))
    return "\n".join(chunks)


def print_event_report(report) -> None:
    print("\n--- EVENT LISTENERS DE CELDAS (CDP, SOLO LECTURA) ---")
    if report is None:
        print("No se generó reporte de listeners.")
        return
    print(f"CDP disponible: {'sí' if report.cdp_supported else 'no'}")
    print(f"Listeners relevantes detectados: {report.listener_count}")
    print("Tipos detectados: " + (", ".join(report.listener_types) if report.listener_types else "ninguno"))


def print_vue_report(report) -> None:
    print("\n--- VUE/QUASAR HANDLERS (CDP, SOLO LECTURA) ---")
    if report is None:
        print("No se generó reporte Vue/Quasar.")
        return
    print(f"CDP disponible: {'sí' if report.cdp_supported else 'no'}")
    print(f"Columnas inspeccionadas: {report.inspected_columns}")
    print(f"Handlers click encontrados: {report.handlers_found}")
    text = _collect_handler_text(report)
    print("\nContrato de interacción inferido:")
    print(f"  Celda → clickEdicion(): {'CONFIRMADO' if 'clickEdicion' in text else 'no confirmado'}")
    print(f"  Fila/ancestro → clickAlumno(...): {'CONFIRMADO' if 'clickAlumno' in text else 'no confirmado'}")


def _print_editor_probe(result, evidence_path) -> None:
    print("\n--- PRUEBA CONTROLADA V2: SELECCIÓN DE ALUMNO + APERTURA DE EDITOR ---")
    print(f"Estudiante: orden {result.student_order} | {result.student_code} | {result.student_name}")
    print(f"Columna: {result.column_index + 1} | {result.column_label[:160]}")
    print(f"Estudiante seleccionado antes: {result.selected_before or '(no aislado)'}")
    print(f"Estudiante seleccionado después del clic de fila: {result.selected_after_row_click or '(no aislado)'}")
    print(f"Selección del estudiante objetivo confirmada: {'sí' if result.row_selection_confirmed else 'no'}")
    print(f"Editor detectado tras segundo clic: {'sí' if result.editor_detected else 'no'}")
    if result.editor_detection_reasons:
        print("Razones de detección:")
        for reason in result.editor_detection_reasons[:12]:
            print(f"  - {reason}")
    print(f"Escape enviado: {'sí' if result.escape_sent else 'no'}")
    print(f"Editor cerrado después de Escape: {'sí' if result.editor_closed_after_escape else 'no'}")
    print(f"Texto de celda sin cambios: {'sí' if result.grade_text_unchanged else 'NO'}")
    print(f"Solicitudes de escritura al seleccionar fila: {len(result.network_requests_row_select)}")
    print(f"Solicitudes de escritura al abrir editor: {len(result.network_requests_editor_open)}")
    if result.active_after_open:
        a = result.active_after_open
        print(
            "activeElement tras abrir: "
            f"tag={a.get('tag') or '-'} | role={a.get('role') or '-'} | "
            f"type={a.get('type') or '-'} | class={str(a.get('class_name') or '')[:140]}"
        )
    if result.editor_elements:
        print("Elementos nuevos del editor (muestra):")
        for item in result.editor_elements[:12]:
            print(
                f"  {item.get('tag')} | role={item.get('role') or '-'} | "
                f"type={item.get('type') or '-'} | class={str(item.get('class_name',''))[:120]} | "
                f"placeholder={str(item.get('placeholder',''))[:100]}"
            )
    if result.error:
        print(f"Detalle: {result.error}")
    print(f"Evidencia JSON: {evidence_path}")
    if result.ok and result.grade_text_unchanged:
        print("OK: la prueba no escribió ni alteró el texto visible de la calificación.")
    else:
        print("AVISO: la prueba no pudo verificarse completamente; no realizar más interacciones.")


def maybe_run_editor_probe(probe) -> None:
    page = getattr(probe, "_page", None)
    cell_map = getattr(probe, "_cell_map", None)
    if page is None or cell_map is None or not getattr(cell_map, "students", None):
        return

    print("\n--- PRUEBA V2 DISPONIBLE (OPCIONAL) ---")
    print("E = seleccionar primero UN alumno y luego abrir UNA celda; no escribe y cierra con Escape.")
    print("ENTER = omitir y continuar en modo lectura.")
    choice = legacy.prompt("Elige E o ENTER: ").lower()
    if choice not in {"e", "editor"}:
        return

    max_order = max([int(str(s.get("order") or 0)) for s in cell_map.students] or [1])
    raw_order = legacy.prompt(f"Número de orden del estudiante [1-{max_order}] (ENTER=1): ") or "1"
    raw_col = legacy.prompt(f"Columna [1-{cell_map.column_count}] (ENTER=1): ") or "1"
    try:
        order = int(raw_order)
        column = int(raw_col)
    except ValueError:
        print("Entrada inválida. No se realizó ningún clic.")
        return
    if order < 1 or order > max_order or column < 1 or column > cell_map.column_count:
        print("Orden/columna fuera de rango. No se realizó ningún clic.")
        return

    evidence_dir = legacy.app_data_root() / "evidence"
    evidence_dir.mkdir(parents=True, exist_ok=True)
    result = probe_editor_open_v2(page, cell_map, order, column, evidence_dir)
    stamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    path = legacy.save_json(evidence_dir, f"{stamp}_sieweb_editor_open_probe_v2.json", result.as_dict())
    _print_editor_probe(result, path)


legacy.APP_VERSION = APP_VERSION
legacy.map_grade_cells = map_grade_cells_normalized
legacy.probe_grade_cells = probe_grade_cells_with_framework
original_print = legacy.print_grade_cell_probe


def print_grade_cell_probe_v091(probe) -> None:
    original_print(probe)
    print_event_report(getattr(probe, "event_listener_report", None))
    print_vue_report(getattr(probe, "vue_event_report", None))
    maybe_run_editor_probe(probe)


legacy.print_grade_cell_probe = print_grade_cell_probe_v091


if __name__ == "__main__":
    legacy.main()
