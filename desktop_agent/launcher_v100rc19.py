from __future__ import annotations

import builtins

import main as legacy
import launcher_v100rc1 as rc1
import launcher_v100rc3 as rc3
import launcher_v100rc15 as rc15
import performance_plan_rc18 as plan18
import browser_startup_rc19 as startup19


APP_VERSION = "1.0.0-rc19"
_original_print = builtins.print


def _print_rc19(*args, **kwargs):
    patched = []
    for arg in args:
        if isinstance(arg, str):
            text = (
                arg.replace("RC18", "RC19")
                .replace("rc18", "rc19")
                .replace("RC17", "RC19")
                .replace("rc17", "rc19")
                .replace("RC16", "RC19")
                .replace("rc16", "rc19")
                .replace("RC15", "RC19")
                .replace("rc15", "rc19")
            )
            patched.append(text)
        else:
            patched.append(arg)
    _original_print(*patched, **kwargs)


# RC19 conserva RC18 para desempeño/criterios y cambia el arranque del navegador:
# deja únicamente Classroom + SIEweb abiertos desde el inicio, reutilizando las
# pestañas existentes cuando ya pertenecen a esas aplicaciones.
startup19.install()
rc15.print = _print_rc19
rc15.preview_plan = plan18.preview_plan
rc15.create_missing_performances = plan18.create_missing_performances
rc15.APP_VERSION = APP_VERSION

legacy.APP_VERSION = APP_VERSION
legacy.map_grade_cells = rc3.map_grade_cells_normalized_rc3
legacy.probe_grade_cells = rc1.probe_grade_cells_preview
legacy.print_grade_cell_probe = rc15.print_grade_cell_probe_rc15


if __name__ == "__main__":
    legacy.main()
