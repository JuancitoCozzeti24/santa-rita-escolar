from __future__ import annotations

import main as legacy
import launcher_v100rc1 as rc1
from grade_cell_mapper_rc2 import map_grade_cells as dynamic_map_grade_cells


APP_VERSION = "1.0.0-rc2"


def map_grade_cells_normalized_rc2(page):
    changed = rc1.normalize_grade_view(page)
    if changed:
        page.wait_for_timeout(180)
    mapped = dynamic_map_grade_cells(page)
    setattr(mapped, "normalized_scroll_surfaces", changed)
    return mapped


# RC2 conserva el flujo de preflight de RC1, pero sustituye el mapper por uno
# independiente del ancho del viewport. En una ventana estrecha la primera
# competencia puede quedar en x<450; RC1 podía omitirla por ese corte histórico.
legacy.APP_VERSION = APP_VERSION
legacy.map_grade_cells = map_grade_cells_normalized_rc2
legacy.probe_grade_cells = rc1.probe_grade_cells_preview
legacy.print_grade_cell_probe = rc1.print_grade_cell_probe_rc1


if __name__ == "__main__":
    legacy.main()
