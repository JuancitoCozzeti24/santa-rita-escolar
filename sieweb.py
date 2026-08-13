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
