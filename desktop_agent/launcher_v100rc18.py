from __future__ import annotations

import builtins

import main as legacy
import launcher_v100rc1 as rc1
import launcher_v100rc3 as rc3
import launcher_v100rc15 as rc15
import performance_plan_rc18 as plan18


APP_VERSION = "1.0.0-rc18"
_original_print = builtins.print


def _print_rc18(*args, **kwargs):
    patched = []
    for arg in args:
        if isinstance(arg, str):
            text = (
                arg.replace("RC17", "RC18")
                .replace("rc17", "rc18")
                .replace("RC16", "RC18")
                .replace("rc16", "rc18")
                .replace("RC15", "RC18")
                .replace("rc15", "rc18")
            )
            patched.append(text)
        else:
            patched.append(arg)
    _original_print(*patched, **kwargs)


# RC18 mantiene el contexto dinámico y la escritura masiva de RC15/RC16,
# pero resuelve Competencia -> Capacidad -> Desempeño desde el árbol REAL
# dataInicialPesosCriterios/json.resCriterios que usa el modal de SIEweb.
# Esto corrige el falso "sin capacidades nivelEva=2" causado por buscarlas
# en el resumen de la libreta, donde SIEweb puede omitirlas.
rc15.print = _print_rc18
rc15.preview_plan = plan18.preview_plan
rc15.create_missing_performances = plan18.create_missing_performances
rc15.APP_VERSION = APP_VERSION

legacy.APP_VERSION = APP_VERSION
legacy.map_grade_cells = rc3.map_grade_cells_normalized_rc3
legacy.probe_grade_cells = rc1.probe_grade_cells_preview
legacy.print_grade_cell_probe = rc15.print_grade_cell_probe_rc15


if __name__ == "__main__":
    legacy.main()
