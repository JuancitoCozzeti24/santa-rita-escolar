from __future__ import annotations

from typing import Any

import main as legacy
from event_listener_probe import inspect_grade_cell_event_listeners
from grade_cell_probe import probe_grade_cells as base_probe_grade_cells
from vue_event_probe import inspect_vue_event_handlers


APP_VERSION = "0.8.0"


class EnrichedProbe:
    def __init__(self, base: Any, event_report: Any, vue_report: Any) -> None:
        self._base = base
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


def probe_grade_cells_with_framework(page, grade_cell_map):
    base = base_probe_grade_cells(page, grade_cell_map)
    event_report = inspect_grade_cell_event_listeners(page, base)
    vue_report = inspect_vue_event_handlers(page, base)
    return EnrichedProbe(base, event_report, vue_report)


def print_event_report(report) -> None:
    print("\n--- EVENT LISTENERS DE CELDAS (CDP, SOLO LECTURA) ---")
    if report is None:
        print("No se generó reporte de listeners.")
        return
    print(f"CDP disponible: {'sí' if report.cdp_supported else 'no'}")
    print(f"Listeners relevantes detectados: {report.listener_count}")
    print("Tipos detectados: " + (", ".join(report.listener_types) if report.listener_types else "ninguno"))
    if report.source_urls:
        print("Scripts origen (muestra):")
        for url in report.source_urls[:8]:
            print(f"  - {url[:220]}")
    if report.error:
        print(f"Detalle CDP: {report.error}")
    for sample in report.samples[:8]:
        listeners = sample.get("listeners", [])
        print(
            f"  Col {int(sample.get('column_index', -1)) + 1} | "
            f"estudiante {sample.get('student_code', '')} | listeners={len(listeners)}"
        )
        for item in listeners[:10]:
            source = item.get("source_url") or f"scriptId={item.get('script_id', '')}"
            print(
                f"     {item.get('type')} | ancestro={item.get('depth')} | "
                f"línea={item.get('line_number')} | {source[:180]}"
            )


def _print_function_details(prefix: str, details: dict[str, Any] | None) -> None:
    if not details:
        return
    description = str(details.get("description") or "").replace("\n", " ")
    if description:
        print(f"       {prefix}: {description[:260]}")
    props = details.get("properties") or []
    for prop in props[:12]:
        print(
            f"         prop {prop.get('name')} = {str(prop.get('value') or '')[:220]}"
        )
    for nested in (details.get("nested") or [])[:6]:
        nd = nested.get("details") or {}
        desc = str(nd.get("description") or "").replace("\n", " ")
        print(
            f"         {nested.get('property')} -> {desc[:260] if desc else '(objeto sin descripción)'}"
        )
        for prop in (nd.get("properties") or [])[:8]:
            print(
                f"           prop {prop.get('name')} = {str(prop.get('value') or '')[:200]}"
            )


def print_vue_report(report) -> None:
    print("\n--- VUE/QUASAR HANDLERS (CDP, SOLO LECTURA) ---")
    if report is None:
        print("No se generó reporte Vue/Quasar.")
        return
    print(f"CDP disponible: {'sí' if report.cdp_supported else 'no'}")
    print(f"Columnas inspeccionadas: {report.inspected_columns}")
    print(f"Handlers click encontrados: {report.handlers_found}")
    print(
        "Marcadores de framework: "
        + (", ".join(report.framework_markers) if report.framework_markers else "ninguno visible")
    )
    if report.error:
        print(f"Detalle: {report.error}")

    for sample in report.samples[:8]:
        print(
            f"  Col {int(sample.get('column_index', -1)) + 1} | "
            f"estudiante {sample.get('student_code', '')}"
        )
        for node in (sample.get("chain") or [])[:8]:
            markers = node.get("framework_properties") or []
            listeners = node.get("click_listeners") or []
            if markers:
                print(f"     ancestro={node.get('depth')} | propiedades framework: {', '.join(markers)}")
            for listener in listeners[:6]:
                print(
                    f"     click ancestro={listener.get('depth')} | "
                    f"script={listener.get('script_id')} | línea={listener.get('line_number')}"
                )
                _print_function_details("handler", listener.get("handler"))
                _print_function_details("original", listener.get("original_handler"))


legacy.APP_VERSION = APP_VERSION
legacy.probe_grade_cells = probe_grade_cells_with_framework
original_print = legacy.print_grade_cell_probe


def print_grade_cell_probe_with_framework(probe) -> None:
    original_print(probe)
    print_event_report(getattr(probe, "event_listener_report", None))
    print_vue_report(getattr(probe, "vue_event_report", None))


legacy.print_grade_cell_probe = print_grade_cell_probe_with_framework


if __name__ == "__main__":
    legacy.main()
