from __future__ import annotations

from typing import Any
from urllib.parse import urlsplit

from playwright.sync_api import Page

import verified_writer_bridge as writer
from sieweb import SieWebClient


# Conservar el fallback RC4 por compatibilidad. RC5 intenta primero capturar los
# encabezados REALES de una petición autenticada del navegador, evitando inventar
# X-Tab-Id o escoger el JWT equivocado de local/session storage.
_LEGACY_HYDRATE = writer._hydrate_client_from_browser


def _browser_cookies(page: Page) -> list[dict[str, Any]]:
    try:
        return [
            c for c in page.context.cookies()
            if "sieweb.com.pe" in str(c.get("domain") or "").lower()
        ]
    except Exception:
        return []


def _request_headers(request) -> dict[str, str]:
    try:
        raw = request.all_headers()
    except Exception:
        try:
            raw = request.headers
        except Exception:
            raw = {}
    return {str(k).lower(): str(v) for k, v in dict(raw or {}).items()}


def _capture_live_sieweb_headers(page: Page) -> dict[str, str]:
    """Captura, sin imprimir ni persistir, los headers auth que usa SIEweb.

    Se abre una pestaña temporal en el MISMO BrowserContext/perfil. Así el frontend
    usa la sesión ya autenticada del usuario y genera su X-Tab-Id real. Solo se
    conservan en memoria los encabezados necesarios para el writer HTTP.
    """
    captures: list[dict[str, str]] = []
    temp = None

    def on_request(req) -> None:
        url = str(getattr(req, "url", "") or "").lower()
        if "sieweb.com.pe" not in url or "/lms/api/" not in url:
            return
        headers = _request_headers(req)
        if not headers:
            return
        # Una petición con Sie-Token y X-Usucod es preferible. También guardamos
        # candidatas parciales por si una build de SIEweb cambia el nombre de uno.
        if headers.get("sie-token") or headers.get("authorization"):
            captures.append(headers)

    try:
        temp = page.context.new_page()
        temp.on("request", on_request)
        current_url = str(page.url or "")
        parsed = urlsplit(current_url)
        base = f"{parsed.scheme}://{parsed.netloc}" if parsed.scheme and parsed.netloc else "https://santaritadecasia.sieweb.com.pe"

        targets = []
        if current_url and "sieweb.com.pe" in current_url.lower():
            targets.append(current_url)
        targets.append(base + "/sistema/intranet")

        for target in targets:
            try:
                temp.goto(target, wait_until="domcontentloaded", timeout=25000)
                temp.wait_for_timeout(2500)
            except Exception:
                # Aun cuando goto termine por timeout, las peticiones iniciales ya
                # pudieron revelar los headers correctos.
                pass
            if captures:
                # Dar una ventana breve para obtener una petición más completa.
                try:
                    temp.wait_for_timeout(700)
                except Exception:
                    pass
                break
    finally:
        if temp is not None:
            try:
                temp.close()
            except Exception:
                pass

    if not captures:
        return {}

    def score(h: dict[str, str]) -> int:
        points = 0
        if h.get("sie-token"):
            points += 100
        if h.get("x-usucod"):
            points += 40
        if h.get("x-tab-id"):
            points += 35
        if h.get("x-tab-refresh"):
            points += 10
        if h.get("authorization"):
            points += 10
        return points

    return max(captures, key=score)


def _hydrate_from_exact_headers(page: Page, headers: dict[str, str]) -> tuple[SieWebClient, dict[str, bool]]:
    client = SieWebClient()
    client.session.cookies.clear()

    cookies = _browser_cookies(page)
    for cookie in cookies:
        name = str(cookie.get("name") or "")
        value = str(cookie.get("value") or "")
        if not name:
            continue
        kwargs: dict[str, Any] = {"path": str(cookie.get("path") or "/")}
        domain = str(cookie.get("domain") or "").strip()
        if domain:
            kwargs["domain"] = domain
        client.session.cookies.set(name, value, **kwargs)

    token = str(headers.get("sie-token") or "")
    user_code = str(headers.get("x-usucod") or "")
    tab_id = str(headers.get("x-tab-id") or "")
    tab_refresh = str(headers.get("x-tab-refresh") or "")

    if token:
        client._token = token
    if user_code:
        client._user_code = user_code.upper()
    if tab_id:
        client._tab_id = tab_id

    client._logged_in = True
    client._set_authenticated_headers()

    # Conservar exactamente los encabezados de sesión observados. No se guardan
    # en logs/evidencia y nunca se devuelven al llamador.
    if token:
        client.session.headers["Sie-Token"] = token
    if user_code:
        client.session.headers["X-Usucod"] = user_code
    if tab_id:
        client.session.headers["X-Tab-Id"] = tab_id
    if tab_refresh:
        client.session.headers["X-Tab-Refresh"] = tab_refresh
    if headers.get("authorization"):
        client.session.headers["Authorization"] = headers["authorization"]

    return client, {
        "browser_cookie_present": bool(cookies),
        "browser_token_present": bool(token),
        "browser_user_code_present": bool(user_code),
        "browser_tab_id_present": bool(tab_id),
        "browser_live_header_capture": True,
    }


def _read_only_session_ok(client: SieWebClient) -> bool:
    """Prueba la sesión con una lectura inocua; nunca modifica SIEweb."""
    try:
        response = client._request_once(
            "GET",
            "/lms/api/HyoUsuario/obtListaUsuariosIntranet",
            params={"isMensajeria": "true"},
        )
        return bool(response.ok) and not client._looks_logged_out(response)
    except Exception:
        return False


def hydrate_client_from_browser_rc5(page: Page) -> tuple[SieWebClient, dict[str, bool]]:
    headers = _capture_live_sieweb_headers(page)
    if headers:
        client, status = _hydrate_from_exact_headers(page, headers)
        if _read_only_session_ok(client):
            status["browser_session_read_verified"] = True
            return client, status

    # Fallback conservador al método RC4. A diferencia de RC4, RC5 NO lo acepta
    # ciegamente: exige que una lectura real confirme la sesión antes de continuar.
    try:
        client, status = _LEGACY_HYDRATE(page)
        if _read_only_session_ok(client):
            status = dict(status)
            status["browser_live_header_capture"] = False
            status["browser_session_read_verified"] = True
            return client, status
    except Exception:
        pass

    raise writer.VerifiedWriterBridgeError(
        "RC5 no pudo trasladar de forma verificable la sesión autenticada del navegador al writer. "
        "No se escribió nada. La pestaña de SIEweb permanece intacta."
    )


def install() -> None:
    writer._hydrate_client_from_browser = hydrate_client_from_browser_rc5
