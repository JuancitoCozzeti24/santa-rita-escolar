from __future__ import annotations

import builtins

import main as legacy
import launcher_v100rc1 as rc1
import launcher_v100rc3 as rc3
import launcher_v100rc15 as rc15
import performance_plan_rc18 as plan18
import browser_startup_rc19 as startup19
import criteria_raw_rc21 as raw21


APP_VERSION = "1.0.0-rc21"
_original_print = builtins.print


def _print_rc21(*args, **kwargs):
    patched = []
    for arg in args:
        if isinstance(arg, str):
            text = arg
            for old in ("RC20", "RC19", "RC18", "RC17", "RC16", "RC15"):
                text = text.replace(old, "RC21").replace(old.lower(), "rc21")
            patched.append(text)
        else:
            patched.append(arg)
    _original_print(*patched, **kwargs)


# RC21 conserva el arranque automático de Classroom + SIEweb y abandona la
# suposición de que resCriterios debe exponer NIVEL=2 o children. Resuelve capacidades
# usando toda la respuesta cruda de dataInicialPesosCriterios + summary.criteria,
# que es la misma fuente históricamente usada por el complemento en produccion.
startup19.install()
raw21.install()

rc15.print = _print_rc21
rc15.preview_plan = plan18.preview_plan
rc15.create_missing_performances = plan18.create_missing_performances
rc15.APP_VERSION = APP_VERSION

legacy.APP_VERSION = APP_VERSION
legacy.map_grade_cells = rc3.map_grade_cells_normalized_rc3
legacy.probe_grade_cells = rc1.probe_grade_cells_preview
legacy.print_grade_cell_probe = rc15.print_grade_cell_probe_rc15


if __name__ == "__main__":
    legacy.main()
