from __future__ import annotations

import difflib
import html as html_lib
import json
import re
import unicodedata
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
                "User-Agent": "Mozilla/5.0 SieRoom-SRC/0.7.0",
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

        # Una misma promoción con varias secciones: "5A y B", "2 A, B".
        # El segundo literal no repite el grado, así que se hereda solo dentro del
        # mismo fragmento explícito para evitar adivinar secciones.
        for grade, letters_chunk in re.findall(
            r"(?:\bS)?\s*([1-6])\s*[-.]?\s*([A-Z](?:\s*(?:Y|,|/)\s*[A-Z])+)\b",
            raw,
        ):
            for letter in re.split(r"\s*(?:Y|,|/)\s*", letters_chunk):
                if not re.fullmatch(r"[A-Z]", letter):
                    continue
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
            for letters_chunk in re.findall(
                rf"\b{word}(?:\s+(?:ANO|GRADO|SECUNDARIA))?\s+([A-Z](?:\s*(?:Y|,|/)\s*[A-Z])+)\b",
                raw,
            ):
                for letter in re.split(r"\s*(?:Y|,|/)\s*", letters_chunk):
                    if not re.fullmatch(r"[A-Z]", letter):
                        continue
                    code = f"S{grade}{letter}"
                    if code not in found:
                        found.append(code)
        return found

    def resolve_student_recipients_by_sections(self, sections: list[str]) -> dict[str, Any]:
        """Resuelve los USUCOD de alumnos de una o más secciones usando NGS.

        El directorio de Mensajería identifica alumnos con TIPCOD=005. Para un
        envío grupal no se intenta buscar literalmente frases como "estudiantes
        de 5A y 5B": se filtra el directorio real por NGS y se devuelven los
        USUCOD existentes, sin inventar destinatarios.
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

        students_by_code: dict[str, dict[str, Any]] = {}
        for row in rows:
            if str(row.get("TIPCOD") or "") != "005":
                continue
            code = str(row.get("USUCOD") or "").strip()
            if not code:
                continue
            row_ngs = self._normalize_text(row.get("NGS") or "").replace(" ", "")
            if row_ngs not in wanted:
                continue
            previous = students_by_code.get(code)
            if previous is None or (row.get("NGS") and not previous.get("NGS")):
                students_by_code[code] = dict(row)

        resolved = sorted(
            [
                {
                    "USUCOD": str(row.get("USUCOD") or "").strip(),
                    "USUNOM": row.get("USUNOM"),
                    "TIPCOD": "005",
                    "NGS": row.get("NGS"),
                }
                for row in students_by_code.values()
            ],
            key=lambda r: (
                self._normalize_text(r.get("NGS") or ""),
                self._normalize_text(r.get("USUNOM") or ""),
            ),
        )
        recipient_codes = [r["USUCOD"] for r in resolved if r.get("USUCOD")]

        per_section: dict[str, dict[str, int]] = {}
        for section in wanted:
            count = sum(
                1
                for row in resolved
                if self._normalize_text(row.get("NGS") or "").replace(" ", "") == section
            )
            per_section[section] = {"students": count, "resolved": count}

        missing_sections = [
            section for section in wanted if per_section.get(section, {}).get("students", 0) == 0
        ]
        return {
            "resolver": "messaging_directory_ngs_to_students",
            "requires_class_context": False,
            "directory_endpoint": "/lms/api/HyoUsuario/obtListaUsuariosIntranet?isMensajeria=true",
            "sections": wanted,
            "recipient_codes": recipient_codes,
            "recipient_count": len(recipient_codes),
            "students_found": len(resolved),
            "resolved": resolved,
            "missing_sections": missing_sections,
            "complete": bool(recipient_codes) and not missing_sections,
            "per_section": per_section,
        }

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

    def build_grade_records(self, summary: dict[str, Any], *, header_id: int,
                            grades_by_student_code: dict[str, str]) -> list[dict[str, Any]]:
        records = []
        for s in summary.get("students") or []:
            code = str(s.get("alucod") or "")
            if code not in grades_by_student_code:
                continue
            note = str(grades_by_student_code[code]).strip().upper()
            note_obj = (s.get("notas") or {}).get(str(header_id)) or {}
            if not note_obj:
                continue
            records.append({
                "idNota": note_obj.get("idNota"),
                "notaNue": note,
                "nivelEva": note_obj.get("nivelEva"),
                "idPersona": s.get("idPersona"),
                "alucod": code,
                "nemo": s.get("nemo"),
            })
        return records
