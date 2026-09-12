from __future__ import annotations

import builtins

import main as legacy
import launcher_v100rc1 as rc1
import launcher_v100rc3 as rc3
import launcher_v100rc7 as rc7
import launcher_v100rc9 as rc9
from verified_writer_bridge import VerifiedWriterBridgeError


APP_VERSION = "1.0.0-rc10"
_original_print = builtins.print


def _print_rc10(*args, **kwargs):
    patched = []
    for arg in args:
        if isinstance(arg, str):
            text = arg.replace("RC9", "RC10")
            text = text.replace(
                "Releer DOM actual DESPUÉS de todas las celdas previas ya verificadas.",
                "Sincronizando DOM con la libreta antes de cada escritura.",
            )
            patched.append(text)
        else:
            patched.append(arg)
    _original_print(*patched, **kwargs)


# Todos los print del módulo RC9 pasan a mostrar RC10.
rc9.print = _print_rc10
rc9.APP_VERSION = APP_VERSION


def _read_target_cell(page, *, code: str, column: int) -> tuple[str, str, bool]:
    mapped = rc3.map_grade_cells_normalized_rc3(page)
    matches = [
        s for s in (mapped.students or [])
        if str(s.get("code") or "").strip() == str(code).strip()
    ]
    if len(matches) != 1:
        raise VerifiedWriterBridgeError(
            f"El alumno {code} aparece {len(matches)} veces en el DOM actual."
        )
    cell = rc1._target_cell(matches[0], int(column) - 1)
    if not cell:
        raise VerifiedWriterBridgeError("No se localizó la celda objetivo en el DOM actual.")

    text = str(cell.get("text") or "").strip().upper()
    state = str(cell.get("value_state") or "unreadable")
    confident = bool(cell.get("value_confident"))
    if not confident or state not in {"blank", "grade"}:
        raise VerifiedWriterBridgeError(
            f"La lectura DOM actual no es confiable (estado={state}, confiable={confident})."
        )
    return text, state, confident


def _stable_remap_current_cell(page, *, code: str, column: int) -> tuple[str, str, bool]:
    """Revalida una celda con refresco suave y dos lecturas concordantes.

    RC9 podía obtener una lectura DOM transitoria justo después del preflight. RC10
    vuelve a pedir la MISMA libreta re-seleccionando el período (sin recargar toda
    la SPA y sin escribir), y luego exige que dos lecturas consecutivas coincidan.
    Si no puede estabilizarse, bloquea el lote antes de enviar cualquier PUT.
    """
    before = _read_target_cell(page, code=code, column=column)

    snapshot = rc7._selector_snapshot(page)
    period = rc7._find_snapshot(snapshot, "periodo") or rc7._find_snapshot(snapshot, "período")
    refreshed = False
    if period:
        refreshed = bool(rc7._select_same_value(page, period))
        if refreshed:
            page.wait_for_timeout(1000)

    second = _read_target_cell(page, code=code, column=column)
    page.wait_for_timeout(260)
    third = _read_target_cell(page, code=code, column=column)

    if second != third:
        raise VerifiedWriterBridgeError(
            "El DOM de la celda no se estabilizó en dos lecturas consecutivas. "
            f"Lectura 1={second[0] or '(vacío)'}; lectura 2={third[0] or '(vacío)'}. "
            "No se escribió nada."
        )

    # Si el refresco suave no pudo ejecutarse, solo aceptamos un DOM que ya era
    # estable antes y después. Cualquier cambio espontáneo bloquea la escritura.
    if not refreshed and before != second:
        raise VerifiedWriterBridgeError(
            "El DOM cambió entre lecturas y no fue posible refrescar la misma libreta de forma segura. "
            f"Antes={before[0] or '(vacío)'}; después={second[0] or '(vacío)'}. No se escribió nada."
        )

    if before != second:
        _print_rc10(
            "  Nota de seguridad RC10: el refresco suave sincronizó la celda visible "
            f"de {before[0] or '(vacío)'} a {second[0] or '(vacío)'} antes de escribir."
        )

    return second


# Sustituimos únicamente la relectura previa a cada escritura. El preflight,
# writer verificado, parada ante fallo y verificación API+navegador siguen siendo
# exactamente los de RC9/RC7.
rc9._remap_current_cell = _stable_remap_current_cell

legacy.APP_VERSION = APP_VERSION
legacy.map_grade_cells = rc3.map_grade_cells_normalized_rc3
legacy.probe_grade_cells = rc1.probe_grade_cells_preview
legacy.print_grade_cell_probe = rc9.print_grade_cell_probe_rc9


if __name__ == "__main__":
    legacy.main()
