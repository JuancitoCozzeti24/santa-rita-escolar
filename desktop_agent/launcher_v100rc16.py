from __future__ import annotations

import builtins

import main as legacy
import launcher_v100rc1 as rc1
import launcher_v100rc3 as rc3
import launcher_v100rc15 as rc15
import performance_plan_rc16 as plan16


APP_VERSION = "1.0.0-rc16"
_original_print = builtins.print


def _print_rc16(*args, **kwargs):
    patched = []
    for arg in args:
        if isinstance(arg, str):
            patched.append(arg.replace("RC15", "RC16").replace("rc15", "rc16"))
        else:
            patched.append(arg)
    _original_print(*patched, **kwargs)


# RC16 conserva todo RC15 y sustituye únicamente la resolución del plan docente
# por la captura dinámica de la libreta visible (la misma estrategia probada en RC11).
rc15.print = _print_rc16
rc15.preview_plan = plan16.preview_plan
rc15.APP_VERSION = APP_VERSION

legacy.APP_VERSION = APP_VERSION
legacy.map_grade_cells = rc3.map_grade_cells_normalized_rc3
legacy.probe_grade_cells = rc1.probe_grade_cells_preview
legacy.print_grade_cell_probe = rc15.print_grade_cell_probe_rc15


if __name__ == "__main__":
    legacy.main()
