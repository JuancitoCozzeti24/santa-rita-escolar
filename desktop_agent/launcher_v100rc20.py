from __future__ import annotations

import builtins

import main as legacy
import launcher_v100rc1 as rc1
import launcher_v100rc3 as rc3
import launcher_v100rc15 as rc15
import performance_plan_rc18 as plan18
import browser_startup_rc19 as startup19
import criteria_hierarchy_rc20 as hierarchy20


APP_VERSION = "1.0.0-rc20"
_original_print = builtins.print


def _print_rc20(*args, **kwargs):
    patched = []
    for arg in args:
        if isinstance(arg, str):
            text = (
                arg.replace("RC19", "RC20")
                .replace("rc19", "rc20")
                .replace("RC18", "RC20")
                .replace("rc18", "rc20")
                .replace("RC17", "RC20")
                .replace("rc17", "rc20")
                .replace("RC16", "RC20")
                .replace("rc16", "rc20")
                .replace("RC15", "RC20")
                .replace("rc15", "rc20")
            )
            patched.append(text)
        else:
            patched.append(arg)
    _original_print(*patched, **kwargs)


# RC20 conserva el arranque automático Classroom + SIEweb de RC19 y el motor de
# creación/escritura de RC18, pero interpreta resCriterios por jerarquía children.
# SIEweb observado etiqueta varios nodos con NIVEL=1; por eso RC20 deja de depender
# de NIVEL=2/3 para distinguir Capacidad y Desempeño.
startup19.install()
hierarchy20.install()

rc15.print = _print_rc20
rc15.preview_plan = plan18.preview_plan
rc15.create_missing_performances = plan18.create_missing_performances
rc15.APP_VERSION = APP_VERSION

legacy.APP_VERSION = APP_VERSION
legacy.map_grade_cells = rc3.map_grade_cells_normalized_rc3
legacy.probe_grade_cells = rc1.probe_grade_cells_preview
legacy.print_grade_cell_probe = rc15.print_grade_cell_probe_rc15


if __name__ == "__main__":
    legacy.main()
