from __future__ import annotations

import builtins

import main as legacy
import launcher_v100rc1 as rc1
import launcher_v100rc3 as rc3
import launcher_v100rc15 as rc15
import performance_plan as base_plan
import performance_plan_rc16 as plan16
import capacity_resolver_rc17 as cap17


APP_VERSION = "1.0.0-rc17"
_original_print = builtins.print


def _print_rc17(*args, **kwargs):
    patched = []
    for arg in args:
        if isinstance(arg, str):
            text = (
                arg.replace("RC16", "RC17")
                .replace("rc16", "rc17")
                .replace("RC15", "RC17")
                .replace("rc15", "rc17")
            )
            patched.append(text)
        else:
            patched.append(arg)
    _original_print(*patched, **kwargs)


# RC17 conserva el contexto dinámico de RC16 y mejora exclusivamente la resolución
# de capacidades. El plan ya no exige que el texto de capacidad coincida letra por
# letra con SIEweb: primero intenta exacto y luego una coincidencia semántica muy
# conservadora. Si no hay una única coincidencia segura, muestra las capacidades
# reales disponibles y bloquea toda escritura.
base_plan._find_capacity = cap17.find_capacity_robust
rc15.print = _print_rc17
rc15.preview_plan = plan16.preview_plan
rc15.APP_VERSION = APP_VERSION

legacy.APP_VERSION = APP_VERSION
legacy.map_grade_cells = rc3.map_grade_cells_normalized_rc3
legacy.probe_grade_cells = rc1.probe_grade_cells_preview
legacy.print_grade_cell_probe = rc15.print_grade_cell_probe_rc15


if __name__ == "__main__":
    legacy.main()
