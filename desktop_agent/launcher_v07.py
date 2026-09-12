from __future__ import annotations

from typing import Any

import main as legacy
from event_listener_probe import inspect_grade_cell_event_listeners
from grade_cell_probe import probe_grade_cells as base_probe_grade_cells


APP_VERSION = "0.7.0"


class EnrichedProbe:
    def __init__(self, base: Any, event_report: Any) -> None:
        self._base = base
        self.event_listener_report = event_report
        self.column_count = base.column_count
        self.probed_cell_count = base.probed_cell_count
        self.columns = base.columns
        self.cell_signatures = base.cell_signatures

    def as_dict(self) -> dict[str, Any]:
        payload = self._base.as_dict()
        payload["event_listener_report"] = self.event_listener_report.as_dict()
        return payload


def probe_grade_cells_with_events(page, grade_cell_map):
    base = base_probe_grade_cells(page, grade_cell_map)
    report = inspect_grade_cell_event_listeners(page, base)
    return EnrichedProbe(base, report)


def print_grade_cell_probe_with_events(probe) -> None:
    original_print(probe)
    report = getattr(probe, "event_listener_report", None)
    print("\n--- EVENT LISTENERS DE CELDAS (CDP, SOLO LECTURA) ---")
    if report is None:
        print("No se generó reporte de listeners.")
        return

    print(f"CDP disponible: {'sí' if report.cdp_supported else 'no'}")
    print(f"Listeners relevantes detectados: {report.listener_count}")
    print(
        "Tipos detectados: "
        + (", ".join(report.listener_types) if report.listener_types else "ninguno")
    )
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


legacy.APP_VERSION = APP_VERSION
legacy.probe_grade_cells = probe_grade_cells_with_events
original_print = legacy.print_grade_cell_probe
legacy.print_grade_cell_probe = print_grade_cell_probe_with_events


if __name__ == "__main__":
    legacy.main()
