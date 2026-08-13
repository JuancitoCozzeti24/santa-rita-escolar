from __future__ import annotations

import uuid
from typing import Any

import requests

from config import settings


class SieWebError(RuntimeError):
    pass


class SieWebClient:
    """Cliente privado de SieWeb para la cuenta autorizada del usuario.

    El login y los endpoints fueron observados en la interfaz web de la cuenta
    autorizada del usuario. SieWeb no publica estos endpoints como API pública,
    por lo que deben tratarse como una integración privada susceptible a cambios.
    """

    def __init__(self) -> None:
        self.session = requests.Session()
        self.session.headers.update(
            {
                "Accept": "application/json, text/plain, */*",
                "User-Agent": "Mozilla/5.0 Santa-Rita-Escolar-MCP/0.2",
                "X-Requested-With": "XMLHttpRequest",
                "Cache-Control": "no-cache",
                "Pragma": "no-cache",
                "Referer": f"{settings.sieweb_base_url}/sistema/login",
            }
        )
        self._token = ""
        self._token_viewer = ""
        self._refresh_token = ""
        self._user_code = settings.sieweb_user.upper() if settings.sieweb_user else ""
        self._tab_id = str(uuid.uuid4())
        self._logged_in = False

        # Compatibilidad temporal con la primera versión.
        if settings.sieweb_cookie:
            self.session.headers["Cookie"] = settings.sieweb_cookie
        if settings.sieweb_authorization:
            self.session.headers["Authorization"] = settings.sieweb_authorization

    @property
    def has_login_credentials(self) -> bool:
        return bool(settings.sieweb_user and settings.sieweb_password)

    def _base(self, path: str) -> str:
        return f"{settings.sieweb_base_url}/{path.lstrip('/')}"

    def _set_authenticated_headers(self) -> None:
        if self._token:
            self.session.headers["Sie-Token"] = self._token
        if self._user_code:
            self.session.headers["X-Usucod"] = self._user_code
        self.session.headers["X-Tab-Id"] = self._tab_id
        self.session.headers["X-Tab-Refresh"] = "1"

    def _refresh_token_with_cookie(self) -> bool:
        """Pide a SieWeb un token actualizado usando la sesión/cookies actuales."""
        if not self._token or not self.session.cookies:
            return False
        self._set_authenticated_headers()
        response = self.session.get(
            self._base("/lms/api/login/getTokenConCookie"),
            timeout=settings.sieweb_timeout_seconds,
        )
        if not response.ok:
            return False
        token = response.text.strip().strip('"')
        if not token.startswith("eyJ"):
            return False
        self._token = token
        self._set_authenticated_headers()
        return True

    def login(self) -> dict[str, Any]:
        """Inicia sesión y devuelve un resumen seguro, sin tokens ni contraseña."""
        if not self.has_login_credentials:
            raise SieWebError(
                "Faltan SIEWEB_USER y SIEWEB_PASSWORD en el archivo .env. "
                "Ejecuta CONFIGURAR_SIEWEB.bat."
            )

        # Empezar limpio evita conservar cookies caducadas.
        self.session.cookies.clear()
        response = self.session.post(
            self._base("/lms/api/login/Ingresar"),
            json={
                "user": settings.sieweb_user,
                "pass": settings.sieweb_password,
                "isMobil": False,
            },
            timeout=settings.sieweb_timeout_seconds,
        )
        if not response.ok:
            raise SieWebError(
                f"El login de SieWeb falló (HTTP {response.status_code}): "
                f"{response.text[:500]}"
            )
        try:
            outer = response.json()
        except ValueError as exc:
            raise SieWebError("SieWeb no devolvió JSON al iniciar sesión.") from exc

        data = outer.get("json") or {}
        token = data.get("token") or ""
        if not token:
            raise SieWebError(
                "SieWeb respondió al login, pero no devolvió el token esperado. "
                "Verifica usuario/contraseña."
            )

        info = data.get("infoColegio") or {}
        self._token = token
        self._token_viewer = data.get("tokenViewer") or ""
        self._refresh_token = data.get("refreshToken") or ""
        self._user_code = (info.get("usucod") or settings.sieweb_user or "").upper()
        self._set_authenticated_headers()

        # La interfaz real hace esta llamada inmediatamente después del login.
        # Si funciona, reemplaza el token inicial por el token ligado a la cookie.
        self._refresh_token_with_cookie()
        self._logged_in = True
        self.session.headers["Referer"] = f"{settings.sieweb_base_url}/sistema/intranet"

        return {
            "ok": True,
            "colegio": info.get("colname") or info.get("nombreColegio"),
            "nombre": info.get("nombre"),
            "tipo": info.get("tipnom"),
            "usuario": self._user_code,
            "anio": info.get("ano"),
            "modulo": info.get("modulo"),
        }

    def _ensure_auth(self) -> None:
        if self._logged_in:
            return
        if self.has_login_credentials:
            self.login()
            return
        if settings.sieweb_cookie or settings.sieweb_authorization:
            # Modo heredado de la v0.1; no es el recomendado.
            self._logged_in = True
            return
        raise SieWebError(
            "SieWeb aún no está configurado. Ejecuta CONFIGURAR_SIEWEB.bat "
            "para guardar tus credenciales únicamente en tu .env local."
        )

    def _request_once(
        self,
        method: str,
        path: str,
        *,
        params: dict[str, Any] | None = None,
        json: dict[str, Any] | list[Any] | None = None,
    ) -> requests.Response:
        return self.session.request(
            method,
            self._base(path),
            params=params,
            json=json,
            timeout=settings.sieweb_timeout_seconds,
        )

    def _looks_logged_out(self, response: requests.Response) -> bool:
        if response.status_code in (401, 403):
            return True
        content_type = response.headers.get("content-type", "").lower()
        return "text/html" in content_type and "login" in response.text.lower()

    def _request(
        self,
        method: str,
        path: str,
        *,
        params: dict[str, Any] | None = None,
        json: dict[str, Any] | list[Any] | None = None,
    ) -> dict[str, Any]:
        self._ensure_auth()
        response = self._request_once(method, path, params=params, json=json)

        if self._looks_logged_out(response) and self.has_login_credentials:
            # Primero intenta renovar con la cookie; si no basta, relogin completo.
            if self._refresh_token_with_cookie():
                response = self._request_once(method, path, params=params, json=json)
            if self._looks_logged_out(response):
                self.login()
                response = self._request_once(method, path, params=params, json=json)

        if self._looks_logged_out(response):
            raise SieWebError(
                f"SieWeb rechazó la sesión (HTTP {response.status_code})."
            )
        if not response.ok:
            raise SieWebError(
                f"SieWeb {method} {path} falló ({response.status_code}): "
                f"{response.text[:1000]}"
            )
        try:
            return response.json()
        except ValueError as exc:
            raise SieWebError(
                f"SieWeb devolvió una respuesta no JSON: {response.text[:500]}"
            ) from exc

    # ---------- Mensajería ----------
    def list_messages(self, folder_id: int = 1, search: str = "") -> dict[str, Any]:
        return self._request(
            "GET",
            "/lms/api/HyoMensajeria/obtMensajes",
            params={"search": search, "idCarpeta": folder_id},
        )

    def get_message(self, message_id: int, folder_id: int = 1) -> dict[str, Any]:
        return self._request(
            "GET",
            "/lms/api/HyoMensajeria/obtDetalle",
            params={"carpeta": folder_id, "idMensaje": message_id},
        )

    def send_reply(
        self,
        *,
        recipient_codes: list[str],
        subject: str,
        html_message: str,
        reply_to_message_id: int,
    ) -> dict[str, Any]:
        payload = {
            "adjunto": [],
            "asunto": subject,
            "fh_programado": "1970-01-01T00:00:00.000Z",
            "idEdition": str(reply_to_message_id),
            "mensaje": html_message,
            "para": recipient_codes,
            "programado": False,
            "response": 1,
        }
        return self._request(
            "POST", "/lms/api/HyoMensajeria/enviarMensaje", json=payload
        )

    # ---------- Calificaciones ----------
    def update_grades(
        self,
        *,
        year: str,
        course_code: str,
        class_period_id: int,
        period: int,
        section_ng: list[dict[str, str]],
        records: list[dict[str, Any]],
        class_name: str | None = None,
        notify: bool = True,
    ) -> dict[str, Any]:
        payload = {
            "ano": year,
            "cursocod": course_code,
            "idClasePeriodo": class_period_id,
            "objNG": section_ng,
            "periodo": period,
            "registros": records,
        }
        result = self._request("PUT", "/lms/api/HyoClasenota/actualizar", json=payload)
        estado = ((result.get("json") or {}).get("estado"))
        if estado != 1:
            raise SieWebError(f"SieWeb no confirmó actualización de notas: {result}")
        notification_result = None
        if notify and class_name:
            notification_result = self._request(
                "POST",
                "/lms/api/HyoClasenota/enviaNotificacion",
                json={"idClasePeriodo": class_period_id, "nombreClase": class_name},
            )
        return {"update": result, "notification": notification_result}

    def get_gradebook(
        self,
        *,
        class_period_id: int,
        root_content_id: int,
        extra_params: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        params: dict[str, Any] = {
            "idClasePeriodo": class_period_id,
            "idContenido": root_content_id,
        }
        params.update(extra_params or {})
        return self._request(
            "GET", "/lms/api/HyoClasenota/obtRegistroNotas", params=params
        )

    # ---------- Criterios / desempeños ----------
    def get_criteria(
        self,
        *,
        class_id: int,
        class_period_id: int,
        root_content_id: int,
        id_ambito: int | None = None,
        extra_params: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        params: dict[str, Any] = {
            "idClase": class_id,
            "idClasePeriodo": class_period_id,
            "idContenido": root_content_id,
            "idAmbito": id_ambito or settings.sieweb_id_ambito_registro_notas,
        }
        params.update(extra_params or {})
        return self._request(
            "GET", "/lms/api/HyoClaseContenido/dataInicialPesosCriterios", params=params
        )

    def upsert_criteria(
        self,
        *,
        class_id: int,
        records: list[dict[str, Any]],
        replica: dict[str, Any],
    ) -> dict[str, Any]:
        payload = {"registros": records, "idClase": class_id, "datosReplica": replica}
        result = self._request(
            "POST", "/lms/api/HyoClaseContenido/insertar", json=payload
        )
        if ((result.get("json") or {}).get("estado")) != 1:
            raise SieWebError(f"SieWeb no confirmó el guardado del criterio: {result}")
        return result

    # ---------- Conclusiones descriptivas ----------
    def get_conclusion(
        self,
        *,
        person_id: int,
        class_content_id: int,
        ng: str,
    ) -> dict[str, Any]:
        return self._request(
            "GET",
            "/lms/api/HyoClasecomentario/obtComentario",
            params={
                "idPersona": person_id,
                "idClaseContenido": class_content_id,
                "ng": ng,
            },
        )

    def update_conclusion(
        self,
        *,
        person_id: int,
        class_content_id: int,
        comment: str,
        comment2: str = "",
    ) -> dict[str, Any]:
        if len(comment) > 500:
            raise SieWebError("La conclusión descriptiva supera el límite de 500 caracteres.")
        payload = {
            "idPersona": person_id,
            "idClaseContenido": class_content_id,
            "comentario": comment,
            "comentario2": comment2,
        }
        result = self._request(
            "PUT", "/lms/api/HyoClasecomentario/actualizar", json=payload
        )
        if ((result.get("json") or {}).get("estado")) != 1:
            raise SieWebError(f"SieWeb no confirmó la conclusión descriptiva: {result}")
        return result
