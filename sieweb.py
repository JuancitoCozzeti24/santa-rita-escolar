from __future__ import annotations

import copy
import difflib
import html as html_lib
import json
import re
import unicodedata
import uuid
import time
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
                "User-Agent": "Mozilla/5.0 SieRoom-SRC/0.8.4",
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
        self._criteria_course_cache: dict[tuple[int, int], str] = {}
        self._last_criteria_context: dict[str, Any] = {}

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

    @staticmethod
    def _reply_detail_body(detail: dict[str, Any]) -> dict[str, Any]:
        """Devuelve el objeto útil de ``obtDetalle`` sin asumir un único wrapper.

        SieWeb ha devuelto tanto objetos directos como respuestas envueltas en ``json``
        en distintas rutas. Mantener esta normalización local evita que una variación
        menor de la respuesta rompa la preparación de una respuesta al hilo.
        """
        if not isinstance(detail, dict):
            return {}
        body = detail.get("json")
        return body if isinstance(body, dict) else detail

    @classmethod
    def _find_first_recursive(cls, value: Any, keys: tuple[str, ...]) -> Any:
        wanted = {str(key).lower() for key in keys}
        if isinstance(value, dict):
            for key, item in value.items():
                if str(key).lower() in wanted and item not in (None, "", [], {}):
                    return item
            for item in value.values():
                found = cls._find_first_recursive(item, keys)
                if found not in (None, "", [], {}):
                    return found
        elif isinstance(value, list):
            for item in value:
                found = cls._find_first_recursive(item, keys)
                if found not in (None, "", [], {}):
                    return found
        return None

    @classmethod
    def _reply_sender_code(cls, body: dict[str, Any]) -> str:
        """Extrae el USUCOD del remitente sin confundirlo con usuarios citados.

        Primero se buscan campos explícitos de remitente/emisor. Luego se inspeccionan
        contenedores con nombre de remitente. No se hace una búsqueda global de
        ``USUCOD`` porque el detalle puede incluir destinatarios y otros usuarios.
        """
        direct = cls._find_first_recursive(body, (
            "usucodRemitente", "usuCodRemitente", "codigoRemitente",
            "codRemitente", "remitenteCodigo", "remitenteUsucod",
            "usucodEmisor", "usuCodEmisor", "codigoEmisor", "codEmisor",
        ))
        if direct not in (None, ""):
            return str(direct).strip()

        def scan_named_containers(value: Any) -> str:
            if isinstance(value, dict):
                for key, item in value.items():
                    normalized = str(key).lower()
                    if normalized in {"remitente", "sender", "emisor", "from"} and isinstance(item, dict):
                        code = cls._find_first_recursive(
                            item, ("USUCOD", "usucod", "codigo", "code", "usuCod")
                        )
                        if code not in (None, ""):
                            return str(code).strip()
                for item in value.values():
                    code = scan_named_containers(item)
                    if code:
                        return code
            elif isinstance(value, list):
                for item in value:
                    code = scan_named_containers(item)
                    if code:
                        return code
            return ""

        return scan_named_containers(body)

    def prepare_reply(
        self,
        *,
        reply_to_message_id: int,
        html_message: str,
        recipient_codes: list[str] | None = None,
        subject: str = "",
        folder_id: int = 1,
    ) -> dict[str, Any]:
        """Prepara una respuesta usando el mensaje real como fuente de contexto.

        La versión anterior convertía ``idEdition`` a texto y dependía de que el
        llamador adivinara destinatario y asunto. La interfaz de SieWeb trabaja con
        IDs numéricos. Esta versión relee el mensaje, conserva su asunto por defecto,
        resuelve el remitente cuando el detalle lo expone y usa un ``idEdition`` real
        si SieWeb lo devuelve; de lo contrario usa el ID numérico del mensaje original.
        """
        message_id = int(reply_to_message_id)
        if message_id <= 0:
            raise SieWebError("reply_to_message_id debe ser un entero positivo.")

        detail = self.get_message(message_id, folder_id=int(folder_id))
        body = self._reply_detail_body(detail)

        raw_edition_id = self._find_first_recursive(
            body,
            (
                "idEdition", "idEdicion", "id_edicion", "idMensajeEdicion",
                "idMensajeEdition",
            ),
        )
        try:
            edition_id = int(raw_edition_id) if raw_edition_id not in (None, "") else message_id
        except (TypeError, ValueError):
            edition_id = message_id
        if edition_id <= 0:
            edition_id = message_id

        clean_codes: list[str] = []
        seen: set[str] = set()
        for code in recipient_codes or []:
            value = str(code or "").strip()
            if value and value not in seen:
                clean_codes.append(value)
                seen.add(value)
        if not clean_codes:
            sender_code = self._reply_sender_code(body)
            if sender_code:
                clean_codes = [sender_code]
        if not clean_codes:
            raise SieWebError(
                "SieWeb no expuso el USUCOD del remitente en el detalle. "
                "Proporciona recipient_codes para responder este hilo; no se envió nada."
            )

        clean_subject = str(subject or "").strip()
        if not clean_subject:
            found_subject = self._find_first_recursive(
                body, ("asunto", "subject", "tituloMensaje")
            )
            clean_subject = str(found_subject or "").strip()
        if not clean_subject:
            raise SieWebError(
                "SieWeb no devolvió el asunto del mensaje y no se proporcionó uno; no se envió nada."
            )

        body_html = str(html_message or "").strip()
        if not body_html:
            raise SieWebError("La respuesta necesita contenido; no se envió nada.")

        payload = {
            "adjunto": [],
            "asunto": clean_subject,
            "fh_programado": "1970-01-01T00:00:00.000Z",
            # Importante: la UI envía IDs numéricos; v0.7.4 lo convertía a string.
            "idEdition": edition_id,
            "mensaje": body_html,
            "para": clean_codes,
            "programado": False,
            "response": 1,
        }
        return {
            "reply_to_message_id": message_id,
            "folder_id": int(folder_id),
            "edition_id": edition_id,
            "edition_id_source": "detail" if raw_edition_id not in (None, "") else "message_id",
            "recipients": clean_codes,
            "subject": clean_subject,
            "payload": payload,
        }

    def send_reply(
        self,
        *,
        html_message: str,
        reply_to_message_id: int,
        recipient_codes: list[str] | None = None,
        subject: str = "",
        folder_id: int = 1,
    ) -> dict[str, Any]:
        """Responde un hilo existente y exige confirmación positiva de SieWeb.

        Nunca devuelve ``sent=True`` cuando el proveedor responde ``estado != 1``.
        """
        prepared = self.prepare_reply(
            reply_to_message_id=reply_to_message_id,
            html_message=html_message,
            recipient_codes=recipient_codes,
            subject=subject,
            folder_id=folder_id,
        )
        payload = prepared["payload"]
        result = self._request(
            "POST", "/lms/api/HyoMensajeria/enviarMensaje", json=payload
        )
        provider = result.get("json") if isinstance(result, dict) else None
        body = provider if isinstance(provider, dict) else (result if isinstance(result, dict) else {})
        estado = body.get("estado")
        if estado != 1:
            code = body.get("codigo") or body.get("code") or body.get("mensaje") or body.get("message")
            raise SieWebError(
                "SieWeb no confirmó la respuesta al hilo "
                f"{prepared['reply_to_message_id']} (estado={estado!r}, codigo={code!r}). "
                "No se marcará como enviada."
            )
        return {
            "sent": True,
            "message_id": body.get("idMensaje") or body.get("idmensaje"),
            "reply_to_message_id": prepared["reply_to_message_id"],
            "edition_id": prepared["edition_id"],
            "edition_id_source": prepared["edition_id_source"],
            "status_code": estado,
            "provider_message": body.get("mensaje") or body.get("message"),
            "recipients": prepared["recipients"],
            "subject": prepared["subject"],
            "raw": result,
        }

    # ---------- Descubrimiento de clases / periodos ----------
    _KNOWN_SECTIONS_2026 = {
        "S2A": 518,
        "S5A": 524,
    }

    # Períodos observados en 2026. Se usa solo como respaldo cuando una herramienta
    # recibe IDs crudos en vez de resolver primero sección+período.
    _KNOWN_PREVIOUS_PERIOD_2026 = {
        6304: 0,
        6305: 6304,
        6306: 6305,
        6550: 0,
        6551: 6550,
        6552: 6551,
    }

    @staticmethod
    def _normalize_text(value: str) -> str:
        value = unicodedata.normalize("NFKD", str(value or ""))
        value = "".join(ch for ch in value if not unicodedata.combining(ch))
        return " ".join(value.upper().strip().split())

    @classmethod
    def _normalize_section(cls, section: str) -> str:
        q = cls._normalize_text(section).replace(".", "").replace("º", "").replace("°", "")
        compact = q.replace(" ", "").replace("-", "")
        aliases = {
            "S2A": "S2A", "2A": "S2A", "2DOA": "S2A", "2DOANOA": "S2A",
            "2GRADOA": "S2A", "SEGUNDOA": "S2A", "SEGUNDOGRADOA": "S2A",
            "S5A": "S5A", "5A": "S5A", "5TOA": "S5A", "5TOANOA": "S5A",
            "5GRADOA": "S5A", "QUINTOA": "S5A", "QUINTOGRADOA": "S5A",
        }
        if compact in aliases:
            return aliases[compact]
        # Forma genérica para otras secciones (por ejemplo 2B, 5B).
        m = re.fullmatch(r"S?([1-6])([A-Z])", compact)
        if m:
            return f"S{m.group(1)}{m.group(2)}"
        return compact

    def list_classes(self, *, id_ambito: int, validar_permisos: bool = True) -> dict[str, Any]:
        """Lista cursos/clases disponibles para un ámbito (salón) de SieWeb."""
        packed = json.dumps(
            {"id_ambito": int(id_ambito), "validarPermisos": bool(validar_permisos)},
            ensure_ascii=False,
            separators=(",", ":"),
        )
        return self._request(
            "GET", "/lms/api/HyoClase/obtListar", params={"params": packed}
        )

    def list_class_periods(self, *, class_id: int) -> dict[str, Any]:
        """Lista los períodos disponibles de una clase SieWeb."""
        return self._request(
            "GET", "/lms/api/HyoClase/obtClasePeriodo", params={"idClase": int(class_id)}
        )

    def resolve_class_context(
        self,
        *,
        section: str,
        period: int,
        course_code: str = "05",
        id_ambito: int | None = None,
    ) -> dict[str, Any]:
        """Resuelve sección+curso+período a los IDs internos observados en SieWeb.

        Para 2026 se conocen S2A=518 y S5A=524. Si SieWeb cambia esos ámbitos en
        otro año, se puede pasar id_ambito explícitamente hasta mapear el listado de salones.
        """
        section_code = self._normalize_section(section)
        ambito = int(id_ambito) if id_ambito is not None else self._KNOWN_SECTIONS_2026.get(section_code)
        if ambito is None:
            raise SieWebError(
                "Sección no mapeada. Actualmente se conocen 2.º A/S2A y 5.º A/S5A; "
                "pasa id_ambito explícitamente para otra sección."
            )
        classes_payload = self.list_classes(id_ambito=ambito)
        classes = (classes_payload.get("json") or []) if isinstance(classes_payload, dict) else []
        selected = next(
            (row for row in classes if str(row.get("CURSOCOD") or "").strip() == str(course_code).strip()),
            None,
        )
        if not selected:
            raise SieWebError(
                f"No se encontró el curso {course_code} para la sección {section_code} (id_ambito={ambito})."
            )
        class_id = int(selected["ID_CLASE"])
        periods_payload = self.list_class_periods(class_id=class_id)
        periods = (periods_payload.get("json") or []) if isinstance(periods_payload, dict) else []
        selected_period = next(
            (row for row in periods if int(row.get("PERIODO") or 0) == int(period)),
            None,
        )
        if not selected_period:
            raise SieWebError(f"No existe el período {period} para ID_CLASE={class_id}.")
        previous_period = None
        earlier = [
            row for row in periods
            if int(row.get("PERIODO") or 0) < int(selected_period.get("PERIODO") or 0)
        ]
        if earlier:
            previous_period = max(earlier, key=lambda row: int(row.get("PERIODO") or 0))
        return {
            "section": section_code,
            "idAmbito": ambito,
            "course": selected,
            "period": selected_period,
            "idClase": class_id,
            "idClasePeriodo": int(selected_period["ID_CLASE_PERIODO"]),
            "idContenido": int(selected_period["ID_CONTENIDO"]),
            "periodo": int(selected_period["PERIODO"]),
            "idPeriodoAnt": (int(previous_period["ID_CLASE_PERIODO"]) if previous_period else 0),
        }

    # ---------- Directorio y mensajes nuevos ----------
    def list_messaging_users(self) -> dict[str, Any]:
        """Obtiene el directorio usado por Mensajería de SieWeb."""
        return self._request(
            "GET",
            "/lms/api/HyoUsuario/obtListaUsuariosIntranet",
            params={"isMensajeria": "true"},
        )

    def search_messaging_users(
        self,
        *,
        query: str,
        recipient_type: str = "any",
        ngs: str = "",
        limit: int = 30,
    ) -> list[dict[str, Any]]:
        """Busca destinatarios por nombre/código y deduplica por USUCOD.

        Según el directorio observado: 004=familia, 005=alumno, 006=docente.
        Si hay dos filas del mismo USUCOD, se prefiere la que incluye NGS.
        """
        raw = self.list_messaging_users()
        rows = (raw.get("json") or []) if isinstance(raw, dict) else []
        type_map = {
            "family": "004", "familia": "004", "parent": "004", "apoderado": "004",
            "student": "005", "alumno": "005", "estudiante": "005",
            "teacher": "006", "docente": "006", "profesor": "006",
        }
        wanted_type = type_map.get(self._normalize_text(recipient_type).lower(), "")
        # El lookup anterior usa .lower() sobre texto ya normalizado; resolver también directo.
        direct = str(recipient_type or "").strip().lower()
        wanted_type = type_map.get(direct, wanted_type)
        q = self._normalize_text(query)
        wanted_ngs = self._normalize_text(ngs).replace(" ", "")
        by_code: dict[str, dict[str, Any]] = {}
        for row in rows:
            code = str(row.get("USUCOD") or "").strip()
            if not code:
                continue
            hay = self._normalize_text(f"{row.get('USUNOM','')} {code}")
            if q and q not in hay:
                continue
            if wanted_type and str(row.get("TIPCOD") or "") != wanted_type:
                continue
            row_ngs = self._normalize_text(row.get("NGS") or "").replace(" ", "")
            if wanted_ngs and row_ngs and row_ngs != wanted_ngs:
                continue
            if wanted_ngs and not row_ngs:
                # Podría existir una fila duplicada con NGS; esperar a esa fila.
                pass
            previous = by_code.get(code)
            if previous is None or (row.get("NGS") and not previous.get("NGS")):
                by_code[code] = dict(row)
        out = list(by_code.values())
        if wanted_ngs:
            with_ngs = [r for r in out if self._normalize_text(r.get("NGS") or "").replace(" ", "") == wanted_ngs]
            if with_ngs:
                out = with_ngs
        out.sort(key=lambda r: self._normalize_text(r.get("USUNOM") or ""))
        return out[: max(1, min(int(limit), 100))]

    @classmethod
    def extract_section_codes(cls, text: str) -> list[str]:
        """Extrae secciones como 2A, 2.º B, S5A o 'segundo A' desde una frase natural."""
        raw = cls._normalize_text(text).replace("°", "")
        # NFKD convierte 2.º en 2.O; retirar ese marcador ordinal antes de buscar la sección.
        raw = re.sub(r"\b([1-6])\s*\.\s*O\b", r"\1", raw)
        found: list[str] = []

        # Formas compactas comunes: 2A, 2 A, S2A, 5-B, etc.
        for grade, letter in re.findall(r"(?:\bS)?\s*([1-6])\s*[-.]?\s*([A-Z])\b", raw):
            code = f"S{grade}{letter}"
            if code not in found:
                found.append(code)

        # Formas escritas frecuentes en español.
        words = {
            "PRIMERO": "1", "PRIMER": "1",
            "SEGUNDO": "2",
            "TERCERO": "3", "TERCER": "3",
            "CUARTO": "4",
            "QUINTO": "5",
            "SEXTO": "6",
        }
        for word, grade in words.items():
            for letter in re.findall(rf"\b{word}(?:\s+(?:ANO|GRADO|SECUNDARIA))?\s+([A-Z])\b", raw):
                code = f"S{grade}{letter}"
                if code not in found:
                    found.append(code)
        return found

    @classmethod
    def _family_match_score(cls, student_surname: str, family_name: str) -> tuple[float, str]:
        """Puntúa una relación estudiante→familia usando solo nombres reales del directorio.

        No inventa códigos. Acepta coincidencia exacta, apellido familiar como prefijo
        (p. ej. LAMAS VERA frente a LAMAS VERA TUDELA) y pequeñas erratas únicas
        (p. ej. ORTMAN/ORTMANN).
        """
        s = cls._normalize_text(student_surname)
        f = cls._normalize_text(family_name)
        if not s or not f:
            return 0.0, ""
        if s == f:
            return 1.0, "exact"
        st, ft = s.split(), f.split()
        if len(ft) >= 2 and len(st) >= len(ft) and st[: len(ft)] == ft:
            return 0.97, "family_prefix"
        if len(st) >= 2 and len(ft) >= len(st) and ft[: len(st)] == st:
            return 0.96, "student_prefix"
        ratio = difflib.SequenceMatcher(None, s, f).ratio()
        if ratio >= 0.92:
            return float(ratio), "fuzzy"
        return 0.0, ""

    def resolve_family_recipients_by_sections(self, sections: list[str]) -> dict[str, Any]:
        """Resuelve todos los USUCOD de familias de una o más secciones.

        Flujo: identifica alumnos TIPCOD=005 por NGS y los relaciona con usuarios
        familia TIPCOD=004 por apellidos. Devuelve diagnóstico y nunca inventa un
        destinatario. Los códigos de familia se deduplican.
        """
        wanted: list[str] = []
        for section in sections:
            code = self._normalize_section(section)
            if code and code not in wanted:
                wanted.append(code)
        if not wanted:
            raise SieWebError("Debes indicar al menos una sección, por ejemplo 2A o 2B.")

        raw = self.list_messaging_users()
        rows = (raw.get("json") or []) if isinstance(raw, dict) else []

        # Dedupe: conservar la fila de alumno que sí contiene NGS cuando existe.
        students_by_code: dict[str, dict[str, Any]] = {}
        families_by_code: dict[str, dict[str, Any]] = {}
        for row in rows:
            tip = str(row.get("TIPCOD") or "")
            code = str(row.get("USUCOD") or "").strip()
            if not code:
                continue
            if tip == "005":
                ngs = self._normalize_text(row.get("NGS") or "").replace(" ", "")
                if ngs not in wanted:
                    continue
                prev = students_by_code.get(code)
                if prev is None or (row.get("NGS") and not prev.get("NGS")):
                    students_by_code[code] = dict(row)
            elif tip == "004":
                families_by_code.setdefault(code, dict(row))

        resolved: list[dict[str, Any]] = []
        unresolved: list[dict[str, Any]] = []
        ambiguous: list[dict[str, Any]] = []

        for student in sorted(students_by_code.values(), key=lambda r: self._normalize_text(r.get("USUNOM") or "")):
            student_name = str(student.get("USUNOM") or "").strip()
            surname = student_name.split(",", 1)[0].strip() if "," in student_name else " ".join(student_name.split()[:2])
            candidates: list[tuple[float, str, dict[str, Any]]] = []
            for family in families_by_code.values():
                score, match_kind = self._family_match_score(surname, str(family.get("USUNOM") or ""))
                if score > 0:
                    candidates.append((score, match_kind, family))
            candidates.sort(key=lambda item: item[0], reverse=True)
            if not candidates:
                unresolved.append({
                    "student": student_name, "student_code": student.get("USUCOD"),
                    "section": student.get("NGS"), "surname": surname,
                })
                continue
            best_score = candidates[0][0]
            top = [item for item in candidates if abs(item[0] - best_score) < 1e-9]
            unique_codes = {str(item[2].get("USUCOD") or "") for item in top}
            if len(unique_codes) != 1:
                ambiguous.append({
                    "student": student_name, "student_code": student.get("USUCOD"),
                    "section": student.get("NGS"),
                    "matches": [
                        {"USUCOD": item[2].get("USUCOD"), "USUNOM": item[2].get("USUNOM"), "score": item[0], "match": item[1]}
                        for item in top[:10]
                    ],
                })
                continue
            _, match_kind, family = top[0]
            resolved.append({
                "student": student_name,
                "student_code": student.get("USUCOD"),
                "section": student.get("NGS"),
                "family_name": family.get("USUNOM"),
                "family_code": family.get("USUCOD"),
                "match": match_kind,
                "score": best_score,
            })

        recipient_codes: list[str] = []
        seen: set[str] = set()
        for item in resolved:
            code = str(item.get("family_code") or "").strip()
            if code and code not in seen:
                seen.add(code)
                recipient_codes.append(code)

        per_section: dict[str, dict[str, int]] = {}
        for section in wanted:
            students = [r for r in students_by_code.values() if self._normalize_text(r.get("NGS") or "").replace(" ", "") == section]
            ok = [r for r in resolved if self._normalize_text(r.get("section") or "").replace(" ", "") == section]
            bad = [r for r in unresolved if self._normalize_text(r.get("section") or "").replace(" ", "") == section]
            amb = [r for r in ambiguous if self._normalize_text(r.get("section") or "").replace(" ", "") == section]
            per_section[section] = {"students": len(students), "resolved": len(ok), "unresolved": len(bad), "ambiguous": len(amb)}

        return {
            "resolver": "messaging_directory_ngs_to_family",
            "requires_class_context": False,
            "directory_endpoint": "/lms/api/HyoUsuario/obtListaUsuariosIntranet?isMensajeria=true",
            "sections": wanted,
            "recipient_codes": recipient_codes,
            "recipient_count": len(recipient_codes),
            "students_found": len(students_by_code),
            "resolved": resolved,
            "unresolved": unresolved,
            "ambiguous": ambiguous,
            "complete": bool(students_by_code) and all(per_section.get(sec, {}).get("students", 0) > 0 for sec in wanted) and not unresolved and not ambiguous,
            "per_section": per_section,
        }

    def find_student_messaging_user(self, *, alucod: str) -> dict[str, Any] | None:
        """Busca el usuario de mensajería del alumno. Solo usa A+alucod si existe realmente."""
        expected = "A" + str(alucod or "").strip().lstrip("A")
        candidates = self.search_messaging_users(query=expected, recipient_type="student", limit=10)
        return next((r for r in candidates if str(r.get("USUCOD") or "") == expected), None)

    @staticmethod
    def _plain_text_to_html(text: str) -> str:
        """Convierte texto plano a HTML simple y seguro para el editor de SieWeb."""
        escaped = html_lib.escape(str(text or ""))
        paragraphs = [part.strip() for part in escaped.replace("\r\n", "\n").split("\n\n") if part.strip()]
        if not paragraphs:
            return "<p></p>"
        return "\n".join(f"<p>{p.replace(chr(10), '<br>')}</p>" for p in paragraphs)

    def compose_message(
        self,
        *,
        recipient_codes: list[str],
        subject: str,
        html_message: str = "",
        plain_text: str = "",
    ) -> dict[str, Any]:
        """Construye un correo NUEVO con el payload real observado en SieWeb.

        No necesita idEdition ni response porque no es una respuesta a un hilo.
        SieWeb crea el registro definitivo cuando se llama a enviarMensaje.
        """
        clean_codes = []
        seen = set()
        for code in recipient_codes:
            c = str(code or "").strip()
            if c and c not in seen:
                clean_codes.append(c)
                seen.add(c)
        clean_subject = str(subject or "").strip()
        if not clean_codes:
            raise SieWebError("El correo nuevo necesita al menos un destinatario USUCOD.")
        if not clean_subject:
            raise SieWebError("El correo nuevo necesita un asunto.")
        body_html = str(html_message or "").strip()
        if not body_html:
            body_html = self._plain_text_to_html(plain_text)
        if not body_html.strip():
            raise SieWebError("El correo nuevo necesita contenido.")
        return {
            "adjunto": [],
            "asunto": clean_subject,
            "fh_programado": "1970-01-01T00:00:00.000Z",
            "mensaje": body_html,
            "para": clean_codes,
            "programado": False,
        }

    def send_message(
        self,
        *,
        recipient_codes: list[str],
        subject: str,
        html_message: str = "",
        plain_text: str = "",
    ) -> dict[str, Any]:
        """Crea y envía un mensaje NUEVO usando HyoMensajeria/enviarMensaje."""
        payload = self.compose_message(
            recipient_codes=recipient_codes,
            subject=subject,
            html_message=html_message,
            plain_text=plain_text,
        )
        result = self._request(
            "POST", "/lms/api/HyoMensajeria/enviarMensaje", json=payload
        )
        body = result.get("json") or {}
        if body.get("estado") != 1:
            raise SieWebError(f"SieWeb no confirmó el envío del correo nuevo: {result}")
        return {
            "sent": True,
            "message_id": body.get("idMensaje"),
            "status_code": body.get("estado"),
            "provider_message": body.get("mensaje"),
            "recipients": payload["para"],
            "subject": payload["asunto"],
            "raw": result,
        }

    # ---------- Calificaciones ----------
    @staticmethod
    def _decode_grade_scope_value(value: Any) -> Any:
        """Normaliza wrappers JSON sin confundir el selector de sección con objNG."""
        if not isinstance(value, str):
            return value
        raw = value.strip()
        if not raw:
            return []
        if raw[:1] in {"[", "{"}:
            try:
                return json.loads(raw)
            except ValueError:
                return value
        return value

    @classmethod
    def _normalize_arr_nivel_grado(cls, value: Any) -> list[dict[str, str]]:
        """Devuelve el contrato nativo de SieWeb para objNG: [{"n": ..., "g": ...}]."""
        value = cls._decode_grade_scope_value(value)
        if isinstance(value, dict):
            wrapped = cls._dict_get_ci(value, "arrNivelGrado", "objNG")
            if wrapped not in (None, "", [], {}):
                value = cls._decode_grade_scope_value(wrapped)
            else:
                value = [value]
        if not isinstance(value, list) or not value:
            raise SieWebError(
                "PROTECCIÓN DE NOTAS SIEWEB: falta arrNivelGrado nativo; no se envió nada."
            )

        out: list[dict[str, str]] = []
        seen: set[tuple[str, str]] = set()
        for index, item in enumerate(value):
            if not isinstance(item, dict):
                raise SieWebError(
                    "PROTECCIÓN DE NOTAS SIEWEB: objNG debe usar arrNivelGrado "
                    f"con objetos {{n,g}}; elemento {index}={item!r}. No se envió nada."
                )
            n = cls._dict_get_ci(item, "n", "N", "nivel", "NIVEL")
            g = cls._dict_get_ci(item, "g", "G", "grado", "GRADO")
            if n in (None, "") or g in (None, ""):
                raise SieWebError(
                    "PROTECCIÓN DE NOTAS SIEWEB: arrNivelGrado contiene un objeto "
                    f"sin n/g en la posición {index}. No se envió nada."
                )
            pair = (str(n).strip(), str(g).strip())
            if pair not in seen:
                out.append({"n": pair[0], "g": pair[1]})
                seen.add(pair)
        if not out:
            raise SieWebError(
                "PROTECCIÓN DE NOTAS SIEWEB: arrNivelGrado quedó vacío; no se envió nada."
            )
        return out

    @classmethod
    def _normalize_arr_ngs(cls, value: Any) -> list[str]:
        """Normaliza arrNGS únicamente como selector de sección (p. ej. S2A)."""
        value = cls._decode_grade_scope_value(value)
        if isinstance(value, dict):
            wrapped = cls._dict_get_ci(value, "arrNGS", "NGS")
            if wrapped not in (None, "", [], {}):
                value = cls._decode_grade_scope_value(wrapped)
        if value in (None, "", [], {}):
            return []
        if isinstance(value, str):
            value = [value]
        if not isinstance(value, list):
            raise SieWebError(
                "PROTECCIÓN DE NOTAS SIEWEB: arrNGS debe ser una lista de secciones."
            )
        out: list[str] = []
        for item in value:
            if isinstance(item, dict):
                raise SieWebError(
                    "PROTECCIÓN DE NOTAS SIEWEB: arrNGS y arrNivelGrado son contratos distintos."
                )
            section = str(item or "").strip().upper()
            if section and section not in out:
                out.append(section)
        return out

    def resolve_grade_write_scope(
        self,
        summary: dict[str, Any],
        supplied_scope: Any = None,
    ) -> list[dict[str, str]]:
        """Resuelve objNG desde arrNivelGrado y valida cualquier selector heredado arrNGS."""
        class_info = summary.get("class") or {}
        native = self._normalize_arr_nivel_grado(
            self._dict_get_ci(class_info, "arrNivelGrado", "objNG")
        )
        if supplied_scope in (None, "", [], {}):
            return native

        supplied = self._decode_grade_scope_value(supplied_scope)
        if isinstance(supplied, dict):
            explicit_native = self._dict_get_ci(supplied, "arrNivelGrado", "objNG")
            explicit_ngs = self._dict_get_ci(supplied, "arrNGS", "NGS")
            if explicit_native not in (None, "", [], {}):
                supplied = self._decode_grade_scope_value(explicit_native)
            elif explicit_ngs not in (None, "", [], {}):
                supplied = self._decode_grade_scope_value(explicit_ngs)

        if isinstance(supplied, dict) or (
            isinstance(supplied, list)
            and supplied
            and all(isinstance(item, dict) for item in supplied)
        ):
            candidate = self._normalize_arr_nivel_grado(supplied)
            if candidate != native:
                raise SieWebError(
                    "PROTECCIÓN DE NOTAS SIEWEB: el arrNivelGrado solicitado no coincide "
                    "con el registro leído de SieWeb. No se envió nada."
                )
            return native

        requested_ngs = self._normalize_arr_ngs(supplied)
        native_ngs = self._normalize_arr_ngs(self._dict_get_ci(class_info, "arrNGS", "NGS"))
        if not requested_ngs or not native_ngs or set(requested_ngs) != set(native_ngs):
            raise SieWebError(
                "PROTECCIÓN DE NOTAS SIEWEB: el selector arrNGS solicitado no coincide "
                "con la sección del registro leído. No se envió nada."
            )
        return native

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
        if not records:
            raise SieWebError("No se enviaron notas: la lista de registros está vacía.")
        invalid = []
        for index, record in enumerate(records):
            if not isinstance(record, dict):
                invalid.append({"index": index, "reason": "record_not_object"})
                continue
            missing = [
                field for field in ("alucod", "idPersona", "notaNue")
                if record.get(field) in (None, "")
            ]
            if missing:
                invalid.append({
                    "index": index,
                    "alucod": record.get("alucod"),
                    "reason": "missing_required_fields",
                    "fields": missing,
                })
        if invalid:
            raise SieWebError(
                "No se enviaron notas porque hay registros incompletos: "
                + json.dumps(invalid, ensure_ascii=False)
            )

        obj_ng = self._normalize_arr_nivel_grado(section_ng)
        payload = {
            "ano": year,
            "cursocod": course_code,
            "idClasePeriodo": class_period_id,
            "objNG": obj_ng,
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
        """Lee el Registro de Notas con la ruta y parámetros observados en SieWeb.

        La interfaz real usa HyoClasePeriodo/obtRegistroNotas, no HyoClasenota.
        Para 2.º A y 5.º A de 2026 se puede inferir el período anterior cuando la
        herramienta recibe solo los IDs. extra_params siempre puede sobreescribirlo.
        """
        previous_id = self._KNOWN_PREVIOUS_PERIOD_2026.get(int(class_period_id), 0)
        params: dict[str, Any] = {
            "idClasePeriodo": int(class_period_id),
            "idContenido": int(root_content_id),
            "permisoMenu": 3,
            "idPeriodoAnt": int(previous_id),
            # La UI oficial envía objInfoRegIndividual con tipoRegistro y solo
            # agrega alucod cuando el usuario abre el registro individual. Enviar
            # alucod=False filtra la respuesta y elimina dataAlumno por completo.
            "objInfoRegIndividual[tipoRegistro]": "registroNotas",
            "chkNotFRET": False,
        }
        params = self._merge_endpoint_params(
            params,
            extra_params,
            protected_keys={"idClasePeriodo", "idContenido"},
            endpoint="HyoClasePeriodo/obtRegistroNotas",
        )
        return self._request(
            "GET", "/lms/api/HyoClasePeriodo/obtRegistroNotas", params=params
        )

    # ---------- Criterios / desempeños ----------
    @staticmethod
    def _parameter_key(value: Any) -> str:
        raw = unicodedata.normalize("NFKD", str(value or ""))
        raw = "".join(ch for ch in raw if not unicodedata.combining(ch))
        return re.sub(r"[^a-z0-9]", "", raw.lower())

    @classmethod
    def _merge_endpoint_params(
        cls,
        base: dict[str, Any],
        extra: dict[str, Any] | None,
        *,
        protected_keys: set[str],
        endpoint: str,
    ) -> dict[str, Any]:
        """Añade parámetros auxiliares sin permitir que cambien la identidad destino."""
        out = dict(base)
        protected = {cls._parameter_key(key): key for key in protected_keys}
        for key, value in dict(extra or {}).items():
            canonical = cls._parameter_key(key)
            if canonical in protected:
                base_key = protected[canonical]
                expected = base.get(base_key)
                if str(value).strip() != str(expected).strip():
                    raise SieWebError(
                        f"PROTECCIÓN DE CONTEXTO SIEWEB: {endpoint} no permite que "
                        f"extra_params cambie {base_key}={expected!r} por {value!r}. No se envió nada."
                    )
                continue
            out[key] = value
        return out

    def _resolve_criteria_course_context(
        self,
        *,
        class_id: int,
        id_ambito: int,
        extra_params: dict[str, Any] | None = None,
    ) -> tuple[str, dict[str, Any]]:
        """Resuelve el código de curso para el editor de criterios.

        El backend actual de SIEweb distingue el nombre del parámetro por
        mayúsculas/minúsculas: la consulta SQL enlaza ``CG.CURSOCOD`` desde
        ``cursocod``. v0.7.12 enviaba únicamente ``CURSOCOD`` y el proveedor
        terminaba compilando el SELECT con un binding indefinido. Conservamos
        ambos alias porque otros despliegues sí consumen la forma mayúscula.
        """
        extra = dict(extra_params or {})
        explicit = None
        for key in list(extra):
            if self._canon_text(key).replace(" ", "") == "cursocod":
                value = extra.get(key)
                if explicit is None and value not in (None, ""):
                    explicit = str(value).strip()
                extra.pop(key, None)
        if explicit:
            extra["CURSOCOD"] = explicit
            extra["cursocod"] = explicit
            self._criteria_course_cache[(int(id_ambito), int(class_id))] = explicit
            return explicit, extra

        cache_key=(int(id_ambito), int(class_id))
        cached=self._criteria_course_cache.get(cache_key)
        if cached:
            extra["CURSOCOD"] = cached
            extra["cursocod"] = cached
            return cached, extra

        classes_payload = self.list_classes(id_ambito=int(id_ambito))
        classes = (classes_payload.get("json") or []) if isinstance(classes_payload, dict) else []
        matches = [
            row for row in classes
            if isinstance(row, dict) and str(row.get("ID_CLASE") or "").strip() == str(class_id).strip()
        ]
        if len(matches) != 1:
            raise SieWebError(
                "No se pudo resolver CURSOCOD de forma única para dataInicialPesosCriterios "
                f"(idAmbito={id_ambito}, idClase={class_id}, coincidencias={len(matches)}). "
                "No se envió la escritura."
            )
        course_code = str(matches[0].get("CURSOCOD") or "").strip()
        if not course_code:
            raise SieWebError(
                "La clase resuelta no contiene CURSOCOD; no es seguro llamar "
                "dataInicialPesosCriterios sin ese contexto."
            )
        self._criteria_course_cache[cache_key] = course_code
        extra["CURSOCOD"] = course_code
        extra["cursocod"] = course_code
        return course_code, extra

    def get_criteria(
        self,
        *,
        class_id: int,
        class_period_id: int,
        root_content_id: int,
        id_ambito: int | None = None,
        extra_params: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        ambito = int(id_ambito or settings.sieweb_id_ambito_registro_notas)
        course_code, normalized_extra = self._resolve_criteria_course_context(
            class_id=int(class_id), id_ambito=ambito, extra_params=extra_params
        )
        params: dict[str, Any] = {
            "idClase": class_id,
            "idClasePeriodo": class_period_id,
            "idContenido": root_content_id,
            "idAmbito": ambito,
            "CURSOCOD": course_code,
            "cursocod": course_code,
        }
        params = self._merge_endpoint_params(
            params,
            normalized_extra,
            protected_keys={
                "idClase", "idClasePeriodo", "idContenido", "idAmbito",
                "CURSOCOD", "cursocod",
            },
            endpoint="HyoClaseContenido/dataInicialPesosCriterios",
        )
        self._last_criteria_context = {
            "idClase": int(class_id),
            "idClasePeriodo": int(class_period_id),
            "idContenido": int(root_content_id),
            "idAmbito": int(ambito),
            "CURSOCOD": str(course_code),
            "cursocod": str(course_code),
        }
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

    @staticmethod
    def _canon_text(value: Any) -> str:
        raw = unicodedata.normalize("NFKD", str(value or ""))
        raw = "".join(ch for ch in raw if not unicodedata.combining(ch))
        return re.sub(r"\s+", " ", re.sub(r"[^a-z0-9]+", " ", raw.lower())).strip()

    def find_exact_criterion(self, summary: dict[str, Any], *, description: str,
                             parent_id: int | None = None, level: int | None = None) -> list[dict[str, Any]]:
        """Busca un criterio por texto canónico y, opcionalmente, padre/nivel.

        Se usa para evitar duplicados y, sobre todo, para no reutilizar IDs de otra sección.
        """
        wanted = self._canon_text(description)
        out = []
        for item in summary.get("criteria") or []:
            text = item.get("descripcion") or item.get("desc") or item.get("abreviatura") or ""
            if self._canon_text(text) != wanted:
                continue
            if parent_id is not None and str(item.get("idpadre")) != str(parent_id):
                continue
            if level is not None and str(item.get("nivelEva")) != str(level):
                continue
            out.append(item)
        return out

    def assert_performance_target(self, summary: dict[str, Any], *, header_id: int,
                                  performance_level: int = 3) -> dict[str, Any]:
        """Bloquea escrituras sobre competencia/Nivel de Logro.

        Para el flujo automático Classroom→SIEweb solo se permite un desempeño de nivel 3.
        """
        matches = [x for x in summary.get("criteria") or [] if str(x.get("id")) == str(header_id)]
        if len(matches) != 1:
            raise SieWebError(f"El desempeño {header_id} no existe o es ambiguo; no se guardó nada.")
        target = matches[0]
        if str(target.get("nivelEva")) != str(performance_level):
            raise SieWebError(
                f"PROTECCIÓN NIVEL DE LOGRO: el destino {header_id} tiene nivelEva={target.get('nivelEva')}; "
                f"el flujo automático solo admite desempeños nivel {performance_level}. No se guardó nada."
            )
        return target

    @staticmethod
    def _walk_dicts(value: Any):
        """Recorre todos los dicts de una respuesta SIEweb sin asumir su envoltura."""
        if isinstance(value, dict):
            yield value
            for child in value.values():
                yield from SieWebClient._walk_dicts(child)
        elif isinstance(value, list):
            for child in value:
                yield from SieWebClient._walk_dicts(child)

    def _criterion_description(self, row: dict[str, Any]) -> str:
        for key in ("descripcion", "desc", "descComp", "DESCRIPCION", "DESC", "nombre", "nom"):
            if row.get(key) not in (None, ""):
                return str(row.get(key))
        return ""

    def _criterion_parent(self, row: dict[str, Any]) -> Any:
        # En dataInicialPesosCriterios real el padre jerárquico se llama
        # ID_CONTENIDO_REF (p. ej. Desempeño -> ID_CONTENIDO de su Capacidad).
        for key in (
            "idpadre", "idPadre", "ID_PADRE",
            "idContenidoPadre", "idClaseContenidoPadre",
            "ID_CONTENIDO_REF", "idContenidoRef", "id_contenido_ref",
        ):
            if key in row:
                return row.get(key)
        return None

    def _criterion_level(self, row: dict[str, Any]) -> Any:
        # Filas persistidas exponen NIVEL=1/2/3 para
        # Competencia/Capacidad/Desempeño. Las filas NUEVAS que construye la UI
        # real son más espartanas y pueden omitir NIVEL; en ese caso se infiere
        # desde ID_PROGRAMA (3->1, 4->2, 5->3, 6->4).
        for key in ("nivelEva", "nivel", "NIVEL", "NIVEL_EVA", "nivelEvaluacion"):
            if key in row and row.get(key) not in (None, ""):
                return row.get(key)
        prog = row.get("ID_PROGRAMA", row.get("idPrograma"))
        try:
            prog_int = int(prog)
        except (TypeError, ValueError):
            return None
        if 3 <= prog_int <= 6:
            return prog_int - 2
        return None

    @staticmethod
    def _criterion_content_id(row: dict[str, Any]) -> Any:
        for key in ("ID_CONTENIDO", "idContenido", "id_contenido"):
            if key in row:
                return row.get(key)
        return None

    @staticmethod
    def _criterion_class_content_id(row: dict[str, Any]) -> Any:
        for key in ("ID_CLASE_CONTENIDO", "idClaseContenido", "id_clase_contenido", "id"):
            if key in row:
                return row.get(key)
        return None

    @classmethod
    def _walk_criterion_tree(cls, rows: list[Any], path: tuple[Any, ...] = ()):
        """Recorre el árbol real resCriterios conservando referencias a sus nodos."""
        if not isinstance(rows, list):
            return
        for idx, row in enumerate(rows):
            if not isinstance(row, dict):
                continue
            node_path = path + (idx,)
            yield node_path, row
            children = row.get("children")
            if isinstance(children, list):
                yield from cls._walk_criterion_tree(children, node_path + ("children",))

    def _find_tree_nodes(self, rows: list[Any], *, content_id: Any | None = None,
                         description: str | None = None, parent_id: Any | None = None,
                         level: int | None = None) -> list[tuple[tuple[Any, ...], dict[str, Any]]]:
        wanted = self._canon_text(description) if description is not None else None
        out=[]
        for path, row in self._walk_criterion_tree(rows):
            if content_id is not None and str(self._criterion_content_id(row)) != str(content_id):
                continue
            if wanted is not None and self._canon_text(self._criterion_description(row)) != wanted:
                continue
            if parent_id is not None and str(self._criterion_parent(row)) != str(parent_id):
                continue
            if level is not None and str(self._criterion_level(row)) != str(level):
                continue
            out.append((path,row))
        return out

    def find_raw_criteria(self, raw: dict[str, Any], *, description: str | None = None,
                          parent_id: int | None = None, level: int | None = None) -> list[dict[str, Any]]:
        """Busca nodos reales de dataInicialPesosCriterios para poder clonar su esquema exacto."""
        wanted = self._canon_text(description) if description is not None else None
        out=[]
        seen=set()
        for row in self._walk_dicts(raw):
            desc=self._criterion_description(row)
            if not desc:
                continue
            if wanted is not None and self._canon_text(desc) != wanted:
                continue
            parent=self._criterion_parent(row)
            lev=self._criterion_level(row)
            if parent_id is not None and str(parent) != str(parent_id):
                continue
            if level is not None and lev is not None and str(lev) != str(level):
                continue
            marker=id(row)
            if marker not in seen:
                seen.add(marker); out.append(row)
        return out

    @staticmethod
    def _strip_identity_for_new_criterion(record: dict[str, Any]) -> dict[str, Any]:
        """Quita solo identidades persistidas; conserva flags/pesos/campos que SIEweb exige."""
        out=copy.deepcopy(record)
        identity_keys={
            "id", "ID", "idClaseContenido", "ID_CLASE_CONTENIDO", "idContenido", "ID_CONTENIDO",
            "idCriterio", "ID_CRITERIO", "codigo", "codContenido"
        }
        for key in list(out):
            if key in identity_keys:
                out.pop(key, None)
        return out

    def build_new_performance_record(self, *, class_id: int, class_period_id: int,
                                     root_content_id: int, parent_id: int, description: str,
                                     level: int = 3, id_ambito: int | None = None,
                                     extra_params: dict[str, Any] | None = None,
                                     preferred_template: dict[str, Any] | None = None) -> dict[str, Any]:
        """Construye una fila nueva con las mismas reglas del guardado jerárquico v0.7.11."""
        raw=self.get_criteria(class_id=class_id,class_period_id=class_period_id,
                              root_content_id=root_content_id,id_ambito=id_ambito,
                              extra_params=extra_params)
        model=self.extract_criteria_editor_model(raw)
        merged=self.merge_requested_criteria_into_editor_rows(
            model["rows"],
            [{"descripcion":description,"idpadre":parent_id,"nivelEva":level}],
            [{"description":description,"parent_id":parent_id,"level":level}],
        )
        matches=self._find_tree_nodes(merged["rows"],description=description,parent_id=parent_id,level=level)
        if len(matches)!=1:
            raise SieWebError("No se pudo construir de forma única el nuevo desempeño.")
        return copy.deepcopy(matches[0][1])

    @staticmethod
    def _criterion_row_score(row: dict[str, Any]) -> int:
        """Puntúa si un dict parece una fila editable real de HyoClaseContenido."""
        if not isinstance(row, dict):
            return -1000
        keys={str(k).lower() for k in row}
        desc_keys={"descripcion","desc","desccomp","nombre","nom"}
        if not (keys & desc_keys):
            return -1000
        score=20
        for group, weight in (
            ({"id","idclasecontenido","id_clase_contenido","idcontenido","id_contenido","idcriterio"}, 10),
            ({"idpadre","id_padre","idpadrecontenido","idcontenidopadre","idclasecontenidopadre",
              "id_contenido_ref","idcontenidoref"}, 9),
            ({"niveleva","nivel","nivel_eva","nivelevaluacion"}, 8),
            ({"peso","porcentaje","ponderacion"}, 5),
            ({"orden","numord","posicion","indice"}, 3),
            ({"flexiste","editoreg"}, 3),
            ({"activo","estado","habilitado"}, 2),
        ):
            if keys & group:
                score += weight
        return score

    @classmethod
    def _walk_lists_with_paths(cls, value: Any, path: tuple[Any, ...] = ()):
        if isinstance(value, dict):
            for key, child in value.items():
                if isinstance(child, list):
                    yield path + (key,), child
                yield from cls._walk_lists_with_paths(child, path + (key,))
        elif isinstance(value, list):
            for idx, child in enumerate(value):
                yield from cls._walk_lists_with_paths(child, path + (idx,))

    def extract_criteria_editor_model(self, raw: dict[str, Any]) -> dict[str, Any]:
        """Extrae el árbol completo que realmente edita SIEweb.

        En el despliegue observado de SIEweb, dataInicialPesosCriterios devuelve
        ``json.resCriterios`` como árbol Competencia -> Capacidad -> Desempeño.
        Se prefiere explícitamente esa ruta; el detector heurístico queda solo como
        compatibilidad con otros despliegues.
        """
        observed = None
        if isinstance(raw, dict):
            envelope = raw.get("json")
            if isinstance(envelope, dict) and isinstance(envelope.get("resCriterios"), list):
                observed = envelope.get("resCriterios")
        if isinstance(observed, list):
            nodes=[row for _,row in self._walk_criterion_tree(observed)]
            useful=[self._criterion_row_score(r) for r in nodes if self._criterion_description(r) != ""]
            if useful and max(useful) >= 30:
                return {
                    "path":["json","resCriterios"],
                    "score":sum(x for x in useful if x > 0),
                    "rows":copy.deepcopy(observed),
                    "candidate_count":1,
                    "tree":True,
                    "node_count":len(nodes),
                }

        candidates=[]
        for path, rows in self._walk_lists_with_paths(raw):
            dict_rows=[r for r in rows if isinstance(r, dict)]
            if not dict_rows:
                continue
            scores=[self._criterion_row_score(r) for r in dict_rows]
            useful=[x for x in scores if x >= 20]
            if not useful:
                continue
            path_text="/".join(str(x).lower() for x in path)
            path_bonus=18 if any(x in path_text for x in ("registro","criter","contenido","peso")) else 0
            if any(x in path_text for x in ("cabecera","nota","alumno")):
                path_bonus -= 20
            coverage=len(useful)/max(1,len(dict_rows))
            score=sum(useful)+int(coverage*30)+path_bonus+min(len(dict_rows),50)
            candidates.append((score,path,rows,dict_rows))
        if not candidates:
            raise SieWebError(
                "SIEweb devolvió dataInicialPesosCriterios, pero no se pudo identificar "
                "de forma segura el modelo editable. No se envió nada."
            )
        candidates.sort(key=lambda x:x[0], reverse=True)
        score,path,rows,dict_rows=candidates[0]
        if max(self._criterion_row_score(r) for r in dict_rows) < 30:
            raise SieWebError("El modelo de criterios encontrado no tiene identidad suficiente; no se envió nada.")
        return {"path":list(path),"score":score,"rows":copy.deepcopy(rows),
                "candidate_count":len(candidates),"tree":False,"node_count":len(dict_rows)}

    @classmethod
    def _find_named_value(cls, value: Any, names: set[str]) -> Any:
        wanted={cls._canon_text(x).replace(" ","") for x in names}
        if isinstance(value, dict):
            for key, child in value.items():
                nk=cls._canon_text(key).replace(" ","")
                if nk in wanted:
                    return copy.deepcopy(child)
            for child in value.values():
                found=cls._find_named_value(child,names)
                if found is not None:
                    return found
        elif isinstance(value, list):
            for child in value:
                found=cls._find_named_value(child,names)
                if found is not None:
                    return found
        return None

    def extract_replica_from_editor(self, raw: dict[str, Any], fallback: Any = None) -> Any:
        # Algunos despliegues sí devuelven datosReplica explícitamente. objOrigenReplica
        # NO es equivalente y no debe enviarse como destino de réplica.
        found=self._find_named_value(raw,{"datosReplica","dataReplica","replica","datos_replicar"})
        return copy.deepcopy(fallback if found is None else found)

    @staticmethod
    def normalize_replica_for_criteria_write(replica: Any) -> dict[str, Any]:
        """Acepta únicamente el objeto ``paramDatosReplica`` de la UI oficial.

        La captura del cliente de SIEWeb demuestra que ``datosReplica`` no es una
        lista de destinos. Es un objeto con el contexto de la clase y el flag
        ``replicar``. Los valores vacíos se completan después desde las lecturas
        autenticadas; una lista no vacía se rechaza para no replicar por error.
        """
        if replica in (None, {}, []):
            return {}
        if isinstance(replica, dict):
            return copy.deepcopy(replica)
        if isinstance(replica, list):
            raise SieWebError(
                "datosReplica no admite una lista de destinos en el contrato nativo de SIEWeb. "
                "La réplica entre secciones debe hacerse como altas independientes; no se envió nada."
            )
        raise SieWebError("datosReplica debe ser un objeto de contexto; no se envió nada.")

    @staticmethod
    def _criteria_json(raw: dict[str, Any]) -> dict[str, Any]:
        envelope=(raw or {}).get("json") if isinstance(raw,dict) else None
        return envelope if isinstance(envelope,dict) else {}

    def _native_child_program(self, raw: dict[str, Any], parent: dict[str, Any]) -> dict[str, Any]:
        """Obtiene el programa hijo igual que ``mostrarPrograma`` en la UI."""
        envelope=self._criteria_json(raw)
        data_program=envelope.get("dataPrograma") or {}
        obj_programs=data_program.get("objProgramas") if isinstance(data_program,dict) else None
        parent_program=parent.get("ID_PROGRAMA",parent.get("idPrograma"))
        choices = None
        if isinstance(obj_programs, dict):
            choices = obj_programs.get(str(parent_program))
            if choices is None:
                choices = obj_programs.get(parent_program)
        program = None
        if isinstance(choices, list):
            performance_choices = [
                item for item in choices
                if isinstance(item, dict) and str(item.get("ID_PROGRAMA")) == "5"
            ]
            if len(performance_choices) > 1:
                raise SieWebError(
                    "SIEWeb devolvió más de un programa hijo de tipo Desempeño; no se puede elegir uno de forma segura."
                )
            if performance_choices:
                program = copy.deepcopy(performance_choices[0])

        # Compatibilidad defensiva con despliegues que omitan dataPrograma: un
        # desempeño hermano persistido aporta los mismos metadatos de programa.
        if not isinstance(program,dict):
            children=parent.get("children") or []
            sibling=next((x for x in children if isinstance(x,dict) and self._criterion_level(x)==3),None)
            if sibling:
                program={
                    "ID_PROGRAMA":sibling.get("ID_PROGRAMA",5),
                    "ID_PROGRAMA_REF":parent_program,
                    "DESCRIPCION":sibling.get("DESCPROGRAMA") or "Desempeño",
                    "ICONO":sibling.get("ICONO") or "simbolo5",
                    "COLOR":sibling.get("COLOR") or "#ffffff",
                    "LIMITE":6,
                }
        if not isinstance(program,dict):
            raise SieWebError("SIEWeb no devolvió el programa hijo de la capacidad; no se envió nada.")
        if str(program.get("ID_PROGRAMA_REF")) != str(parent_program):
            raise SieWebError("El programa hijo no corresponde a la capacidad seleccionada; no se envió nada.")
        if str(program.get("ID_PROGRAMA")) != "5":
            raise SieWebError(
                f"PROTECCIÓN NIVEL DE LOGRO: el programa hijo es {program.get('ID_PROGRAMA')}, "
                "no Desempeño (5). No se envió nada."
            )
        return program

    @classmethod
    def _requested_value(cls, requested: dict[str, Any], names: set[str], default: Any) -> Any:
        wanted={cls._canon_text(x).replace(" ","") for x in names}
        for key,value in (requested or {}).items():
            if cls._canon_text(key).replace(" ","") in wanted:
                return copy.deepcopy(value)
        return copy.deepcopy(default)

    def build_native_new_criterion_record(
        self, *, raw: dict[str, Any], parent: dict[str, Any], requested: dict[str, Any],
        description: str, class_id: int, class_period_id: int,
        reserved_indices: set[int] | None = None,
    ) -> dict[str, Any]:
        """Reproduce el objeto ``defaultDataContenido`` del modal oficial."""
        program=self._native_child_program(raw,parent)
        limit=int(program.get("LIMITE") or 0)
        if limit <= 0:
            raise SieWebError("El programa Desempeño no permite nuevas filas; no se envió nada.")
        used=set(reserved_indices or set())
        for child in parent.get("children") or []:
            if not isinstance(child,dict) or str(child.get("ID_PROGRAMA"))!="5":
                continue
            try: used.add(int(child.get("INDICE")))
            except (TypeError,ValueError): pass
        index=next((candidate for candidate in range(1,limit+1) if candidate not in used),None)
        if index is None:
            raise SieWebError(
                f"La capacidad {self._criterion_content_id(parent)} alcanzó el límite de {limit} desempeños; "
                f"no se creó '{description}'."
            )
        parent_id=self._criterion_content_id(parent)
        parent_key=str(parent.get("LLAVE") or "").strip()
        if parent_id in (None,"",0,"0") or not parent_key:
            raise SieWebError("La capacidad padre no tiene ID_CONTENIDO/LLAVE persistidos; no se envió nada.")
        parent_level=self._criterion_level(parent)
        if str(parent_level)!="2":
            raise SieWebError(
                f"PROTECCIÓN NIVEL DE LOGRO: el padre tiene nivel {parent_level}, no Capacidad (2). "
                "No se envió nada."
            )
        abbreviation=self._requested_value(requested,{"ABREVIATURA","abrev","abrevComp"},"")
        record={
            "ID_CLASE_CONTENIDO":0,
            "ID_CLASE":int(class_id),
            "ID_CLASE_PERIODO":int(class_period_id),
            "EXCLUIR":self._requested_value(requested,{"EXCLUIR"},0),
            "SUMATIVO":self._requested_value(requested,{"SUMATIVO"},0),
            "PESO":self._requested_value(requested,{"PESO"},1),
            "ID_CONTENIDO":0,
            "DESCRIPCION":str(description),
            "ID_PROGRAMA":int(program["ID_PROGRAMA"]),
            "ID_CONTENIDO_REF":parent_id,
            "ABREVIATURA":"" if abbreviation is None else abbreviation,
            "INCLUSIVO":self._requested_value(requested,{"INCLUSIVO"},0),
            "ORDEN":1,
            "BASE":0,
            "INDICE":index,
            "replicar":False,
            "TRADUCCION":self._requested_value(requested,{"TRADUCCION"},None),
            "NIVEL_PADRE":int(parent_level),
            "LLAVE":f"{program['ID_PROGRAMA']}-{index}_{parent_key}",
            "COLORP":program.get("COLOR") or "#ffffff",
            "DESCP":program.get("DESCRIPCION") or "Desempeño",
            "ICONOP":program.get("ICONO") or "simbolo5",
        }
        return record

    def build_native_replica_context(
        self, *, raw: dict[str, Any], class_info: dict[str, Any], parent: dict[str, Any],
        criteria_context: dict[str, Any], supplied: Any = None,
    ) -> dict[str, Any]:
        """Construye ``paramDatosReplica`` exactamente como el componente oficial."""
        override=self.normalize_replica_for_criteria_write(supplied)
        envelope=self._criteria_json(raw)
        annual=envelope.get("nivelReplicaAnual") or []
        annual_first=annual[0] if isinstance(annual,list) and annual and isinstance(annual[0],dict) else {}
        derived={
            "periodo":class_info.get("periodo",class_info.get("PERIODO")),
            "idCurso":class_info.get("idCurso") or parent.get("ID_CURSO") or parent.get("idCurso"),
            "grupocod":class_info.get("grupocod") or parent.get("GRUPOCOD") or parent.get("grupocod"),
            "cursocod":class_info.get("cursocod") or class_info.get("CURSOCOD")
                       or criteria_context.get("cursocod") or criteria_context.get("CURSOCOD"),
            "limiteReplica":annual_first.get("LIMITE"),
            "replicar":False,
        }
        # Se permiten overrides solo si no cambian la identidad resuelta de la clase.
        for key,value in override.items():
            if key=="replicar" and bool(value):
                raise SieWebError(
                    "La réplica automática del modal está deshabilitada por seguridad; "
                    "se deben crear altas verificadas por sección. No se envió nada."
                )
            if key in derived and derived[key] not in (None,"") and value not in (None,"") \
                    and str(value)!=str(derived[key]):
                raise SieWebError(
                    f"datosReplica.{key}={value!r} no coincide con el contexto leído "
                    f"({derived[key]!r}); no se envió nada."
                )
            if key in derived and value not in (None,""):
                derived[key]=copy.deepcopy(value)
        missing=[key for key in ("periodo","idCurso","grupocod","cursocod","limiteReplica")
                 if derived.get(key) in (None,"")]
        if missing:
            raise SieWebError(
                "No se pudo construir paramDatosReplica nativo; faltan "+", ".join(missing)+". No se envió nada."
            )
        for key in ("periodo","idCurso","limiteReplica"):
            derived[key]=int(derived[key])
        derived["grupocod"]=str(derived["grupocod"])
        derived["cursocod"]=str(derived["cursocod"])
        derived["replicar"]=False
        return derived

    @staticmethod
    def _set_existing_alias(row: dict[str, Any], aliases: tuple[str, ...], value: Any,
                            default_key: str | None = None) -> str:
        for key in aliases:
            if key in row:
                row[key]=value
                return key
        if default_key:
            row[default_key]=value
            return default_key
        return ""

    def _raw_row_matches(self, row: dict[str, Any], *, description: str,
                         parent_id: int | None, level: int | None) -> bool:
        if self._canon_text(self._criterion_description(row)) != self._canon_text(description):
            return False
        if parent_id is not None and str(self._criterion_parent(row)) != str(parent_id):
            return False
        if level is not None and str(self._criterion_level(row)) != str(level):
            return False
        return True

    def _set_new_row_semantics(self, newrow: dict[str, Any], *, parent: dict[str, Any],
                               description: str, level: int, index: int,
                               requested: dict[str, Any]) -> dict[str, Any]:
        """Construye una fila NUEVA con la forma espartana que genera la UI real.

        v0.7.10 clonaba un desempeño persistido y solo anulaba sus IDs. La captura
        real de ``dataInicialPesosCriterios`` muestra otra cosa: las plazas nuevas
        ``flExiste=false`` NO incluyen campos de identidad/contexto del servidor
        (ID_CLASE, ID_CURSO, GRUPOCOD, ID_CLASE_PERIODO, NIVEL, TIPO_EVA,
        FL_CONCLUSION, ORDEN_PROG, etc.). Esos campos aparecen recién cuando el
        backend persiste la fila.

        Por ello v0.7.11 construye una fila *sparse/UI-native* desde cero y usa el
        hermano solo para recuperar metadatos visuales/de programa.
        """
        schema = copy.deepcopy(newrow or {})
        program_id = schema.get("ID_PROGRAMA") or schema.get("idPrograma") or 5
        parent_id = self._criterion_content_id(parent)
        parent_key = str(parent.get("LLAVE") or parent.get("llave") or "").strip()

        # La UI observada crea plazas vacías con este conjunto compacto de claves.
        out: dict[str, Any] = {
            "ABREVIATURA": None,
            "ABREV_ORIGI": None,
            "COLOR": schema.get("COLOR") or "#ffffff",
            "DESCPROGRAMA": schema.get("DESCPROGRAMA") or "Desempeño",
            "DESCRIPCION": description,
            "EDITOREG": 1,
            "EXCLUIR": schema.get("EXCLUIR", 0) if schema.get("EXCLUIR") not in (None, "") else 0,
            "ICONO": schema.get("ICONO") or "simbolo5",
            "ID_CLASE_CONTENIDO": None,
            "ID_CONTENIDO": None,
            "ID_CONTENIDO_REF": parent_id,
            "ID_PROGRAMA": int(program_id) if str(program_id).isdigit() else program_id,
            "INCLUSIVO": schema.get("INCLUSIVO", 0) if schema.get("INCLUSIVO") not in (None, "") else 0,
            "INDICE": index,
            "INDICE_ORIGI": index,
            "ORDEN": index,
            "ORIGI": "",
            # Una fila vacía llega con PESO=""; al editar un desempeño la UI termina
            # guardando el peso efectivo. Si el llamador no indica uno, heredamos el
            # peso real del hermano (normalmente 1) en lugar de copiar su identidad.
            "PESO": schema.get("PESO", 1) if schema.get("PESO") not in (None, "") else 1,
            "PESO_ORIGI": "",
            "SUMATIVO": schema.get("SUMATIVO", 0) if schema.get("SUMATIVO") not in (None, "") else 0,
            "EXCLUIR_PORCENTAJE": (
                schema.get("EXCLUIR_PORCENTAJE", 0)
                if schema.get("EXCLUIR_PORCENTAJE") not in (None, "") else 0
            ),
            "TRADUCCION": None,
            "TRAD_ORIGI": None,
            "LLAVE": f"{program_id}-{index}_{parent_key}" if parent_key else f"{program_id}-{index}",
            "flExiste": False,
            "bloquearCriterio": False,
            "children": [],
        }

        # Alias pedagógicos permitidos. No se aceptan identidades ni campos de
        # contexto que la plaza nueva real todavía no posee.
        for key, value in requested.items():
            canon = self._canon_text(key).replace(" ", "")
            if canon in {"abreviatura", "abrev", "abrevcomp"}:
                out["ABREVIATURA"] = copy.deepcopy(value)
            elif canon in {"peso"} and value not in (None, ""):
                out["PESO"] = copy.deepcopy(value)
            elif canon in {"inclusivo"} and value not in (None, ""):
                out["INCLUSIVO"] = copy.deepcopy(value)
            elif canon in {"sumativo"} and value not in (None, ""):
                out["SUMATIVO"] = copy.deepcopy(value)
            elif canon in {"excluir"} and value not in (None, ""):
                out["EXCLUIR"] = copy.deepcopy(value)
            elif canon in {"excluirporcentaje"} and value not in (None, ""):
                out["EXCLUIR_PORCENTAJE"] = copy.deepcopy(value)
            elif canon in {"traduccion"}:
                out["TRADUCCION"] = copy.deepcopy(value)

        # El nivel NO se serializa en una fila nueva UI-native. Se valida/infiere
        # internamente por ID_PROGRAMA (5 => desempeño/nivel 3).
        inferred = self._criterion_level(out)
        if str(inferred) != str(level):
            raise SieWebError(
                f"El programa de la fila nueva infiere nivel {inferred}, no {level}; no se envió nada."
            )
        return out

    def merge_requested_criteria_into_editor_rows(self, rows: list[Any],
                                                  records: list[dict[str, Any]],
                                                  expected: list[dict[str, Any]]) -> dict[str, Any]:
        """Aplica altas/ediciones en el árbol real Competencia->Capacidad->Desempeño.

        Mantiene compatibilidad con modelos planos antiguos, pero cuando existen ``children``
        nunca inserta un desempeño en la raíz.
        """
        if len(records) != len(expected):
            raise SieWebError("records y expected deben tener la misma longitud; no se envió nada.")
        out=copy.deepcopy(rows)
        operations=[]
        is_tree=any(isinstance(r,dict) and isinstance(r.get("children"),list) for r in out)

        for requested, exp in zip(records, expected):
            desc=str(exp["description"])
            parent_id=exp.get("parent_id")
            level=int(exp.get("level",3))
            matches=self._find_tree_nodes(out,description=desc,parent_id=parent_id,level=level)
            if len(matches)>1:
                raise SieWebError(f"El editor ya contiene más de un desempeño '{desc}'; no se envió nada.")
            if len(matches)==1:
                path,row=matches[0]
                # Edición real: conservar identidad y ORIGINAL, pero marcar EDITOREG=1.
                for key,value in requested.items():
                    if key in row and key not in {"id","ID","idClaseContenido","ID_CLASE_CONTENIDO",
                                                  "idContenido","ID_CONTENIDO","LLAVE","llave",
                                                  "flExiste","EDITOREG"}:
                        row[key]=copy.deepcopy(value)
                self._set_existing_alias(row,("DESCRIPCION","descripcion","desc","descComp","DESC","nombre","nom"),desc,"DESCRIPCION")
                # No se reescribe ID_CONTENIDO_REF ni LLAVE en una edición existente.
                if "EDITOREG" in row: row["EDITOREG"]=1
                elif "editoreg" in row: row["editoreg"]=1
                else: row["EDITOREG"]=1
                if "flExiste" in row: row["flExiste"]=True
                operations.append({"action":"update","path":list(path),"description":desc,
                                   "idContenido":self._criterion_content_id(row),"editoreg":1})
                continue

            if is_tree:
                parents=self._find_tree_nodes(out,content_id=parent_id,level=max(1,level-1))
                if len(parents)!=1:
                    raise SieWebError(
                        f"No se encontró de forma única la capacidad padre ID_CONTENIDO={parent_id} "
                        f"para crear '{desc}'. No se envió nada."
                    )
                parent_path,parent=parents[0]
                children=parent.get("children")
                if not isinstance(children,list):
                    raise SieWebError(f"La capacidad {parent_id} no expone children; no se envió nada.")
                siblings=[r for r in children if isinstance(r,dict) and str(self._criterion_level(r))==str(level)]
                if not siblings:
                    raise SieWebError(
                        f"La capacidad {parent_id} no tiene un desempeño hermano real para inferir el esquema de alta."
                    )
                # El límite real del programa Desempeño observado es 6 por capacidad.
                indices=[]
                for sib in siblings:
                    val=sib.get("INDICE",sib.get("indice"))
                    try: indices.append(int(val))
                    except (TypeError,ValueError): pass
                next_index=(max(indices) if indices else len(siblings))+1
                if next_index > 6:
                    raise SieWebError(
                        f"La capacidad {parent_id} ya alcanzó el límite seguro de 6 desempeños; no se creó '{desc}'."
                    )
                sibling=max(siblings,key=self._criterion_row_score)
                newrow=self._set_new_row_semantics(
                    sibling,parent=parent,description=desc,level=level,index=next_index,requested=requested
                )
                # Revalidación estructural antes de construir el payload.
                if str(self._criterion_parent(newrow)) != str(parent_id):
                    raise SieWebError("El nuevo desempeño no quedó enlazado a su capacidad; escritura bloqueada.")
                expected_llave=f"{newrow.get('ID_PROGRAMA',5)}-{next_index}_{parent.get('LLAVE','')}"
                if parent.get("LLAVE") and str(newrow.get("LLAVE")) != expected_llave:
                    raise SieWebError("La LLAVE jerárquica del nuevo desempeño es inconsistente; escritura bloqueada.")
                children.append(newrow)
                operations.append({"action":"insert","parent_path":list(parent_path),
                                   "child_index":len(children)-1,"description":desc,
                                   "parent_id":parent_id,"indice":next_index,"llave":newrow.get("LLAVE"),
                                   "flExiste":newrow.get("flExiste")})
                continue

            # Compatibilidad con builds antiguos que devuelvan una lista plana.
            siblings=[]
            for idx,row in enumerate(out):
                if not isinstance(row,dict): continue
                if str(self._criterion_parent(row))!=str(parent_id): continue
                if str(self._criterion_level(row))!=str(level): continue
                if self._criterion_row_score(row)<30: continue
                siblings.append((idx,row))
            if not siblings:
                raise SieWebError(f"No existe una fila hermana editable para crear '{desc}' bajo {parent_id}.")
            sibling_idx,sibling=max(siblings,key=lambda ir:self._criterion_row_score(ir[1]))
            next_index=len(siblings)+1
            synthetic_parent={"ID_CONTENIDO":parent_id,"LLAVE":"","NIVEL":level-1}
            newrow=self._set_new_row_semantics(sibling,parent=synthetic_parent,description=desc,
                                                level=level,index=next_index,requested=requested)
            insert_at=sibling_idx+1
            out.insert(insert_at,newrow)
            operations.append({"action":"insert-flat","index":insert_at,"description":desc})
        return {"rows":out,"operations":operations,"tree":is_tree}

    def validate_criteria_tree_for_write(self, rows: list[Any], *, class_id: int,
                                         class_period_id: int) -> dict[str, Any]:
        """Valida invariantes del árbol antes de llamar HyoClaseContenido/insertar."""
        errors=[]
        new_nodes=[]
        edited_nodes=[]
        seen_content={}
        seen_class_content={}

        def walk(nodes: list[Any], parent: dict[str, Any] | None = None, path: tuple[Any,...] = ()):
            sibling_keys=set()
            for idx,row in enumerate(nodes or []):
                if not isinstance(row,dict):
                    continue
                pth=path+(idx,)
                desc=self._criterion_description(row)
                cid=self._criterion_content_id(row)
                ccid=self._criterion_class_content_id(row)
                level=self._criterion_level(row)
                llave=row.get("LLAVE") or row.get("llave")
                exists=row.get("flExiste") if "flExiste" in row else row.get("FLEXISTE")
                edit=row.get("EDITOREG") if "EDITOREG" in row else row.get("editoreg")

                if llave not in (None,""):
                    key=str(llave)
                    if key in sibling_keys:
                        errors.append({"path":list(pth),"reason":"duplicate_llave_sibling","llave":key})
                    sibling_keys.add(key)

                if cid not in (None,"",0,"0"):
                    key=str(cid)
                    if key in seen_content:
                        errors.append({"path":list(pth),"reason":"duplicate_ID_CONTENIDO",
                                       "id":cid,"other_path":seen_content[key]})
                    else:
                        seen_content[key]=list(pth)
                if ccid not in (None,"",0,"0"):
                    key=str(ccid)
                    if key in seen_class_content:
                        errors.append({"path":list(pth),"reason":"duplicate_ID_CLASE_CONTENIDO",
                                       "id":ccid,"other_path":seen_class_content[key]})
                    else:
                        seen_class_content[key]=list(pth)

                for key in ("ID_CLASE","idClase","idclase"):
                    if row.get(key) not in (None,"",0,"0") and str(row.get(key)) != str(class_id):
                        errors.append({"path":list(pth),"reason":"wrong_idClase","actual":row.get(key),"expected":class_id})
                for key in ("ID_CLASE_PERIODO","idClasePeriodo","idclaseperiodo"):
                    if row.get(key) not in (None,"",0,"0") and str(row.get(key)) != str(class_period_id):
                        errors.append({"path":list(pth),"reason":"wrong_idClasePeriodo","actual":row.get(key),"expected":class_period_id})

                if parent is not None and desc:
                    parent_cid=self._criterion_content_id(parent)
                    if parent_cid not in (None,"") and str(self._criterion_parent(row)) != str(parent_cid):
                        errors.append({"path":list(pth),"reason":"broken_parent_ref",
                                       "actual":self._criterion_parent(row),"expected":parent_cid})
                    parent_level=self._criterion_level(parent)
                    if level is not None and parent_level is not None:
                        try:
                            if int(level) != int(parent_level)+1:
                                errors.append({"path":list(pth),"reason":"broken_level_chain",
                                               "level":level,"parent_level":parent_level})
                        except (TypeError,ValueError):
                            pass

                if exists is False and desc:
                    node={"path":list(pth),"description":desc,"level":level,"parent_id":self._criterion_parent(row),
                          "llave":llave,"editoreg":edit}
                    new_nodes.append(node)
                    if cid not in (None,"") or ccid not in (None,""):
                        errors.append({**node,"reason":"new_node_has_persisted_identity",
                                       "ID_CONTENIDO":cid,"ID_CLASE_CONTENIDO":ccid})
                    if str(edit) != "1":
                        errors.append({**node,"reason":"new_node_not_marked_edited"})
                    # La captura real de las plazas flExiste=false demuestra que
                    # estos campos pertenecen a filas YA persistidas. Si aparecen
                    # en una alta, estamos volviendo al clone-payload de v0.7.10.
                    persisted_only={
                        "ID_CLASE","idClase","ID_CURSO","idCurso","GRUPOCOD",
                        "ID_CLASE_PERIODO","idClasePeriodo","NIVEL","nivel",
                        "nivelEva","TIPO_EVA","FL_CONCLUSION","ORDEN_PROG",
                    }
                    leaked=sorted(k for k in persisted_only if k in row)
                    if leaked:
                        errors.append({**node,"reason":"new_node_leaks_persisted_server_fields",
                                       "keys":leaked})
                    required_new={
                        "ID_CLASE_CONTENIDO","ID_CONTENIDO","ID_CONTENIDO_REF",
                        "ID_PROGRAMA","DESCRIPCION","INDICE","INDICE_ORIGI",
                        "ORDEN","LLAVE","flExiste","EDITOREG",
                    }
                    missing=sorted(k for k in required_new if k not in row)
                    if missing:
                        errors.append({**node,"reason":"new_node_missing_ui_fields",
                                       "keys":missing})
                elif exists is True and str(edit) == "1":
                    edited_nodes.append({"path":list(pth),"description":desc,"level":level,
                                         "ID_CONTENIDO":cid,"ID_CLASE_CONTENIDO":ccid})
                    if cid in (None,"",0,"0") or ccid in (None,"",0,"0"):
                        errors.append({"path":list(pth),"reason":"edited_existing_node_missing_identity"})

                children=row.get("children")
                if isinstance(children,list):
                    walk(children,row,pth+("children",))

        walk(rows)
        return {
            "ok":not errors,
            "errors":errors,
            "new_nodes":new_nodes,
            "edited_nodes":edited_nodes,
            "root_count":len(rows or []),
            "node_count":sum(1 for _ in self._walk_criterion_tree(rows or [])),
        }

    def _upsert_criteria_verified_legacy(self, *, class_id: int, class_period_id: int,
                                 root_content_id: int, id_ambito: int,
                                 records: list[dict[str, Any]],
                                 replica: dict[str, Any] | list[Any] | None,
                                 expected: list[dict[str, Any]],
                                 extra_params: dict[str, Any] | None = None,
                                 verification_attempts: int = 3) -> dict[str, Any]:
        """Crea desempeños con el contrato exacto del modal y verifica persistencia.

        La UI oficial llama ``HyoClaseContenido/insertar`` con exactamente tres
        propiedades: ``registros``, ``idClase`` y ``datosReplica``. Para una alta,
        ``registros`` contiene el objeto ``defaultDataContenido`` del modal, no el
        árbol ``resCriterios`` ni una plaza ``flExiste=false``. v0.8.4 conserva ese
        contrato y elimina los fallbacks que causaban e0006/falsos éxitos.
        """
        try:
            id_ambito = int(id_ambito)
        except (TypeError, ValueError) as exc:
            raise SieWebError("id_ambito es obligatorio para guardar desempeños; no se usará un ámbito por defecto.") from exc
        if id_ambito <= 0:
            raise SieWebError("id_ambito debe ser positivo para guardar desempeños; no se usará un ámbito por defecto.")
        if not records or len(records)!=len(expected):
            raise SieWebError("records y expected deben ser listas no vacías de igual longitud; no se envió nada.")

        before = self.get_gradebook_summary(class_period_id=class_period_id, root_content_id=root_content_id,
                                            extra_params=extra_params)
        class_info = before.get("class") or {}
        context_errors = []
        if class_info.get("idClase") not in (None, "") and str(class_info.get("idClase")) != str(class_id):
            context_errors.append({"field":"idClase","expected":class_id,"actual":class_info.get("idClase")})
        if class_info.get("idClasePeriodo") not in (None, "") and str(class_info.get("idClasePeriodo")) != str(class_period_id):
            context_errors.append({"field":"idClasePeriodo","expected":class_period_id,"actual":class_info.get("idClasePeriodo")})
        if class_info.get("idContenidoPrin") not in (None, "") and str(class_info.get("idContenidoPrin")) != str(root_content_id):
            context_errors.append({"field":"idContenido","expected":root_content_id,"actual":class_info.get("idContenidoPrin")})
        if context_errors:
            raise SieWebError(
                "PROTECCIÓN DE CONTEXTO SIEWEB: los IDs del registro no corresponden al destino solicitado; "
                "se bloqueó la escritura antes del POST: " + json.dumps(context_errors, ensure_ascii=False)
            )
        duplicate_preflight=[]
        for e in expected:
            found=self.find_exact_criterion(before,description=str(e["description"]),
                                            parent_id=e.get("parent_id"),level=e.get("level",3))
            if len(found)>1:
                duplicate_preflight.append({"expected":e,"matches":found})
        if duplicate_preflight:
            raise SieWebError("Hay desempeños duplicados antes de escribir; se detuvo el proceso: "+
                              json.dumps(duplicate_preflight,ensure_ascii=False))

        raw_before=self.get_criteria(class_id=class_id,class_period_id=class_period_id,
                                     root_content_id=root_content_id,id_ambito=id_ambito,
                                     extra_params=extra_params)
        model=self.extract_criteria_editor_model(raw_before)
        # Si las filas editables exponen idClase/idClasePeriodo, deben pertenecer al mismo
        # contexto. Esto detecta exactamente la mezcla de sección que v0.7.8 no veía.
        row_class_ids=set()
        row_period_ids=set()
        for _, row in self._walk_criterion_tree(model["rows"]):
            for key in ("idClase","ID_CLASE","idclase"):
                if row.get(key) not in (None, "", 0, "0"):
                    row_class_ids.add(str(row.get(key)))
            for key in ("idClasePeriodo","ID_CLASE_PERIODO","idclaseperiodo"):
                if row.get(key) not in (None, "", 0, "0"):
                    row_period_ids.add(str(row.get(key)))
        if row_class_ids and str(class_id) not in row_class_ids:
            raise SieWebError(
                f"PROTECCIÓN DE CONTEXTO SIEWEB: el editor leído con idAmbito={id_ambito} "
                f"pertenece a idClase={sorted(row_class_ids)}, no a {class_id}. No se envió nada."
            )
        if row_period_ids and str(class_period_id) not in row_period_ids:
            raise SieWebError(
                f"PROTECCIÓN DE CONTEXTO SIEWEB: el editor leído con idAmbito={id_ambito} "
                f"pertenece a idClasePeriodo={sorted(row_period_ids)}, no a {class_period_id}. No se envió nada."
            )
        criteria_context = dict(getattr(self, "_last_criteria_context", {}) or {})
        expected_context = {
            "idClase": int(class_id),
            "idClasePeriodo": int(class_period_id),
            "idContenido": int(root_content_id),
            "idAmbito": int(id_ambito),
        }
        stale_context = [
            {"field": key, "expected": value, "actual": criteria_context.get(key)}
            for key, value in expected_context.items()
            if str(criteria_context.get(key)) != str(value)
        ]
        if stale_context:
            raise SieWebError(
                "PROTECCIÓN DE CONTEXTO SIEWEB: la lectura del editor no dejó el "
                "contexto exacto requerido para insertar; se bloqueó el POST: "
                + json.dumps(stale_context, ensure_ascii=False)
            )
        write_course_code = str(
            criteria_context.get("cursocod") or criteria_context.get("CURSOCOD") or ""
        ).strip()
        if not write_course_code:
            raise SieWebError(
                "No se resolvió cursocod para HyoClaseContenido/insertar; "
                "se bloqueó la escritura antes del POST."
            )

        # Construir únicamente altas de modal. Si el criterio ya existe, el flujo
        # es idempotente; no se convierte una petición de alta en edición implícita.
        native_records=[]
        operations=[]
        parents_for_new=[]
        reserved_by_parent: dict[str,set[int]]={}
        for requested,exp in zip(records,expected):
            if not isinstance(requested,dict) or not isinstance(exp,dict):
                raise SieWebError("Cada registro/expectativa debe ser un objeto; no se envió nada.")
            desc=str(exp.get("description") or "").strip()
            parent_id=exp.get("parent_id")
            level=int(exp.get("level",3))
            if not desc or parent_id in (None,"",0,"0"):
                raise SieWebError("description y parent_id son obligatorios; no se envió nada.")
            if level!=3:
                raise SieWebError(
                    f"PROTECCIÓN NIVEL DE LOGRO: solo se crean desempeños nivel 3; se recibió nivel {level}."
                )
            matches=self._find_tree_nodes(
                model["rows"],description=desc,parent_id=parent_id,level=level
            )
            if len(matches)>1:
                raise SieWebError(f"El editor contiene más de un desempeño '{desc}'; no se envió nada.")
            if len(matches)==1:
                row=matches[0][1]
                if self._criterion_content_id(row) in (None,"",0,"0"):
                    raise SieWebError(f"'{desc}' aparece sin identidad persistida; no se envió nada.")
                operations.append({"action":"already-present","description":desc,
                                   "parent_id":parent_id,"idContenido":self._criterion_content_id(row)})
                continue
            parents=self._find_tree_nodes(model["rows"],content_id=parent_id,level=2)
            if len(parents)!=1:
                raise SieWebError(
                    f"No se encontró de forma única la capacidad padre ID_CONTENIDO={parent_id} "
                    f"para crear '{desc}'. No se envió nada."
                )
            parent=parents[0][1]
            key=str(parent_id)
            record=self.build_native_new_criterion_record(
                raw=raw_before,parent=parent,requested=requested,description=desc,
                class_id=class_id,class_period_id=class_period_id,
                reserved_indices=reserved_by_parent.setdefault(key,set()),
            )
            reserved_by_parent[key].add(int(record["INDICE"]))
            native_records.append(record)
            parents_for_new.append(parent)
            operations.append({"action":"insert-native-modal","description":desc,
                               "parent_id":parent_id,"indice":record["INDICE"],
                               "llave":record["LLAVE"]})

        def verify_once() -> tuple[list[dict[str,Any]],bool]:
            raw_after=self.get_criteria(
                class_id=class_id,class_period_id=class_period_id,
                root_content_id=root_content_id,id_ambito=id_ambito,extra_params=extra_params
            )
            editor_after=self.extract_criteria_editor_model(raw_after)
            after=self.get_gradebook_summary(
                class_period_id=class_period_id,root_content_id=root_content_id,extra_params=extra_params
            )
            checks=[]
            for exp in expected:
                found_editor=[row for _,row in self._walk_criterion_tree(editor_after["rows"])
                              if self._raw_row_matches(
                                  row,description=str(exp["description"]),
                                  parent_id=exp.get("parent_id"),level=exp.get("level",3)
                              ) and self._criterion_content_id(row) not in (None,"",0,"0")]
                found_gradebook=self.find_exact_criterion(
                    after,description=str(exp["description"]),
                    parent_id=exp.get("parent_id"),level=exp.get("level",3)
                )
                checks.append({"expected":exp,"editor_count":len(found_editor),
                               "gradebook_count":len(found_gradebook)})
            return checks,all(x["editor_count"]==1 and x["gradebook_count"]==1 for x in checks)

        if not native_records:
            checks=[]
            for exp in expected:
                editor_count=len(self._find_tree_nodes(
                    model["rows"],description=str(exp["description"]),
                    parent_id=exp.get("parent_id"),level=exp.get("level",3)
                ))
                gradebook_count=len(self.find_exact_criterion(
                    before,description=str(exp["description"]),
                    parent_id=exp.get("parent_id"),level=exp.get("level",3)
                ))
                checks.append({"expected":exp,"editor_count":editor_count,
                               "gradebook_count":gradebook_count})
            if not all(x["editor_count"]==1 and x["gradebook_count"]==1 for x in checks):
                raise SieWebError(
                    "El desempeño aparece en el editor pero no simultáneamente en el registro de notas; "
                    "se bloqueó la operación idempotente. Verificación: "+
                    json.dumps(checks,ensure_ascii=False)
                )
            return {
                "saved":True,"already_present":True,"verification":checks,"attempts":[],
                "editor_model_path":model["path"],"editor_model_score":model["score"],
                "operations":operations,"sent_record_count":0,"sent_node_count":0,
                "write_strategy":"no-post-already-present","write_attempts":[],
                "idAmbito":id_ambito,"CURSOCOD":write_course_code,
                "context_guard":"exact-ambito-native-modal-roster-v0.8.4",
                "mode":"ui-native-modal-coursecode-roster-v0.8.4",
            }

        replica_contexts = [
            self.build_native_replica_context(
                raw=raw_before, class_info=class_info, parent=parent,
                criteria_context=criteria_context, supplied=replica,
            )
            for parent in parents_for_new
        ]
        replica_for_post = replica_contexts[0]
        inconsistent_replica_contexts = [
            {"index": index, "context": context}
            for index, context in enumerate(replica_contexts)
            if context != replica_for_post
        ]
        if inconsistent_replica_contexts:
            raise SieWebError(
                "Los desempeños solicitados no comparten el mismo paramDatosReplica nativo; "
                "se bloqueó el lote antes del POST para evitar e0006 o una réplica cruzada: "
                + json.dumps(inconsistent_replica_contexts, ensure_ascii=False)
            )
        native_keys={
            "ID_CLASE_CONTENIDO","ID_CLASE","ID_CLASE_PERIODO","EXCLUIR","SUMATIVO","PESO",
            "ID_CONTENIDO","DESCRIPCION","ID_PROGRAMA","ID_CONTENIDO_REF","ABREVIATURA",
            "INCLUSIVO","ORDEN","BASE","INDICE","replicar","TRADUCCION","NIVEL_PADRE",
            "LLAVE","COLORP","DESCP","ICONOP",
        }
        malformed=[{"index":idx,"missing":sorted(native_keys-set(row)),
                    "extra":sorted(set(row)-native_keys)}
                   for idx,row in enumerate(native_records) if set(row)!=native_keys]
        if malformed:
            raise SieWebError(
                "El registro modal no coincide con defaultDataContenido; se bloqueó el POST: "+
                json.dumps(malformed,ensure_ascii=False)
            )
        payload={"registros":copy.deepcopy(native_records),"idClase":int(class_id),
                 "datosReplica":copy.deepcopy(replica_for_post)}
        result=self._request("POST","/lms/api/HyoClaseContenido/insertar",json=payload)
        body=(result.get("json") or {}) if isinstance(result,dict) else {}
        provider_state=body.get("estado")
        provider_code=body.get("codigo") or body.get("code") or body.get("error") or body.get("mensaje")
        write_attempts=[{
            "strategy":"ui-native-modal-new-record","estado":provider_state,"codigo":provider_code,
            "record_count":len(native_records),"node_count":len(native_records),
            "payload_keys":sorted(payload),"record_keys":sorted(native_keys),
            "datosReplica":"native-object","replicar":False,
        }]

        attempts=[]; final=[]
        max_attempts=max(1,min(int(verification_attempts),5))
        # Incluso si el proveedor devuelve error, una sola relectura decide si fue
        # un falso negativo. Nunca se realiza un segundo POST automático.
        for attempt in range(1,max_attempts+1):
            final,ok=verify_once()
            attempts.append({"attempt":attempt,"ok":ok,"checks":final})
            if ok: break
            if provider_state!=1: break
            if attempt<max_attempts: time.sleep(0.6*attempt)
        if not attempts[-1]["ok"]:
            if provider_state!=1:
                raise SieWebError(
                    "SIEWeb rechazó el alta nativa del desempeño "
                    f"(estado={provider_state!r}, codigo={provider_code!r}). Se realizó un solo POST, "
                    "la relectura confirmó que no persistió y NO se escribirán notas. Diagnóstico: "+
                    json.dumps(write_attempts,ensure_ascii=False)
                )
            raise SieWebError(
                "FALSO ÉXITO SIEWEB: insertar devolvió estado=1, pero el desempeño no quedó "
                "persistido simultáneamente en el editor y el registro de notas. "
                "Se detuvo el flujo y NO se escribirán calificaciones. Verificación: "+
                json.dumps(final,ensure_ascii=False)
            )
        successful_strategy="ui-native-modal-new-record"
        if provider_state!=1:
            successful_strategy+="-provider-false-negative"
        payload_diagnostics={
            "ok":True,"contract":"defaultDataContenido+paramDatosReplica",
            "top_level_keys":sorted(payload),"record_keys":sorted(native_keys),
            "replicar":False,
        }

        return {
            "saved":True,
            "update":result,
            "verification":final,
            "attempts":attempts,
            "editor_model_path":model["path"],
            "editor_model_score":model["score"],
            "operations":operations,
            "payload_diagnostics":payload_diagnostics,
            "sent_record_count":len(native_records),
            "sent_node_count":len(native_records),
            "write_strategy":successful_strategy,
            "write_attempts":write_attempts,
            "idAmbito":id_ambito,
            "CURSOCOD":((getattr(self, "_last_criteria_context", {}) or {}).get("CURSOCOD")),
            "context_guard":"exact-ambito-native-modal-roster-v0.8.4",
            "mode":"ui-native-modal-coursecode-roster-v0.8.4",
        }

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


    # ---------- Utilidades integrales sobre el registro ----------
    @classmethod
    def _gradebook_container_score(cls, value: Any) -> int:
        if not isinstance(value, dict):
            return -1
        keys={cls._canon_text(k).replace(" ", "") for k in value}
        score=0
        if "infoclaseperiodo" in keys: score += 50
        if "cabeceranotas" in keys: score += 35
        if "dataalumno" in keys or "dataalumnos" in keys: score += 45
        if "datapermisoregistro" in keys: score += 10
        return score

    @classmethod
    def _locate_gradebook_data(cls, payload: Any) -> dict[str, Any]:
        """Localiza el objeto real del registro aunque SIEweb agregue wrappers.

        La respuesta histórica llega como ``{json:{...}}``, pero algunas llamadas
        pueden quedar envueltas una capa adicional. v0.7.11 asumía una única capa;
        cuando eso no se cumplía el resumen terminaba con ``students: []`` aun
        existiendo ``dataAlumno`` más abajo.
        """
        if not isinstance(payload, dict):
            return {}
        best=(cls._gradebook_container_score(payload), payload)
        queue=[payload]
        seen=set()
        while queue:
            current=queue.pop(0)
            oid=id(current)
            if oid in seen:
                continue
            seen.add(oid)
            if isinstance(current, dict):
                score=cls._gradebook_container_score(current)
                if score > best[0]:
                    best=(score,current)
                for child in current.values():
                    if isinstance(child,(dict,list)):
                        queue.append(child)
            elif isinstance(current, list):
                for child in current:
                    if isinstance(child,(dict,list)):
                        queue.append(child)
        # Si no apareció ninguna marca de registro, conserva compatibilidad con la
        # respuesta antigua devolviendo json o el objeto directo.
        if best[0] <= 0:
            body=payload.get("json")
            return body if isinstance(body,dict) else payload
        return best[1]

    @classmethod
    def _dict_get_ci(cls, value: dict[str, Any], *names: str) -> Any:
        wanted={cls._canon_text(n).replace(" ","") for n in names}
        for key,item in (value or {}).items():
            if cls._canon_text(key).replace(" ","") in wanted:
                return item
        return None

    @classmethod
    def _student_list_score(cls, rows: Any) -> int:
        if not isinstance(rows,list) or not rows:
            return -1
        sample=[r for r in rows[:8] if isinstance(r,dict)]
        if not sample:
            return -1
        score=0
        for row in sample:
            data=cls._dict_get_ci(row,"datos","datosAlumno","alumno","estudiante","infoAlumno")
            if not isinstance(data,dict):
                data=row
            notes=cls._dict_get_ci(row,"notas","notasAlumno","dataNotas","celdas")
            if isinstance(notes,dict): score += 8
            if cls._dict_get_ci(data,"idPersona","ID_PERSONA") not in (None,""): score += 6
            if cls._dict_get_ci(data,"alucod","ALUCOD","codigoAlumno") not in (None,""): score += 6
            if cls._dict_get_ci(data,"nomcomp","NOMCOMP","nombreCompleto","alumno") not in (None,""): score += 5
        return score

    @classmethod
    def _find_student_rows(cls, data: dict[str, Any]) -> tuple[list[dict[str, Any]], str]:
        # Ruta oficial observada primero.
        for key in ("dataAlumno","dataAlumnos","alumnos","students"):
            rows=cls._dict_get_ci(data,key)
            if isinstance(rows,list) and cls._student_list_score(rows) > 0:
                return [r for r in rows if isinstance(r,dict)], key

        best=(-1,[],"")
        queue=[("root",data)]
        while queue:
            path,current=queue.pop(0)
            if isinstance(current,dict):
                for key,child in current.items():
                    child_path=f"{path}.{key}"
                    if isinstance(child,list):
                        score=cls._student_list_score(child)
                        if score > best[0]:
                            best=(score,[r for r in child if isinstance(r,dict)],child_path)
                    if isinstance(child,(dict,list)):
                        queue.append((child_path,child))
            elif isinstance(current,list):
                for idx,child in enumerate(current):
                    if isinstance(child,(dict,list)):
                        queue.append((f"{path}[{idx}]",child))
        return (best[1],best[2]) if best[0] > 0 else ([],"")

    @classmethod
    def _find_header_rows(cls, data: dict[str, Any]) -> tuple[list[dict[str, Any]], str]:
        direct=cls._dict_get_ci(data,"cabeceraNotas","cabecerasNotas","headers","criterios")
        if isinstance(direct,list):
            rows=[r for r in direct if isinstance(r,dict)]
            if rows:
                return rows,"cabeceraNotas"
        best=(-1,[],"")
        queue=[("root",data)]
        while queue:
            path,current=queue.pop(0)
            if isinstance(current,dict):
                for key,child in current.items():
                    child_path=f"{path}.{key}"
                    if isinstance(child,list):
                        rows=[r for r in child if isinstance(r,dict)]
                        score=0
                        for row in rows[:10]:
                            if cls._dict_get_ci(row,"nivelEva","NIVEL_EVA") is not None: score += 5
                            if cls._dict_get_ci(row,"id","idClaseContenido","ID_CLASE_CONTENIDO") is not None: score += 4
                            if cls._dict_get_ci(row,"desc","descripcion","abreviatura") not in (None,""): score += 3
                        if score > best[0]: best=(score,rows,child_path)
                    if isinstance(child,(dict,list)):
                        queue.append((child_path,child))
            elif isinstance(current,list):
                for idx,child in enumerate(current):
                    if isinstance(child,(dict,list)):
                        queue.append((f"{path}[{idx}]",child))
        return (best[1],best[2]) if best[0] > 0 else ([],"")

    @classmethod
    def _student_summary_row(cls, row: dict[str, Any]) -> dict[str, Any]:
        d=cls._dict_get_ci(row,"datos","datosAlumno","alumno","estudiante","infoAlumno")
        if not isinstance(d,dict):
            d=row
        notes=cls._dict_get_ci(row,"notas","notasAlumno","dataNotas","celdas")
        if not isinstance(notes,dict):
            notes={}
        return {
            "idPersona": cls._dict_get_ci(d,"idPersona","ID_PERSONA","personaId"),
            "alucod": cls._dict_get_ci(d,"alucod","ALUCOD","codigoAlumno","codigo"),
            "nomcomp": cls._dict_get_ci(d,"nomcomp","NOMCOMP","nombreCompleto","nombre","alumno"),
            "ngs": cls._dict_get_ci(d,"ngs","NGS"),
            "nemo": cls._dict_get_ci(d,"nemo","NEMO"),
            "numord": cls._dict_get_ci(d,"numord","NUMORD","orden"),
            "estadoAnual": cls._dict_get_ci(d,"estadoAnual","ESTADO_ANUAL","estado"),
            "notas": notes,
        }

    def summarize_gradebook(self, gradebook: dict[str, Any]) -> dict[str, Any]:
        data = self._locate_gradebook_data(gradebook)
        info = self._dict_get_ci(data,"infoClasePeriodo","clasePeriodo","infoRegistro") or {}
        if not isinstance(info,dict):
            info={}

        header_rows, header_source = self._find_header_rows(data)
        headers = []
        for h in header_rows:
            inf = self._dict_get_ci(h,"info") or {}
            if not isinstance(inf,dict): inf={}
            headers.append({
                "id": self._dict_get_ci(h,"id","ID_CONTENIDO","idContenido"),
                "idpadre": self._dict_get_ci(h,"idpadre","ID_CONTENIDO_REF","idContenidoRef"),
                "idClaseContenido": self._dict_get_ci(h,"idClaseContenido","ID_CLASE_CONTENIDO"),
                "desc": self._dict_get_ci(h,"desc","DESCRIPCION","descripcion"),
                "abreviatura": self._dict_get_ci(h,"abreviatura","ABREVIATURA"),
                "programa": self._dict_get_ci(inf,"programa","DESCPROGRAMA"),
                "descripcion": self._dict_get_ci(inf,"descComp","descripcion","DESCRIPCION"),
                "peso": self._dict_get_ci(inf,"peso","PESO"),
                "nivelEva": self._dict_get_ci(h,"nivelEva","NIVEL","nivel"),
                "esAgrupador": self._dict_get_ci(h,"esAgrupador"),
                "mostrarConclusion": self._dict_get_ci(h,"mostrarConclusion"),
                "addConclDescrp": self._dict_get_ci(h,"addConclDescrp"),
            })

        student_rows, student_source = self._find_student_rows(data)
        students=[]
        for row in student_rows:
            item=self._student_summary_row(row)
            # Evita que listas no relacionadas superen el detector heurístico.
            if item.get("idPersona") in (None,"") and item.get("alucod") in (None,"") and item.get("nomcomp") in (None,""):
                continue
            students.append(item)

        # Deduplicación conservadora: la misma persona/alucod puede aparecer dos
        # veces en wrappers auxiliares; se conserva la fila con más celdas de nota.
        dedup: dict[str,dict[str,Any]]={}
        anonymous=[]
        for item in students:
            key=str(item.get("alucod") or item.get("idPersona") or "").strip()
            if not key:
                anonymous.append(item); continue
            prev=dedup.get(key)
            if prev is None or len(item.get("notas") or {}) > len(prev.get("notas") or {}):
                dedup[key]=item
        students=list(dedup.values())+anonymous

        return {
            "class": {
                "idClasePeriodo": self._dict_get_ci(info,"idClasePeriodo","ID_CLASE_PERIODO"),
                "idAmbito": self._dict_get_ci(info,"idAmbito","ID_AMBITO"),
                "idClase": self._dict_get_ci(info,"idClase","ID_CLASE"),
                "idCurso": self._dict_get_ci(info,"idCurso","ID_CURSO"),
                "idContenidoPrin": self._dict_get_ci(info,"idContenidoPrin","idContenido","ID_CONTENIDO"),
                "ano": self._dict_get_ci(info,"ano","ANIO","year"),
                "cursocod": self._dict_get_ci(info,"cursocod","CURSOCOD"),
                "cursonom": self._dict_get_ci(info,"cursonom","CURSONOM"),
                "periodo": self._dict_get_ci(info,"periodo","PERIODO"),
                "nomSalon": self._dict_get_ci(info,"nomSalon","NOMSALON","salon"),
                "arrNivelGrado": self._dict_get_ci(info,"arrNivelGrado","ARR_NIVEL_GRADO","objNG"),
                "arrNGS": self._dict_get_ci(info,"arrNGS","NGS"),
                "arrNemo": self._dict_get_ci(info,"arrNemo","NEMO"),
                "nomProfesor": self._dict_get_ci(info,"nomProfesor","profesor"),
            },
            "permissions": self._dict_get_ci(data,"dataPermisoRegistro","permisos") or {},
            "criteria": headers,
            "students": students,
            "reader_diagnostics": {
                "mode":"recursive-gradebook-v0.8.4",
                "header_source":header_source,
                "header_count":len(headers),
                "student_source":student_source,
                "student_row_count":len(student_rows),
                "student_count":len(students),
            },
        }

    def get_gradebook_summary(self, *, class_period_id: int, root_content_id: int,
                              extra_params: dict[str, Any] | None = None) -> dict[str, Any]:
        return self.summarize_gradebook(self.get_gradebook(class_period_id=class_period_id, root_content_id=root_content_id, extra_params=extra_params))

    def find_students_in_gradebook(self, summary: dict[str, Any], query: str) -> list[dict[str, Any]]:
        q = (query or "").strip().lower()
        out = []
        for s in summary.get("students") or []:
            if not q or q in str(s.get("alucod") or "").lower() or q in str(s.get("nomcomp") or "").lower():
                out.append(s)
        return out

    def find_criteria_in_gradebook(self, summary: dict[str, Any], query: str) -> list[dict[str, Any]]:
        q = (query or "").strip().lower()
        out = []
        for c in summary.get("criteria") or []:
            hay = " ".join(str(c.get(k) or "") for k in ("id","idClaseContenido","desc","abreviatura","programa","descripcion")).lower()
            if not q or q in hay:
                out.append(c)
        return out

    def get_conclusions_batch(self, targets: list[dict[str, Any]]) -> dict[str, Any]:
        results, errors = [], []
        for t in targets:
            try:
                result = self.get_conclusion(person_id=int(t["person_id"]), class_content_id=int(t["class_content_id"]), ng=str(t["ng"]))
                results.append({"target": t, "result": result})
            except Exception as exc:
                errors.append({"target": t, "error": str(exc)})
        return {"results": results, "errors": errors}

    def update_conclusions_batch(self, records: list[dict[str, Any]]) -> dict[str, Any]:
        results, errors = [], []
        for r in records:
            try:
                grade = str(r.get("grade") or "").strip().upper()
                if grade not in {"B", "C"}:
                    raise SieWebError("Conclusión omitida: solo se permite B o C.")
                comment = str(r.get("comment") or "").strip()
                if not comment:
                    raise SieWebError("Conclusión vacía.")
                if len(comment) > 500:
                    raise SieWebError("La conclusión supera 500 caracteres.")
                result = self.update_conclusion(person_id=int(r["person_id"]), class_content_id=int(r["class_content_id"]), comment=comment, comment2=str(r.get("comment2") or ""))
                results.append({"record": r, "result": result})
            except Exception as exc:
                errors.append({"record": r, "error": str(exc)})
        return {"updated": results, "errors": errors, "count_updated": len(results), "count_errors": len(errors)}

    @staticmethod
    def _student_code_aliases(value: Any) -> set[str]:
        """Alias seguros entre correo/USUCOD de alumno y ALUCOD del registro.

        En el directorio de SIEweb el usuario estudiante suele aparecer como
        ``A`` + ALUCOD, mientras que el Registro de Notas usa ALUCOD sin esa A.
        Classroom puede exponer cualquiera de las dos formas como prefijo del
        correo institucional. Solo se aplica esta equivalencia cuando el resto es
        estrictamente numérico; no se hacen aproximaciones por nombres/códigos.
        """
        raw=str(value or "").strip().upper()
        if "@" in raw:
            raw=raw.split("@",1)[0]
        raw=re.sub(r"\s+","",raw)
        if not raw:
            return set()
        out={raw}
        if raw.startswith("A") and raw[1:].isdigit():
            out.add(raw[1:])
        elif raw.isdigit():
            out.add("A"+raw)
        return out

    @classmethod
    def _students_matching_code(cls, summary: dict[str, Any], code: Any) -> list[dict[str, Any]]:
        wanted=cls._student_code_aliases(code)
        if not wanted:
            return []
        matches=[]
        seen=set()
        for student in summary.get("students") or []:
            aliases=cls._student_code_aliases(student.get("alucod"))
            if not (aliases & wanted):
                continue
            identity=(str(student.get("idPersona") or ""),str(student.get("alucod") or ""))
            if identity in seen:
                continue
            seen.add(identity)
            matches.append(student)
        return matches

    @staticmethod
    def _normalize_grade_value(value: Any) -> str:
        """Normaliza una nota para comparar números o niveles sin alterar el payload."""
        text = str(value if value is not None else "").strip().upper().replace(",", ".")
        if not text:
            return ""
        try:
            number = float(text)
            if number.is_integer():
                return str(int(number))
            return ("%f" % number).rstrip("0").rstrip(".")
        except (TypeError, ValueError):
            return text

    @staticmethod
    def _grade_field_values(note_obj: dict[str, Any]) -> dict[str, Any]:
        """Extrae solo campos que parecen representar la nota actual/registrada."""
        current_aliases = {
            "notareg", "notaregistrada", "notaregistro", "notaguardada",
            "notaactual", "nota", "calificacion", "grade", "valornota",
        }
        pending_aliases = {"notanue", "notanueva", "nuevanota"}
        initial_aliases = {"notaini", "notainicial", "notainicio"}

        def normalized_key(key: Any) -> str:
            raw = unicodedata.normalize("NFKD", str(key))
            raw = "".join(ch for ch in raw if not unicodedata.combining(ch))
            return re.sub(r"[^a-z0-9]", "", raw.lower())

        current: dict[str, Any] = {}
        pending: dict[str, Any] = {}
        initial: dict[str, Any] = {}
        for key, value in (note_obj or {}).items():
            nk = normalized_key(key)
            if nk in current_aliases:
                current[str(key)] = value
            elif nk in pending_aliases:
                pending[str(key)] = value
            elif nk in initial_aliases:
                initial[str(key)] = value

        return current or pending or initial

    @staticmethod
    def _note_object_for_header(student: dict[str, Any], header_id: int) -> dict[str, Any] | None:
        notes = student.get("notas") or {}
        if not isinstance(notes, dict):
            return None
        note_obj = notes.get(str(header_id))
        if note_obj is None:
            note_obj = notes.get(header_id)
        return note_obj if isinstance(note_obj, dict) else None

    def build_grade_records(self, summary: dict[str, Any], *, header_id: int,
                            grades_by_student_code: dict[str, str]) -> list[dict[str, Any]]:
        """Construye el payload desde las celdas REALES devueltas por SieWeb.

        v0.7.4: se copia íntegramente `note_obj` y solo se añade/modifica
        `notaNue` más la identidad que ya utilizaba el guardado anterior.
        """
        requested = {
            str(code).strip(): str(note).strip().upper()
            for code, note in (grades_by_student_code or {}).items()
            if str(code).strip()
        }
        if not requested:
            raise SieWebError("No hay calificaciones para construir.")

        criterion = None
        for item in summary.get("criteria") or []:
            if str(item.get("id")) == str(header_id):
                criterion = item
                break

        records: list[dict[str, Any]] = []
        problems: list[dict[str, Any]] = []

        for code, note in requested.items():
            matches = self._students_matching_code(summary, code)
            if not matches:
                problems.append({
                    "alucod": code,
                    "reason": "student_not_found",
                    "aliases": sorted(self._student_code_aliases(code)),
                    "reader": summary.get("reader_diagnostics") or {},
                })
                continue
            if len(matches) != 1:
                problems.append({
                    "alucod": code,
                    "reason": "student_ambiguous",
                    "matches": len(matches),
                })
                continue

            student = matches[0]
            note_obj = self._note_object_for_header(student, header_id)
            if not note_obj:
                problems.append({
                    "alucod": code,
                    "reason": "grade_cell_not_found",
                    "header_id": header_id,
                })
                continue

            record = copy.deepcopy(note_obj)
            record["notaNue"] = note
            record["idPersona"] = student.get("idPersona")
            # El payload debe usar el ALUCOD real del Registro de Notas, no el
            # alias de Classroom (que puede venir como A+ALUCOD).
            record["alucod"] = str(student.get("alucod") or code).strip()
            record["nemo"] = student.get("nemo")

            if record.get("nivelEva") is None and criterion is not None:
                record["nivelEva"] = criterion.get("nivelEva")

            records.append(record)

        if problems:
            raise SieWebError(
                "No se construyó el lote de notas porque el preflight encontró "
                f"{len(problems)} problema(s). No se envió nada. Detalle: "
                + json.dumps(problems, ensure_ascii=False)
            )

        if len(records) != len(requested):
            raise SieWebError(
                "Preflight inconsistente: "
                f"{len(requested)} notas solicitadas y {len(records)} registros preparados. "
                "No se envió nada."
            )
        return records

    def verify_grade_changes(self, summary: dict[str, Any], *, header_id: int,
                             grades_by_student_code: dict[str, str]) -> dict[str, Any]:
        """Comprueba que el gradebook releído contenga las notas solicitadas."""
        verified: list[dict[str, Any]] = []
        failed: list[dict[str, Any]] = []

        for raw_code, raw_expected in (grades_by_student_code or {}).items():
            code = str(raw_code).strip()
            expected = self._normalize_grade_value(raw_expected)
            matches=self._students_matching_code(summary,code)
            if len(matches) != 1:
                failed.append({
                    "alucod": code,
                    "reason": "student_not_found_after_save" if not matches else "student_ambiguous_after_save",
                    "matches": len(matches),
                    "aliases": sorted(self._student_code_aliases(code)),
                })
                continue
            student=matches[0]
            note_obj = self._note_object_for_header(student, header_id)
            if not note_obj:
                failed.append({
                    "alucod": code,
                    "reason": "grade_cell_not_found_after_save",
                    "header_id": header_id,
                })
                continue

            observed_fields = self._grade_field_values(note_obj)
            observed_normalized = {
                key: self._normalize_grade_value(value)
                for key, value in observed_fields.items()
            }
            if expected and expected in observed_normalized.values():
                verified.append({
                    "alucod": code,
                    "expected": expected,
                    "observed": observed_fields,
                })
            else:
                failed.append({
                    "alucod": code,
                    "reason": "grade_not_persisted",
                    "expected": expected,
                    "observed": observed_fields,
                })

        return {
            "ok": not failed and len(verified) == len(grades_by_student_code or {}),
            "requested_count": len(grades_by_student_code or {}),
            "verified_count": len(verified),
            "failed_count": len(failed),
            "verified": verified,
            "failed": failed,
        }



    # ---------- HF v0.8.10: edición nativa segura de abreviaturas ----------
    @staticmethod
    def _criteria_hf10_value(obj, *keys, default=None):
        if not isinstance(obj, dict):
            return default
        lower = {str(k).lower(): v for k, v in obj.items()}
        for key in keys:
            if key in obj:
                return obj[key]
            lk = str(key).lower()
            if lk in lower:
                return lower[lk]
        return default

    @classmethod
    def _criteria_hf10_norm_text(cls, value):
        return " ".join(str(value or "").strip().split())

    @classmethod
    def _criteria_hf10_real_nodes(cls, tree):
        out = []

        def walk(value):
            if isinstance(value, list):
                for item in value:
                    walk(item)
                return
            if not isinstance(value, dict):
                return
            cid = cls._criteria_hf10_value(value, "ID_CONTENIDO", "id")
            ccid = cls._criteria_hf10_value(value, "ID_CLASE_CONTENIDO", "idClaseContenido")
            if cid not in (None, "") and ccid not in (None, ""):
                out.append(value)
            children = cls._criteria_hf10_value(value, "children", default=[])
            if isinstance(children, list):
                walk(children)

        walk(tree)
        return out

    @classmethod
    def _criteria_hf10_find_node(cls, tree, criterion_id):
        target = str(criterion_id)
        matches = []
        for node in cls._criteria_hf10_real_nodes(tree):
            cid = cls._criteria_hf10_value(node, "ID_CONTENIDO", "id")
            if str(cid) == target:
                matches.append(node)
        if len(matches) != 1:
            return None, len(matches)
        return matches[0], 1

    @classmethod
    def _criteria_hf10_extract_tree(cls, payload):
        data = payload
        if isinstance(data, dict) and isinstance(data.get("json"), dict):
            data = data["json"]
        if not isinstance(data, dict):
            raise SieWebError(
                "PROTECCIÓN HF10: dataInicialPesosCriterios no devolvió un objeto JSON utilizable."
            )
        tree = data.get("resCriterios")
        if not isinstance(tree, list) or not tree:
            raise SieWebError(
                "PROTECCIÓN HF10: no encontré resCriterios del modal nativo. No se envió nada."
            )
        return tree

    @classmethod
    def _criteria_hf10_signature(cls, tree):
        rows = []
        for node in cls._criteria_hf10_real_nodes(tree):
            cid = int(cls._criteria_hf10_value(node, "ID_CONTENIDO", "id"))
            ccid = int(cls._criteria_hf10_value(node, "ID_CLASE_CONTENIDO", "idClaseContenido"))
            parent = int(cls._criteria_hf10_value(node, "ID_CONTENIDO_REF", "idpadre", default=0) or 0)
            desc = cls._criteria_hf10_norm_text(
                cls._criteria_hf10_value(node, "DESCRIPCION", "descripcion")
            )
            rows.append((cid, ccid, parent, desc))
        return sorted(rows)

    def _criteria_hf10_replica_from_payload(self, payload, *, class_id=None, class_period_id=None, root_content_id=None, id_ambito=None):
        """Obtiene datosReplica nativo; para una edición local siempre fuerza replicar=False."""
        preflight = getattr(self, "criteria_write_preflight", None)
        if callable(preflight) and all(v not in (None, "") for v in (class_id, class_period_id, root_content_id, id_ambito)):
            try:
                info = preflight(
                    class_id=int(class_id),
                    class_period_id=int(class_period_id),
                    root_content_id=int(root_content_id),
                    id_ambito=int(id_ambito),
                )
                if isinstance(info, dict):
                    native = info.get("native_replica_context")
                    if isinstance(native, dict):
                        replica = dict(native)
                        replica["replicar"] = False
                        return replica
            except Exception:
                # La edición puede continuar con el contexto derivado del mismo
                # payload nativo si esta revisión no expone el preflight como método.
                pass

        data = payload.get("json") if isinstance(payload, dict) and isinstance(payload.get("json"), dict) else payload
        if not isinstance(data, dict):
            data = {}

        # El modal oficial usa nivelReplicaAnual para el límite. Para una edición
        # local siempre se fuerza replicar=False.
        limite = 1
        nra = data.get("nivelReplicaAnual")
        if isinstance(nra, list) and nra and isinstance(nra[0], dict):
            try:
                limite = int(nra[0].get("LIMITE", 1) or 1)
            except Exception:
                limite = 1

        # idCurso / grupocod se obtienen de un nodo real del propio editor.
        nodes = cls._criteria_hf10_real_nodes(data.get("resCriterios") or [])
        id_curso = None
        grupocod = None
        if nodes:
            id_curso = cls._criteria_hf10_value(nodes[0], "ID_CURSO")
            grupocod = cls._criteria_hf10_value(nodes[0], "GRUPOCOD")

        # SIEweb tolera campos adicionales; estos son los mismos que expone el
        # preflight v0.8.4. Si alguno no está disponible se omite, nunca se inventa.
        replica = {"replicar": False, "limiteReplica": limite}
        if id_curso not in (None, ""):
            replica["idCurso"] = id_curso
        if grupocod not in (None, ""):
            replica["grupocod"] = grupocod
        return replica

    def _criteria_hf10_update_abbreviations_verified(
        self,
        *,
        class_id,
        class_period_id,
        root_content_id,
        id_ambito,
        changes,
    ):
        """
        Edita abreviaturas usando el contrato real del modal: envía el árbol
        COMPLETO resCriterios con el mismo ID_CONTENIDO/ID_CLASE_CONTENIDO.
        No envía una hoja suelta, porque HyoClaseContenido/insertar interpreta
        esos registros como altas nuevas o puede ignorar la modificación.
        """
        before_payload = self.get_criteria(
            class_id=int(class_id),
            class_period_id=int(class_period_id),
            root_content_id=int(root_content_id),
            id_ambito=int(id_ambito),
        )
        before_tree = self._criteria_hf10_extract_tree(before_payload)
        before_signature = self._criteria_hf10_signature(before_tree)
        working_tree = copy.deepcopy(before_tree)
        operations = []
        touched = []

        for change in changes:
            cid = int(change["id"])
            before_node, before_count = self._criteria_hf10_find_node(before_tree, cid)
            work_node, work_count = self._criteria_hf10_find_node(working_tree, cid)
            if before_node is None or work_node is None or before_count != 1 or work_count != 1:
                raise SieWebError(
                    f"PROTECCIÓN HF10: criterio {cid} no es único en el árbol nativo. No se envió nada."
                )

            program_id = self._criteria_hf10_value(before_node, "ID_PROGRAMA")
            program_name = self._criteria_hf10_norm_text(
                self._criteria_hf10_value(before_node, "DESCPROGRAMA", "programa")
            ).lower()
            if program_id not in (None, "", 5, "5") and program_name != "desempeño":
                raise SieWebError(
                    f"PROTECCIÓN HF10: criterio {cid} no es un desempeño. No se envió nada."
                )

            parent = int(self._criteria_hf10_value(before_node, "ID_CONTENIDO_REF", "idpadre", default=0) or 0)
            expected_parent = change.get("parent_id")
            if expected_parent not in (None, "") and parent != int(expected_parent):
                raise SieWebError(
                    f"PROTECCIÓN HF10: el padre de {cid} cambió ({parent} != {expected_parent}). No se envió nada."
                )

            current_description = self._criteria_hf10_norm_text(
                self._criteria_hf10_value(before_node, "DESCRIPCION", "descripcion")
            )
            expected_description = self._criteria_hf10_norm_text(change.get("description"))
            if expected_description and current_description != expected_description:
                raise SieWebError(
                    f"PROTECCIÓN HF10: la descripción de {cid} no coincide exactamente. No se envió nada."
                )

            desired = str(change.get("abbreviation") or "").strip()
            if not desired:
                raise SieWebError(f"PROTECCIÓN HF10: abreviatura vacía para {cid}.")
            if len(desired) > 80:
                raise SieWebError(f"PROTECCIÓN HF10: abreviatura demasiado larga para {cid}.")
            if desired.startswith("__"):
                raise SieWebError(
                    "PROTECCIÓN HF10: se bloquean marcadores internos '__...__'."
                )

            current = str(
                self._criteria_hf10_value(before_node, "ABREVIATURA", "abreviatura", default="") or ""
            ).strip()
            if current == desired:
                operations.append({
                    "action": "already-correct",
                    "idContenido": cid,
                    "abbreviation": desired,
                })
                continue

            # Cambia SOLO lo que el usuario pidió. Los campos *_ORIGI conservan
            # el valor que SIEweb leyó originalmente; sirven para que el modal
            # detecte que el registro EXISTENTE fue editado.
            work_node["ABREVIATURA"] = desired
            if "ABREV_ORIGI" not in work_node or work_node.get("ABREV_ORIGI") in (None, ""):
                work_node["ABREV_ORIGI"] = current
            work_node["EDITOREG"] = 1
            work_node["flExiste"] = True

            # Nunca reescribir descripción ni ORIGI al cambiar una abreviatura.
            work_node["DESCRIPCION"] = self._criteria_hf10_value(before_node, "DESCRIPCION")
            if "ORIGI" in before_node:
                work_node["ORIGI"] = before_node.get("ORIGI")

            touched.append(cid)
            operations.append({
                "action": "update-existing-abbreviation",
                "idContenido": cid,
                "from": current,
                "to": desired,
            })

        if not touched:
            return {
                "saved": True,
                "already_present": True,
                "updated_existing": False,
                "operations": operations,
                "protection": "HF10 full native tree; no new criteria; no grade writes",
            }

        # Protección previa al POST: el árbol a enviar debe contener exactamente
        # los mismos IDs, class-content IDs, padres y descripciones.
        working_signature = self._criteria_hf10_signature(working_tree)
        if working_signature != before_signature:
            raise SieWebError(
                "ALERTA HF10: además de la abreviatura cambió la estructura o una descripción. No se envió nada."
            )

        replica = self._criteria_hf10_replica_from_payload(
            before_payload,
            class_id=class_id,
            class_period_id=class_period_id,
            root_content_id=root_content_id,
            id_ambito=id_ambito,
        )
        write = self.upsert_criteria(
            class_id=int(class_id),
            records=working_tree,
            replica=replica,
        )

        after_payload = self.get_criteria(
            class_id=int(class_id),
            class_period_id=int(class_period_id),
            root_content_id=int(root_content_id),
            id_ambito=int(id_ambito),
        )
        after_tree = self._criteria_hf10_extract_tree(after_payload)
        after_signature = self._criteria_hf10_signature(after_tree)
        if after_signature != before_signature:
            raise SieWebError(
                "ALERTA DE INTEGRIDAD HF10: después del guardado cambió un ID, padre o descripción. Se bloquean nuevas operaciones."
            )

        verification = []
        for change in changes:
            cid = int(change["id"])
            node, count = self._criteria_hf10_find_node(after_tree, cid)
            if node is None or count != 1:
                raise SieWebError(
                    f"VERIFICACIÓN HF10 FALLIDA: criterio {cid} dejó de ser único."
                )
            observed = str(
                self._criteria_hf10_value(node, "ABREVIATURA", "abreviatura", default="") or ""
            ).strip()
            desired = str(change.get("abbreviation") or "").strip()
            if observed != desired:
                raise SieWebError(
                    f"VERIFICACIÓN HF10 FALLIDA: abreviatura de {cid}: {observed!r} != {desired!r}."
                )
            verification.append({
                "id": cid,
                "abbreviation": observed,
                "same_id": True,
                "description_unchanged": True,
            })

        return {
            "saved": True,
            "updated_existing": True,
            "write": write,
            "operations": operations,
            "verification": verification,
            "sent_full_native_tree": True,
            "touched_ids": touched,
            "protection": "HF10: full resCriterios tree; same IDs/parents/descriptions; no grade writes; no replication",
        }

    def upsert_criteria_verified(self, *args, **kwargs):
        """
        HF v0.8.10: intercepta SOLO una edición de abreviatura sobre criterios
        existentes. Las altas nuevas y otros cambios siguen usando el flujo legado.
        """
        records = kwargs.get("records")
        expected = kwargs.get("expected")
        required = ("class_id", "class_period_id", "root_content_id", "id_ambito")

        if (
            not isinstance(records, list)
            or not isinstance(expected, list)
            or not records
            or len(records) != len(expected)
            or not all(k in kwargs and kwargs.get(k) not in (None, "") for k in required)
        ):
            return self._upsert_criteria_verified_legacy(*args, **kwargs)

        before_payload = self.get_criteria(
            class_id=int(kwargs["class_id"]),
            class_period_id=int(kwargs["class_period_id"]),
            root_content_id=int(kwargs["root_content_id"]),
            id_ambito=int(kwargs["id_ambito"]),
        )
        before_tree = self._criteria_hf10_extract_tree(before_payload)
        changes = []

        for record, exp in zip(records, expected):
            cid = self._criteria_hf10_value(exp, "id", "ID_CONTENIDO")
            if cid in (None, ""):
                cid = self._criteria_hf10_value(record, "id", "ID_CONTENIDO")
            if cid in (None, ""):
                return self._upsert_criteria_verified_legacy(*args, **kwargs)

            node, count = self._criteria_hf10_find_node(before_tree, cid)
            if node is None or count != 1:
                return self._upsert_criteria_verified_legacy(*args, **kwargs)

            current_description = self._criteria_hf10_norm_text(
                self._criteria_hf10_value(node, "DESCRIPCION", "descripcion")
            )
            desired_description = self._criteria_hf10_norm_text(
                self._criteria_hf10_value(exp, "description", "DESCRIPCION", default=current_description)
            )
            parent = int(self._criteria_hf10_value(node, "ID_CONTENIDO_REF", "idpadre", default=0) or 0)
            desired_parent = self._criteria_hf10_value(exp, "parent_id", "ID_CONTENIDO_REF", default=parent)
            desired_abbreviation = self._criteria_hf10_value(exp, "abbreviation", "ABREVIATURA")
            if desired_abbreviation in (None, ""):
                desired_abbreviation = self._criteria_hf10_value(record, "abbreviation", "ABREVIATURA")

            # Si intentan cambiar descripción/padre o crear un registro, no lo
            # intercepta HF10: queda en manos del flujo verificado legado.
            if (
                desired_description != current_description
                or int(desired_parent) != parent
                or desired_abbreviation in (None, "")
            ):
                return self._upsert_criteria_verified_legacy(*args, **kwargs)

            if desired_description.startswith("__"):
                raise SieWebError(
                    "PROTECCIÓN HF10: no se permiten descripciones internas '__...__' para forzar una actualización."
                )

            changes.append({
                "id": int(cid),
                "parent_id": parent,
                "description": current_description,
                "abbreviation": str(desired_abbreviation).strip(),
            })

        return self._criteria_hf10_update_abbreviations_verified(
            class_id=kwargs["class_id"],
            class_period_id=kwargs["class_period_id"],
            root_content_id=kwargs["root_content_id"],
            id_ambito=kwargs["id_ambito"],
            changes=changes,
        )
    def save_grades_verified(
        self,
        *,
        year: str,
        course_code: str,
        class_period_id: int,
        root_content_id: int,
        period: int,
        section_ng: list[dict[str, str]],
        header_id: int,
        grades_by_student_code: dict[str, str],
        class_name: str | None = None,
        extra_params: dict[str, Any] | None = None,
        notify: bool = True,
        verification_attempts: int = 3,
        protect_achievement_level: bool = True,
        performance_level: int = 3,
        allow_achievement_level: bool = False,
    ) -> dict[str, Any]:
        """Guarda notas con preflight y verificación posterior obligatoria.

        Por defecto conserva el flujo histórico de desempeños nivelEva=3. Nivel de
        logro solo se habilita cuando ``allow_achievement_level`` es True y el
        llamador, además, desactiva explícitamente la protección histórica. Esa
        vía acepta exclusivamente una cabecera Competencia nivelEva=1 y A/B/C.
        """
        if type(allow_achievement_level) is not bool:
            raise SieWebError("allow_achievement_level debe ser booleano explícito.")
        achievement_mode = allow_achievement_level is True
        if achievement_mode:
            if protect_achievement_level is not False or int(performance_level) != 1:
                raise SieWebError(
                    "PROTECCIÓN NIVEL DE LOGRO HF12: el modo explícito requiere "
                    "protect_achievement_level=False y performance_level=1. No se envió nada."
                )
        else:
            if protect_achievement_level is not True or int(performance_level) != 3:
                raise SieWebError(
                    "PROTECCIÓN DE NOTAS: sin allow_achievement_level=true, "
                    "save_grades_verified solo admite desempeños nivelEva=3. No se envió nada."
                )

        requested = {
            str(code).strip(): str(grade).strip().upper()
            for code, grade in (grades_by_student_code or {}).items()
            if str(code).strip()
        }
        if not requested:
            raise SieWebError("No hay calificaciones para guardar.")
        if achievement_mode:
            invalid = {code: grade for code, grade in requested.items() if grade not in {"A", "B", "C"}}
            if invalid:
                raise SieWebError(
                    "PROTECCIÓN NIVEL DE LOGRO HF12: solo se permiten A, B o C. No se envió nada: "
                    + json.dumps(invalid, ensure_ascii=False)
                )

        before = self.get_gradebook_summary(
            class_period_id=class_period_id,
            root_content_id=root_content_id,
            extra_params=extra_params,
        )
        expected_level = 1 if achievement_mode else 3
        target = self.assert_performance_target(
            before, header_id=header_id, performance_level=expected_level
        )

        if achievement_mode:
            program = str(target.get("programa") or "").strip().casefold()
            parent_id = target.get("idpadre")
            class_content_id = target.get("idClaseContenido")
            is_grouper = target.get("esAgrupador")
            if program != "competencia":
                raise SieWebError(
                    f"PROTECCIÓN NIVEL DE LOGRO HF12: la cabecera {header_id} no es Competencia "
                    f"(programa={target.get('programa')!r}). No se envió nada."
                )
            if str(parent_id) != str(root_content_id):
                raise SieWebError(
                    f"PROTECCIÓN NIVEL DE LOGRO HF12: la cabecera {header_id} no pertenece al "
                    f"contenido raíz {root_content_id}. No se envió nada."
                )
            if class_content_id in (None, "", 0, "0"):
                raise SieWebError(
                    f"PROTECCIÓN NIVEL DE LOGRO HF12: la Competencia {header_id} no tiene "
                    "idClaseContenido persistido. No se envió nada."
                )
            if is_grouper is True or str(is_grouper).strip().lower() in {"1", "true", "si", "sí"}:
                raise SieWebError(
                    f"PROTECCIÓN NIVEL DE LOGRO HF12: la cabecera {header_id} es agrupadora, "
                    "no una celda final de Nivel de logro. No se envió nada."
                )

        native_obj_ng = self.resolve_grade_write_scope(before, section_ng)
        records = self.build_grade_records(
            before,
            header_id=header_id,
            grades_by_student_code=requested,
        )
        if len(records) != len(requested):
            raise SieWebError(
                f"Preflight incompleto: se solicitaron {len(requested)} celdas y se prepararon "
                f"{len(records)}. No se envió nada."
            )

        if achievement_mode:
            expected_ccid = str(target.get("idClaseContenido"))
            for rec in records:
                rec_level = self._dict_get_ci(rec, "nivelEva", "NIVEL", "nivel")
                rec_header = self._dict_get_ci(rec, "idCabecera", "ID_CABECERA", "header_id")
                rec_grade = str(self._dict_get_ci(rec, "notaNue", "NOTANUE", "nota", "grade") or "").strip().upper()
                rec_note_id = self._dict_get_ci(rec, "idNota", "ID_NOTA")
                if str(rec_level) != "1":
                    raise SieWebError(
                        f"PROTECCIÓN NIVEL DE LOGRO HF12: registro con nivelEva={rec_level!r}; no se envió nada."
                    )
                if str(rec_header) != str(header_id):
                    raise SieWebError(
                        f"PROTECCIÓN NIVEL DE LOGRO HF12: registro con cabecera {rec_header!r} distinta "
                        f"de {header_id}. No se envió nada."
                    )
                if rec_grade not in {"A", "B", "C"}:
                    raise SieWebError(
                        f"PROTECCIÓN NIVEL DE LOGRO HF12: nota {rec_grade!r} inválida; no se envió nada."
                    )
                if str(rec_note_id) != expected_ccid:
                    raise SieWebError(
                        f"PROTECCIÓN NIVEL DE LOGRO HF12: idNota {rec_note_id!r} no coincide con "
                        f"idClaseContenido {expected_ccid}. No se envió nada."
                    )

        def snapshot_non_target(summary: dict[str, Any]) -> dict[str, dict[str, Any]]:
            by_code = {
                str(student.get("alucod") or "").strip(): student
                for student in (summary.get("students") or [])
                if str(student.get("alucod") or "").strip()
            }
            snap: dict[str, dict[str, Any]] = {}
            for code in requested:
                student = by_code.get(code)
                if student is None:
                    raise SieWebError(
                        f"PROTECCIÓN HF12: el alumno {code} desapareció de la relectura; verificación abortada."
                    )
                notes = student.get("notas") or {}
                if not isinstance(notes, dict):
                    raise SieWebError(
                        f"PROTECCIÓN HF12: notas inválidas para {code}; verificación abortada."
                    )
                for note_key, note in notes.items():
                    if not isinstance(note, dict):
                        continue
                    note_header = self._dict_get_ci(note, "idCabecera", "ID_CABECERA")
                    if note_header in (None, ""):
                        note_header = note_key
                    if str(note_header) == str(header_id):
                        continue
                    snap[f"{code}:{note_header}"] = {
                        "idNota": self._dict_get_ci(note, "idNota", "ID_NOTA"),
                        "notaIni": self._dict_get_ci(note, "notaIni", "NOTAINI"),
                        "notaReg": self._dict_get_ci(note, "notaReg", "NOTAREG"),
                        "notaPeAnt": self._dict_get_ci(note, "notaPeAnt", "NOTAPEANT"),
                        "nivelEva": self._dict_get_ci(note, "nivelEva", "NIVEL", "nivel"),
                        "llave": self._dict_get_ci(note, "llave", "LLAVE"),
                    }
            return snap

        non_target_before = snapshot_non_target(before) if achievement_mode else {}

        update_result = self.update_grades(
            year=year,
            course_code=course_code,
            class_period_id=class_period_id,
            period=period,
            section_ng=native_obj_ng,
            records=records,
            class_name=class_name,
            notify=notify,
        )

        attempts: list[dict[str, Any]] = []
        verification: dict[str, Any] = {
            "ok": False,
            "requested_count": len(requested),
            "verified_count": 0,
            "failed_count": len(requested),
            "verified": [],
            "failed": [],
        }
        non_target_verification: dict[str, Any] = {
            "checked": achievement_mode,
            "ok": not achievement_mode,
            "verified_count": 0,
            "changed": [],
        }
        max_attempts = max(1, min(int(verification_attempts or 1), 5))
        for attempt in range(1, max_attempts + 1):
            after = self.get_gradebook_summary(
                class_period_id=class_period_id,
                root_content_id=root_content_id,
                extra_params=extra_params,
            )
            verification = self.verify_grade_changes(
                after,
                header_id=header_id,
                grades_by_student_code=requested,
            )
            attempts.append({
                "attempt": attempt,
                "ok": verification["ok"],
                "verified_count": verification["verified_count"],
                "failed_count": verification["failed_count"],
            })
            if verification["ok"]:
                if achievement_mode:
                    non_target_after = snapshot_non_target(after)
                    all_keys = sorted(set(non_target_before) | set(non_target_after))
                    changed = [
                        {
                            "cell": key,
                            "before": non_target_before.get(key),
                            "after": non_target_after.get(key),
                        }
                        for key in all_keys
                        if non_target_before.get(key) != non_target_after.get(key)
                    ]
                    non_target_verification = {
                        "checked": True,
                        "ok": not changed,
                        "verified_count": len(all_keys) - len(changed),
                        "changed": changed,
                    }
                    if changed:
                        raise SieWebError(
                            "PROTECCIÓN HF12: la relectura detectó cambios fuera de la cabecera autorizada. "
                            "Se detiene el flujo: " + json.dumps(changed[:20], ensure_ascii=False)
                        )
                break
            if attempt < max_attempts:
                time.sleep(0.4 * attempt)

        if not verification["ok"]:
            raise SieWebError(
                "SieWeb respondió a la actualización, pero la relectura no confirmó todas las notas. "
                "No se declarará éxito. Verificación: "
                + json.dumps(verification, ensure_ascii=False)
            )

        return {
            "saved": True,
            "mode": "achievement_level" if achievement_mode else "performance_level_3",
            "target": target,
            "requested_count": len(requested),
            "prepared_count": len(records),
            "update": update_result,
            "verification": verification,
            "verification_attempts": attempts,
            "non_target_verification": non_target_verification,
            "objNG": native_obj_ng,
        }

    def save_grades_multi_verified(
        self,
        *,
        year: str,
        course_code: str,
        class_period_id: int,
        root_content_id: int,
        period: int,
        section_ng: list[Any],
        header_ids: list[int],
        grades_by_student_code: dict[str, str],
        class_name: str | None = None,
        extra_params: dict[str, Any] | None = None,
        notify: bool = True,
        verification_attempts: int = 3,
        performance_level: int = 3,
    ) -> dict[str, Any]:
        """Guarda varios desempeños en un solo PUT y verifica cada celda."""
        headers = [int(value) for value in header_ids]
        if not headers or len(set(headers)) != len(headers):
            raise SieWebError("header_ids debe contener desempeños únicos y no estar vacío.")
        requested = {
            str(code).strip(): str(grade).strip().upper()
            for code, grade in (grades_by_student_code or {}).items()
            if str(code).strip()
        }
        if not requested:
            raise SieWebError("No hay calificaciones para guardar.")
        invalid_grades = {
            code: grade for code, grade in requested.items()
            if grade not in {"A", "B", "C"}
        }
        if invalid_grades:
            raise SieWebError(
                "El lote cualitativo multi-desempeño solo admite A, B o C. No se envió nada: "
                + json.dumps(invalid_grades, ensure_ascii=False)
            )

        before = self.get_gradebook_summary(
            class_period_id=class_period_id,
            root_content_id=root_content_id,
            extra_params=extra_params,
        )
        targets = [
            self.assert_performance_target(
                before, header_id=header_id, performance_level=performance_level
            )
            for header_id in headers
        ]
        native_obj_ng = self.resolve_grade_write_scope(before, section_ng)

        records: list[dict[str, Any]] = []
        records_by_header: dict[str, int] = {}
        for header_id in headers:
            prepared = self.build_grade_records(
                before,
                header_id=header_id,
                grades_by_student_code=requested,
            )
            if len(prepared) != len(requested):
                raise SieWebError(
                    f"Preflight incompleto para el desempeño {header_id}; no se envió nada."
                )
            records.extend(prepared)
            records_by_header[str(header_id)] = len(prepared)

        expected_total = len(headers) * len(requested)
        if len(records) != expected_total:
            raise SieWebError(
                f"Preflight inconsistente: se esperaban {expected_total} celdas y se prepararon {len(records)}."
            )

        update_result = self.update_grades(
            year=year,
            course_code=course_code,
            class_period_id=class_period_id,
            period=period,
            section_ng=native_obj_ng,
            records=records,
            class_name=class_name,
            notify=notify,
        )

        max_attempts = max(1, min(int(verification_attempts or 1), 5))
        attempts: list[dict[str, Any]] = []
        per_header: dict[str, dict[str, Any]] = {}
        all_ok = False
        for attempt in range(1, max_attempts + 1):
            after = self.get_gradebook_summary(
                class_period_id=class_period_id,
                root_content_id=root_content_id,
                extra_params=extra_params,
            )
            per_header = {
                str(header_id): self.verify_grade_changes(
                    after,
                    header_id=header_id,
                    grades_by_student_code=requested,
                )
                for header_id in headers
            }
            all_ok = all(item.get("ok") is True for item in per_header.values())
            attempts.append({
                "attempt": attempt,
                "ok": all_ok,
                "verified_cells": sum(int(item.get("verified_count") or 0) for item in per_header.values()),
                "expected_cells": expected_total,
            })
            if all_ok:
                break
            if attempt < max_attempts:
                time.sleep(0.4 * attempt)

        if not all_ok:
            raise SieWebError(
                "SieWeb respondió al lote único, pero la relectura no confirmó todas las celdas. "
                + json.dumps(per_header, ensure_ascii=False)
            )

        return {
            "saved": True,
            "single_update_request": True,
            "header_ids": headers,
            "targets": targets,
            "student_count": len(requested),
            "prepared_count": len(records),
            "records_by_header": records_by_header,
            "update": update_result,
            "verification": {
                "ok": True,
                "expected_cells": expected_total,
                "verified_cells": expected_total,
                "per_header": per_header,
                "attempts": attempts,
            },
        }
