from __future__ import annotations

import builtins
import re

import main as legacy
import launcher_v100rc1 as rc1
import launcher_v100rc3 as rc3
import launcher_v100rc6 as rc6


APP_VERSION = "1.0.0-rc7"
_original_print = builtins.print


def _print_rc7(*args, **kwargs):
    patched = []
    for arg in args:
        if isinstance(arg, str):
            text = arg.replace("RC6", "RC7")
            text = text.replace(
                "Relectura API terminada. Recargando SIEweb para verificar la interfaz...",
                "Relectura API terminada. Actualizando la misma libreta sin perder el contexto...",
            )
            text = text.replace(
                "La página se recargó y el DOM visible confirmó exactamente el mismo valor.",
                "La libreta se actualizó y el DOM visible confirmó exactamente el mismo valor.",
            )
            patched.append(text)
        else:
            patched.append(arg)
    _original_print(*patched, **kwargs)


rc6.print = _print_rc7


def _norm(value: str) -> str:
    text = " ".join(str(value or "").split()).strip().lower()
    text = text.replace("á", "a").replace("é", "e").replace("í", "i").replace("ó", "o").replace("ú", "u")
    return text


def _selector_snapshot(page) -> list[dict]:
    try:
        return page.evaluate(
            r"""
            () => {
              const clean = (v, n=240) => String(v ?? '').replace(/\s+/g,' ').trim().slice(0,n);
              const visible = (el) => {
                if (!el || !(el instanceof Element)) return false;
                const s = getComputedStyle(el); const r = el.getBoundingClientRect();
                return s.display !== 'none' && s.visibility !== 'hidden' && r.width > 0 && r.height > 0;
              };
              return Array.from(document.querySelectorAll('.q-field')).map((el, domIndex) => {
                if (!visible(el)) return null;
                const labelEl = el.querySelector('.q-field__label');
                const label = clean(labelEl?.innerText || labelEl?.textContent || '');
                const native = el.querySelector('.q-field__native, .q-field__input, input');
                let value = clean((native && ('value' in native) ? native.value : '') || native?.innerText || native?.textContent || el.innerText || el.textContent || '');
                if (label) value = value.replace(label, ' ');
                value = value.replace(/arrow_drop_down|keyboard_arrow_down|expand_more/gi, ' ').replace(/\s+/g,' ').trim();
                return {dom_index: domIndex, label, value};
              }).filter(Boolean).filter(x => /sal[oó]n|curso|periodo|per[ií]odo/i.test(x.label + ' ' + x.value)).slice(0, 6);
            }
            """
        ) or []
    except Exception:
        return []


def _current_dom_value(page, *, student_code: str, column: int, expected: str) -> dict:
    result = {
        "ok": False,
        "expected": expected,
        "observed": "",
        "value_state": "unreadable",
        "value_confident": False,
        "student_found": False,
        "cell_found": False,
        "roster_count": 0,
        "column_count": 0,
        "error": "",
    }
    try:
        mapped = rc3.map_grade_cells_normalized_rc3(page)
        result["roster_count"] = int(mapped.student_count or 0)
        result["column_count"] = int(mapped.column_count or 0)
        matches = [
            s for s in (mapped.students or [])
            if str(s.get("code") or "").strip() == str(student_code).strip()
        ]
        if len(matches) != 1:
            result["error"] = f"El alumno objetivo aparece {len(matches)} veces en la libreta visible."
            return result
        result["student_found"] = True
        cell = rc1._target_cell(matches[0], int(column) - 1)
        if not cell:
            result["error"] = "No se pudo localizar la celda objetivo en la libreta visible."
            return result
        result["cell_found"] = True
        observed = str(cell.get("text") or "").strip().upper()
        state = str(cell.get("value_state") or "unreadable")
        confident = bool(cell.get("value_confident"))
        result.update(observed=observed, value_state=state, value_confident=confident)
        result["ok"] = bool(confident and state == "grade" and observed == expected)
        if not result["ok"]:
            result["error"] = (
                f"DOM no confirmó el valor esperado (esperado={expected}, "
                f"observado={observed or '(vacío)'}, estado={state}, confiable={confident})."
            )
        return result
    except Exception as exc:
        result["error"] = f"No se pudo leer la libreta visible: {exc}"
        return result


def _find_snapshot(snapshot: list[dict], key: str) -> dict | None:
    key_n = _norm(key)
    for item in snapshot:
        if key_n in _norm(item.get("label") or ""):
            return item
    for item in snapshot:
        if key_n in _norm(item.get("value") or ""):
            return item
    return None


def _select_same_value(page, item: dict) -> bool:
    target = str(item.get("value") or "").strip()
    if not target:
        return False
    try:
        field = page.locator('.q-field').nth(int(item.get('dom_index') or 0))
        field.click(timeout=5000)
        page.wait_for_timeout(300)
        options = page.locator('.q-menu .q-item:visible, .q-virtual-scroll__content .q-item:visible, [role="option"]:visible')
        count = options.count()
        target_n = _norm(target)
        best = -1
        for i in range(min(count, 120)):
            try:
                text = options.nth(i).inner_text(timeout=1500)
            except Exception:
                continue
            text_n = _norm(text)
            if text_n == target_n:
                best = i
                break
            if best < 0 and target_n and (target_n in text_n or text_n in target_n):
                best = i
        if best < 0:
            try:
                page.keyboard.press('Escape')
            except Exception:
                pass
            return False
        options.nth(best).click(timeout=5000)
        page.wait_for_timeout(900)
        return True
    except Exception:
        try:
            page.keyboard.press('Escape')
        except Exception:
            pass
        return False


def _restore_context(page, snapshot: list[dict]) -> bool:
    restored_any = False
    for key in ("salon", "curso", "periodo"):
        item = _find_snapshot(snapshot, key)
        if not item:
            if key == "salon":
                item = _find_snapshot(snapshot, "salón")
            if key == "periodo":
                item = _find_snapshot(snapshot, "período")
        if not item:
            continue
        if _select_same_value(page, item):
            restored_any = True
    if restored_any:
        page.wait_for_timeout(1600)
    return restored_any


def _verify_dom_after_write_rc7(page, *, student_code: str, column: int, expected: str) -> dict:
    """Verifica el DOM sin dejar Registro de Notas en 'No hay Información'.

    RC6 hacía page.reload() y SIEweb pierde Salón/Curso/Periodo al recargar la SPA.
    RC7 primero intenta refrescar la misma libreta re-seleccionando el período. Si
    no basta, recarga y restaura explícitamente los tres selectores antes de leer.
    Ninguno de estos pasos escribe notas.
    """
    snapshot = _selector_snapshot(page)

    # Si el frontend ya refleja el cambio, no navegamos ni recargamos nada.
    current = _current_dom_value(page, student_code=student_code, column=column, expected=expected)
    if current.get("ok"):
        current["refresh_mode"] = "already_visible"
        return current

    # Intento 1: re-seleccionar el mismo período para que el componente Vue vuelva
    # a pedir la libreta manteniendo salón y curso.
    period = _find_snapshot(snapshot, "periodo") or _find_snapshot(snapshot, "período")
    if period and _select_same_value(page, period):
        page.wait_for_timeout(1200)
        soft = _current_dom_value(page, student_code=student_code, column=column, expected=expected)
        soft["refresh_mode"] = "period_reselect"
        if soft.get("ok"):
            return soft

    # Intento 2: solo como fallback, recarga completa y RESTAURA el contexto que
    # RC6 perdía. Si la restauración falla, se detiene sin tocar datos.
    try:
        page.reload(wait_until="domcontentloaded", timeout=30000)
        page.wait_for_timeout(1200)
    except Exception as exc:
        current["error"] = f"No se pudo recargar SIEweb para la verificación visual: {exc}"
        current["refresh_mode"] = "reload_failed"
        return current

    restored = _restore_context(page, snapshot)
    page.wait_for_timeout(1200)
    final = _current_dom_value(page, student_code=student_code, column=column, expected=expected)
    final["refresh_mode"] = "reload_and_restore" if restored else "reload_restore_failed"
    final["selector_snapshot"] = [
        {"label": str(x.get("label") or ""), "value": str(x.get("value") or "")}
        for x in snapshot
    ]
    if not restored and not final.get("ok"):
        final["error"] = (
            "SIEweb perdió el contexto tras recargar y RC7 no pudo restaurar Salón/Curso/Período automáticamente. "
            "La API permanece verificada; no se hará ninguna escritura adicional."
        )
    return final


rc6._verify_dom_after_write = _verify_dom_after_write_rc7

legacy.APP_VERSION = APP_VERSION
legacy.map_grade_cells = rc3.map_grade_cells_normalized_rc3
legacy.probe_grade_cells = rc1.probe_grade_cells_preview
legacy.print_grade_cell_probe = rc6.print_grade_cell_probe_rc6


if __name__ == "__main__":
    legacy.main()
