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
                "User-Agent": "Mozilla/5.0 SieRoom-SRC/0.7.10",
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
            "objInfoRegIndividual[alucod]": False,
            "chkNotFRET": False,
        }
        params.update(extra_params or {})
        return self._request(
            "GET", "/lms/api/HyoClasePeriodo/obtRegistroNotas", params=params
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
        # El editor usa NIVEL=1/2/3 para Competencia/Capacidad/Desempeño.
        for key in ("nivelEva", "nivel", "NIVEL", "NIVEL_EVA", "nivelEvaluacion"):
            if key in row:
                return row.get(key)
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
        """Construye una fila nueva con las mismas reglas del guardado jerárquico v0.7.10."""
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
    def normalize_replica_for_criteria_write(replica: Any) -> list[Any]:
        """Normaliza datosReplica al contrato seguro observado: una lista de destinos.

        Este complemento replica 2.º A/2.º B haciendo una escritura independiente por
        sección, por lo que la ausencia de réplica se envía como ``[]``. Un dict vacío
        ({}) era otro desajuste de tipo presente hasta v0.7.9 y podía contribuir a e0006.
        """
        if replica in (None, {}, []):
            return []
        if isinstance(replica, list):
            return copy.deepcopy(replica)
        raise SieWebError(
            "datosReplica debe ser una lista. La réplica entre secciones se realiza de forma "
            "independiente para no reutilizar IDs internos; no se envió nada."
        )

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
        """Convierte un desempeño persistido clonado en una fila NUEVA como la UI real.

        El editor distingue altas mediante IDs nulos + flExiste=false, EDITOREG=1 y una LLAVE/INDICE
        nuevos. Reutilizar IDs=0, flExiste=true, EDITOREG=0 o la LLAVE del hermano puede provocar e0006/no-op.
        """
        out=copy.deepcopy(newrow)
        # Las filas nuevas observadas en resCriterios usan null, no 0.
        for key in ("id","ID","idClaseContenido","ID_CLASE_CONTENIDO",
                    "idContenido","ID_CONTENIDO","idCriterio","ID_CRITERIO"):
            if key in out:
                out[key]=None
        # Padre real del desempeño = ID_CONTENIDO de la capacidad.
        self._set_existing_alias(out,("ID_CONTENIDO_REF","idContenidoRef","id_contenido_ref",
                                      "idpadre","idPadre","ID_PADRE","idContenidoPadre",
                                      "idClaseContenidoPadre"),self._criterion_content_id(parent),"ID_CONTENIDO_REF")
        self._set_existing_alias(out,("DESCRIPCION","descripcion","desc","descComp","DESC","nombre","nom"),description,"DESCRIPCION")
        self._set_existing_alias(out,("NIVEL","nivelEva","nivel","NIVEL_EVA","nivelEvaluacion"),level,"NIVEL")

        for key in ("INDICE","indice"):
            if key in out: out[key]=index
        if "INDICE" not in out and "indice" not in out: out["INDICE"]=index
        for key in ("INDICE_ORIGI","indiceOrigi","indice_origi"):
            if key in out: out[key]=index
        if "INDICE_ORIGI" not in out: out["INDICE_ORIGI"]=index
        for key in ("ORDEN","orden"):
            if key in out: out[key]=index
        if "ORDEN" not in out and "orden" not in out: out["ORDEN"]=index

        program_id=out.get("ID_PROGRAMA") or out.get("idPrograma") or 5
        parent_key=str(parent.get("LLAVE") or parent.get("llave") or "").strip()
        if parent_key:
            if "LLAVE" in out or "llave" not in out:
                out["LLAVE"]=f"{program_id}-{index}_{parent_key}"
            else:
                out["llave"]=f"{program_id}-{index}_{parent_key}"

        # Marcadores que usa el editor para distinguir alta de fila ya persistida.
        if "flExiste" in out or "FLEXISTE" not in out:
            out["flExiste"]=False
        else:
            out["FLEXISTE"]=False
        # La fila nueva ya contiene cambios (descripción/peso). flExiste=false decide INSERT;
        # EDITOREG=1 indica al guardado por lotes que debe procesarla. Las plazas vacías
        # sin tocar llegan con EDITOREG=0 y el backend las ignora.
        if "EDITOREG" in out:
            out["EDITOREG"]=1
        elif "editoreg" in out:
            out["editoreg"]=1
        else:
            out["EDITOREG"]=1
        if "ORIGI" in out: out["ORIGI"]=""
        if "PESO_ORIGI" in out: out["PESO_ORIGI"]=""
        if "ABREV_ORIGI" in out: out["ABREV_ORIGI"]=None
        if "TRAD_ORIGI" in out: out["TRAD_ORIGI"]=None
        out["children"]=[]

        # Campos pedagógicos opcionales solicitados por el llamador. Se aceptan alias
        # reales, pero nunca identidades ni marcadores internos de persistencia.
        forbidden={"id","ID","idClaseContenido","ID_CLASE_CONTENIDO","idContenido","ID_CONTENIDO",
                   "idCriterio","ID_CRITERIO","LLAVE","llave","flExiste","FLEXISTE","EDITOREG",
                   "INDICE","INDICE_ORIGI","ORDEN","idpadre","idPadre","ID_PADRE","ID_CONTENIDO_REF",
                   "nivelEva","nivel","NIVEL","NIVEL_EVA"}
        for key,value in requested.items():
            if key in forbidden:
                continue
            if key in out:
                out[key]=copy.deepcopy(value)
            elif self._canon_text(key) in {"abreviatura","abrev"}:
                self._set_existing_alias(out,("ABREVIATURA","abreviatura"),value,"ABREVIATURA")
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

    def upsert_criteria_verified(self, *, class_id: int, class_period_id: int,
                                 root_content_id: int, id_ambito: int,
                                 records: list[dict[str, Any]],
                                 replica: dict[str, Any] | list[Any] | None,
                                 expected: list[dict[str, Any]],
                                 extra_params: dict[str, Any] | None = None,
                                 verification_attempts: int = 3) -> dict[str, Any]:
        """Guarda el MODELO COMPLETO del editor y exige persistencia real.

        v0.7.10 conserva la protección de contexto de v0.7.9 y corrige el árbol real resCriterios: el ``idAmbito``
        usado por el preflight debe viajar también a TODAS las lecturas que rodean el
        POST real. Antes, el preflight podía leer 2.º B correctamente pero el guardado
        releía silenciosamente el ámbito por defecto (518/2.º A), mezclando ``idClase``
        de una sección con filas/replica de otra y provocando ``e0006``.
        """
        try:
            id_ambito = int(id_ambito)
        except (TypeError, ValueError) as exc:
            raise SieWebError("id_ambito es obligatorio para guardar desempeños; no se usará un ámbito por defecto.") from exc
        if id_ambito <= 0:
            raise SieWebError("id_ambito debe ser positivo para guardar desempeños; no se usará un ámbito por defecto.")

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
        merged=self.merge_requested_criteria_into_editor_rows(model["rows"],records,expected)
        actual_replica=self.normalize_replica_for_criteria_write(replica)
        payload_diagnostics=self.validate_criteria_tree_for_write(
            merged["rows"],class_id=class_id,class_period_id=class_period_id
        )
        if not payload_diagnostics["ok"]:
            raise SieWebError(
                "PROTECCIÓN ESTRUCTURAL SIEWEB: el árbol a guardar no cumple las invariantes "
                "de resCriterios; se bloqueó el POST: "+
                json.dumps(payload_diagnostics["errors"],ensure_ascii=False)
            )
        payload={"registros":merged["rows"],"idClase":class_id,"datosReplica":actual_replica}

        # Guardado único. No hacemos reintentos de escritura a ciegas: un timeout o
        # error ambiguo se verifica primero para evitar duplicados.
        result=self._request("POST","/lms/api/HyoClaseContenido/insertar",json=payload)
        body=(result.get("json") or {}) if isinstance(result,dict) else {}
        provider_state=body.get("estado")
        provider_code=body.get("codigo") or body.get("code") or body.get("error") or body.get("mensaje")
        if provider_state != 1:
            raise SieWebError(
                "SIEweb rechazó el guardado de criterios "
                f"(estado={provider_state!r}, codigo={provider_code!r}). No se escribirán notas. "
                "Diagnóstico del payload: "+json.dumps({
                    "root_count":payload_diagnostics["root_count"],
                    "node_count":payload_diagnostics["node_count"],
                    "new_nodes":payload_diagnostics["new_nodes"],
                    "edited_nodes":payload_diagnostics["edited_nodes"],
                    "datosReplicaType":type(actual_replica).__name__,
                },ensure_ascii=False)
            )

        attempts=[]; final=[]
        max_attempts=max(1,min(int(verification_attempts),5))
        for attempt in range(1,max_attempts+1):
            raw_after=self.get_criteria(class_id=class_id,class_period_id=class_period_id,
                                        root_content_id=root_content_id,id_ambito=id_ambito,
                                        extra_params=extra_params)
            editor_after=self.extract_criteria_editor_model(raw_after)
            after=self.get_gradebook_summary(class_period_id=class_period_id,root_content_id=root_content_id,
                                             extra_params=extra_params)
            checks=[]; ok=True
            for e in expected:
                found_editor=[row for _,row in self._walk_criterion_tree(editor_after["rows"]) if
                              self._raw_row_matches(row,description=str(e["description"]),
                                                    parent_id=e.get("parent_id"),level=e.get("level",3))]
                found_gradebook=self.find_exact_criterion(after,description=str(e["description"]),
                                                          parent_id=e.get("parent_id"),level=e.get("level",3))
                check={"expected":e,"editor_count":len(found_editor),"gradebook_count":len(found_gradebook)}
                checks.append(check)
                # La persistencia debe aparecer en AMBAS fuentes; esto elimina el
                # "estado:1" falso que v0.7.7 todavía podía aceptar.
                if len(found_editor)!=1 or len(found_gradebook)!=1:
                    ok=False
            attempts.append({"attempt":attempt,"ok":ok,"checks":checks})
            final=checks
            if ok: break
            if attempt<max_attempts: time.sleep(0.6*attempt)
        if not attempts[-1]["ok"]:
            raise SieWebError(
                "FALSO ÉXITO SIEWEB: insertar devolvió estado=1, pero el desempeño no quedó "
                "persistido simultáneamente en el editor y el registro de notas. "
                "Se detuvo el flujo y NO se escribirán calificaciones. Verificación: "+
                json.dumps(final,ensure_ascii=False)
            )
        return {
            "saved":True,
            "update":result,
            "verification":final,
            "attempts":attempts,
            "editor_model_path":model["path"],
            "editor_model_score":model["score"],
            "operations":merged["operations"],
            "payload_diagnostics":payload_diagnostics,
            "sent_record_count":len(merged["rows"]),
            "sent_node_count":sum(1 for _ in self._walk_criterion_tree(merged["rows"])),
            "idAmbito":id_ambito,
            "context_guard":"exact-ambito-bound-tree-v0.7.10",
            "mode":"hierarchical-rescriterios-v0.7.10",
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
    @staticmethod
    def _unwrap(payload: dict[str, Any]) -> dict[str, Any]:
        return (payload.get("json") or payload) if isinstance(payload, dict) else {}

    def summarize_gradebook(self, gradebook: dict[str, Any]) -> dict[str, Any]:
        data = self._unwrap(gradebook)
        info = data.get("infoClasePeriodo") or {}
        headers = []
        for h in data.get("cabeceraNotas") or []:
            inf = h.get("info") or {}
            headers.append({
                "id": h.get("id"),
                "idpadre": h.get("idpadre"),
                "idClaseContenido": h.get("idClaseContenido"),
                "desc": h.get("desc"),
                "abreviatura": h.get("abreviatura"),
                "programa": inf.get("programa"),
                "descripcion": inf.get("descComp"),
                "peso": inf.get("peso"),
                "nivelEva": h.get("nivelEva"),
                "esAgrupador": h.get("esAgrupador"),
                "mostrarConclusion": h.get("mostrarConclusion"),
                "addConclDescrp": h.get("addConclDescrp"),
            })
        students = []
        for row in data.get("dataAlumno") or []:
            d = row.get("datos") or {}
            notes = row.get("notas") or {}
            students.append({
                "idPersona": d.get("idPersona"), "alucod": d.get("alucod"),
                "nomcomp": d.get("nomcomp"), "ngs": d.get("ngs"), "nemo": d.get("nemo"),
                "numord": d.get("numord"), "estadoAnual": d.get("estadoAnual"),
                "notas": notes,
            })
        return {
            "class": {
                "idClasePeriodo": info.get("idClasePeriodo"), "idClase": info.get("idClase"),
                "idCurso": info.get("idCurso"), "idContenidoPrin": info.get("idContenidoPrin"),
                "ano": info.get("ano"), "cursocod": info.get("cursocod"), "cursonom": info.get("cursonom"),
                "periodo": info.get("periodo"), "nomSalon": info.get("nomSalon"), "arrNGS": info.get("arrNGS"),
                "arrNemo": info.get("arrNemo"), "nomProfesor": info.get("nomProfesor"),
            },
            "permissions": data.get("dataPermisoRegistro") or {},
            "criteria": headers,
            "students": students,
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

        by_code: dict[str, list[dict[str, Any]]] = {}
        for student in summary.get("students") or []:
            code = str(student.get("alucod") or "").strip()
            if code:
                by_code.setdefault(code, []).append(student)

        criterion = None
        for item in summary.get("criteria") or []:
            if str(item.get("id")) == str(header_id):
                criterion = item
                break

        records: list[dict[str, Any]] = []
        problems: list[dict[str, Any]] = []

        for code, note in requested.items():
            matches = by_code.get(code) or []
            if not matches:
                problems.append({"alucod": code, "reason": "student_not_found"})
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
            record["alucod"] = code
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
        by_code = {
            str(s.get("alucod") or "").strip(): s
            for s in summary.get("students") or []
            if str(s.get("alucod") or "").strip()
        }
        verified: list[dict[str, Any]] = []
        failed: list[dict[str, Any]] = []

        for raw_code, raw_expected in (grades_by_student_code or {}).items():
            code = str(raw_code).strip()
            expected = self._normalize_grade_value(raw_expected)
            student = by_code.get(code)
            if not student:
                failed.append({"alucod": code, "reason": "student_not_found_after_save"})
                continue
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
        protect_achievement_level: bool = False,
        performance_level: int = 3,
    ) -> dict[str, Any]:
        """Guarda notas con preflight y verificación posterior obligatoria."""
        before = self.get_gradebook_summary(
            class_period_id=class_period_id,
            root_content_id=root_content_id,
            extra_params=extra_params,
        )
        if protect_achievement_level:
            self.assert_performance_target(before, header_id=header_id, performance_level=performance_level)
        records = self.build_grade_records(
            before,
            header_id=header_id,
            grades_by_student_code=grades_by_student_code,
        )

        update_result = self.update_grades(
            year=year,
            course_code=course_code,
            class_period_id=class_period_id,
            period=period,
            section_ng=section_ng,
            records=records,
            class_name=class_name,
            notify=notify,
        )

        attempts: list[dict[str, Any]] = []
        verification: dict[str, Any] = {
            "ok": False,
            "requested_count": len(grades_by_student_code or {}),
            "verified_count": 0,
            "failed_count": len(grades_by_student_code or {}),
            "verified": [],
            "failed": [],
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
                grades_by_student_code=grades_by_student_code,
            )
            attempts.append({
                "attempt": attempt,
                "ok": verification["ok"],
                "verified_count": verification["verified_count"],
                "failed_count": verification["failed_count"],
            })
            if verification["ok"]:
                break
            if attempt < max_attempts:
                time.sleep(0.4 * attempt)

        if not verification["ok"]:
            raise SieWebError(
                "SieWeb respondió a la actualización, pero la relectura no confirmó "
                "todas las notas. No se declarará éxito. Verificación: "
                + json.dumps(verification, ensure_ascii=False)
            )

        return {
            "saved": True,
            "requested_count": len(grades_by_student_code or {}),
            "prepared_count": len(records),
            "update": update_result,
            "verification": verification,
            "verification_attempts": attempts,
        }
