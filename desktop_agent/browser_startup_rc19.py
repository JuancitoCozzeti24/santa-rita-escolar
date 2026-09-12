from __future__ import annotations

from typing import Any

import browser_controller as browser_mod


CLASSROOM_URL = "https://classroom.google.com/u/0/h"
SIEWEB_URL = "https://santaritadecasia.sieweb.com.pe/sistema/login"

_ORIGINAL_START = browser_mod.ReadOnlyBrowserController.start
_INSTALLED = False


def _safe_goto(page: Any, url: str) -> None:
    """Inicia la navegación sin esperar a que la SPA termine de cargar por completo."""
    try:
        page.goto(url, wait_until="commit", timeout=15000)
    except Exception:
        # Si Classroom/SIEweb están lentos, dejamos la pestaña viva para que termine
        # de cargar normalmente en el navegador. El arranque del agente no debe quedar
        # bloqueado esperando recursos secundarios.
        pass


def _is_classroom(page: Any) -> bool:
    try:
        return "classroom.google.com" in str(page.url).lower()
    except Exception:
        return False


def _is_sieweb(page: Any) -> bool:
    try:
        return "sieweb.com.pe" in str(page.url).lower()
    except Exception:
        return False


def _pick_last(pages: list[Any], predicate) -> Any | None:
    matches = [page for page in pages if not page.is_closed() and predicate(page)]
    return matches[-1] if matches else None


def start_with_classroom_and_sieweb(self):
    """Abre el perfil dedicado dejando SOLO una pestaña Classroom y una SIEweb.

    Conserva una pestaña ya existente de cada aplicación para no destruir el contexto
    en el que el usuario estaba trabajando. Si falta alguna, la crea automáticamente.
    Las páginas ajenas al flujo escolar se cierran para que el agente no tenga que
    pedir cuál pestaña debe controlar.
    """
    context = _ORIGINAL_START(self)

    pages = [page for page in context.pages if not page.is_closed()]
    classroom_page = _pick_last(pages, _is_classroom)
    sieweb_page = _pick_last(pages, _is_sieweb)

    if classroom_page is None:
        classroom_page = context.new_page()
        _safe_goto(classroom_page, CLASSROOM_URL)
    else:
        # La versión antigua podía quedar en la portada informativa. Una pestaña real
        # de classroom.google.com se conserva tal como está para no perder navegación.
        try:
            if classroom_page.url.rstrip("/") == "https://classroom.google.com":
                _safe_goto(classroom_page, CLASSROOM_URL)
        except Exception:
            pass

    if sieweb_page is None:
        sieweb_page = context.new_page()
        _safe_goto(sieweb_page, SIEWEB_URL)

    # Queremos un navegador de trabajo predecible: una pestaña para cada sistema.
    keep_ids = {id(classroom_page), id(sieweb_page)}
    for page in list(context.pages):
        if page.is_closed() or id(page) in keep_ids:
            continue
        try:
            page.close()
        except Exception:
            pass

    # Deja SIEweb visible porque normalmente el siguiente paso del agente es trabajar
    # en Registro de notas. Classroom queda abierto en la pestaña contigua.
    try:
        sieweb_page.bring_to_front()
    except Exception:
        pass

    return context


def install() -> None:
    global _INSTALLED
    if _INSTALLED:
        return
    browser_mod.ReadOnlyBrowserController.start = start_with_classroom_and_sieweb
    _INSTALLED = True
