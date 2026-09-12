from __future__ import annotations

import builtins
import time

import main as legacy
import launcher_v100rc3 as rc3
import launcher_v100rc9 as rc9
import launcher_v100rc12 as rc12
import launcher_v100rc13 as rc13


APP_VERSION = "1.0.0-rc14"
MAX_BATCH = 28
_original_print = builtins.print


def _print_rc14(*args, **kwargs):
    patched = []
    for arg in args:
        if isinstance(arg, str):
            patched.append(arg.replace("RC13", "RC14").replace("RC12", "RC14"))
        else:
            patched.append(arg)
    _original_print(*patched, **kwargs)


# RC14 mantiene el motor de persistencia agrupada de RC13 y corrige únicamente
# la falsa alarma visual observada cuando la API ya había guardado las notas,
# pero la SPA tardaba un poco más en pintar la libreta actualizada.
rc13.print = _print_rc14
rc9.print = _print_rc14
rc13.APP_VERSION = APP_VERSION
rc9.APP_VERSION = APP_VERSION
rc9.MAX_BATCH = MAX_BATCH


def _verify_dom_rows_polling(page, rows, timeout_ms: int = 8000):
    """Espera a que la SPA refleje el lote ya confirmado por API.

    No vuelve a guardar nada y no recarga la página. Solo relee el DOM varias
    veces mientras SIEweb termina de reconstruir la grilla después de la única
    actualización final de RC13.
    """
    deadline = time.monotonic() + max(1.0, timeout_ms / 1000.0)
    last_checks = []

    while time.monotonic() < deadline:
        checks = []
        all_ok = True

        for row in rows:
            observed = ""
            error = ""
            try:
                observed = rc12._read_live_value(
                    page, row["code"], int(row["column"])
                )
                ok = observed == row["grade"]
            except Exception as exc:
                ok = False
                error = str(exc)

            checks.append({
                "student_code": row["code"],
                "student_name": row["name"],
                "column": int(row["column"]),
                "expected": row["grade"],
                "observed": observed,
                "ok": ok,
                "error": error,
            })
            all_ok = all_ok and ok

        last_checks = checks
        if all_ok:
            return checks, True

        # SIEweb/Quasar puede tardar en repintar la tabla aun cuando el servidor
        # ya confirmó el guardado. Esperamos sin reseleccionar ni recargar.
        page.wait_for_timeout(250)

    return last_checks, False


rc13._verify_dom_rows = _verify_dom_rows_polling

legacy.APP_VERSION = APP_VERSION
legacy.map_grade_cells = rc3.map_grade_cells_normalized_rc3
legacy.print_grade_cell_probe = rc9.print_grade_cell_probe_rc9


if __name__ == "__main__":
    legacy.main()
