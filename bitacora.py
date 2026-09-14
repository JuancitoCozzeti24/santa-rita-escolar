from __future__ import annotations

import json
import os
import re
import threading
import unicodedata
from collections import Counter
from datetime import date, datetime
from typing import Any
from urllib.parse import quote
from zoneinfo import ZoneInfo

import requests

LIMA = ZoneInfo("America/Lima")
DEFAULT_SPREADSHEET_ID = "13QYo-Dx23LPzKbY7szrz1HWyOMgQwKP5_oriGKKCNnA"
SPREADSHEET_TITLE = "BITÁCORA DOCENTE – MATEMÁTICA 2026"
TOKEN_URL = "https://oauth2.googleapis.com/token"

ALLOWED_TYPES = {"Positivo", "Observación", "Incidencia", "Seguimiento"}
ALLOWED_CATEGORIES = {
    "Participación positiva", "Esfuerzo destacado", "Cumplimiento académico",
    "No trajo material", "Conversación reiterada", "Distracción",
    "Salida prolongada", "Tardanza", "Trabajo incompleto", "Incumplimiento",
    "Convivencia", "Mejora observada", "Otro",
}
ALLOWED_IMPORTANCE = {"Baja", "Media", "Alta"}
ALLOWED_YES_NO = {"Sí", "No"}

BITACORA_POLICY = f"""
POLÍTICA PERMANENTE DE BITÁCORA DOCENTE:
1. Cuando el docente use la palabra “BITÁCORA”, “registra en la bitácora”, “anota en la bitácora” o una expresión inequívoca equivalente, usa la herramienta bitacora_docente. El repositorio oficial es el Google Sheet “{SPREADSHEET_TITLE}”, ID {DEFAULT_SPREADSHEET_ID}.
2. Antes de escribir, resuelve siempre al estudiante contra la pestaña ALUMNOS. Nunca inventes Alumno_ID, ALUCOD, grado, sección ni nombre. Si hay más de una coincidencia, no escribas y muestra las coincidencias para desambiguar.
3. Usa BITÁCORA para conducta, convivencia, asistencia/tardanzas, bienestar observado, participación, incidencias y seguimiento. Usa ACADÉMICO para evidencias académicas, trabajo en aula, calificaciones y observaciones de aprendizaje.
4. Los registros se agregan al final; nunca sustituyas ni borres registros anteriores mediante esta herramienta.
5. Redacta en primera persona del docente, con lenguaje profesional, objetivo y basado en hechos observables. No uses etiquetas despectivas, diagnósticos, causas médicas no confirmadas ni conclusiones que el docente no haya aportado.
6. Si una información procede de terceros, indícalo como referencia o información comunicada, no como observación directa del docente.
7. Usa fecha local de Lima. No inventes una hora del incidente: si el docente no indicó hora, deja Hora vacía.
8. Si el docente no dijo que informó a familia o tutor/orientación, deja esos campos vacíos; no asumas “No”.
9. Después de cada escritura, relee la fila guardada y verifica que el Registro_ID persista antes de afirmar que el registro quedó almacenado.
10. La frase explícita “BITÁCORA: …”, “registra en la bitácora…” o equivalente constituye autorización para añadir el registro descrito y permite llamar la escritura con confirmed=true. Si el usuario solo está preguntando, analizando o ensayando una redacción, no escribas.
11. Para informes de un estudiante, usa student_report (o student_history si solo necesitas los registros) y construye el informe solo con hechos documentados; protege los datos de otros alumnos y no expongas nombres de terceros innecesariamente.
12. Si el docente indica un rango temporal, envía fecha_desde y fecha_hasta. Si solo dice “BITÁCORA” sin estudiante ni operación, consulta status y ofrece buscar por estudiante, sección o rango; no vuelques datos personales de todos los alumnos.
""".strip()

_token_lock = threading.RLock()
_access_token = ""


def _now() -> datetime:
    return datetime.now(LIMA)


def _norm(value: Any) -> str:
    text = unicodedata.normalize("NFKD", str(value or ""))
    text = "".join(ch for ch in text if not unicodedata.combining(ch))
    text = re.sub(r"[^A-Za-z0-9]+", " ", text).upper()
    return " ".join(text.split())


def _grade_norm(value: Any) -> str:
    match = re.search(r"[25]", str(value or ""))
    return match.group(0) if match else ""


def _section_norm(value: Any) -> str:
    text = _norm(value)
    for token in text.split():
        if token in {"A", "B"}:
            return token
    return ""


def _parse_payload(payload_json: str) -> dict[str, Any]:
    try:
        data = json.loads(payload_json or "{}")
    except Exception as exc:
        raise ValueError(f"payload_json no es JSON válido: {exc}") from exc
    if not isinstance(data, dict):
        raise ValueError("payload_json debe representar un objeto JSON.")
    return data


def _setting(name: str) -> str:
    from config import settings
    return str(getattr(settings, name, "") or "")


def _spreadsheet_id() -> str:
    return str(os.getenv("BITACORA_SPREADSHEET_ID") or DEFAULT_SPREADSHEET_ID).strip()


def _spreadsheet_url() -> str:
    return f"https://docs.google.com/spreadsheets/d/{_spreadsheet_id()}/edit"


def _google_token(*, force: bool = False) -> str:
    global _access_token
    with _token_lock:
        if _access_token and not force:
            return _access_token
        client_id = _setting("google_client_id")
        client_secret = _setting("google_client_secret")
        refresh_token = _setting("google_refresh_token")
        missing = [name for name, value in [
            ("GOOGLE_CLIENT_ID", client_id),
            ("GOOGLE_CLIENT_SECRET", client_secret),
            ("GOOGLE_REFRESH_TOKEN", refresh_token),
        ] if not value]
        if missing:
            raise RuntimeError("Falta configurar OAuth de Google: " + ", ".join(missing))
        response = requests.post(TOKEN_URL, data={
            "client_id": client_id,
            "client_secret": client_secret,
            "refresh_token": refresh_token,
            "grant_type": "refresh_token",
        }, timeout=30)
        if not response.ok:
            raise RuntimeError(f"Google OAuth falló ({response.status_code}): {response.text[:500]}")
        token = str((response.json() or {}).get("access_token") or "")
        if not token:
            raise RuntimeError("Google OAuth no devolvió access_token.")
        _access_token = token
        return token


def _google_request(method: str, url: str, *, params=None, json_body=None) -> dict[str, Any]:
    headers = {"Authorization": f"Bearer {_google_token()}"}
    response = requests.request(method, url, headers=headers, params=params, json=json_body, timeout=45)
    if response.status_code == 401:
        headers["Authorization"] = f"Bearer {_google_token(force=True)}"
        response = requests.request(method, url, headers=headers, params=params, json=json_body, timeout=45)
    if not response.ok:
        raise RuntimeError(f"Google API falló ({response.status_code}): {response.text[:900]}")
    return response.json() if response.content else {}


def _sheets_get(a1_range: str) -> list[list[Any]]:
    encoded = quote(a1_range, safe="")
    url = f"https://sheets.googleapis.com/v4/spreadsheets/{_spreadsheet_id()}/values/{encoded}"
    return list((_google_request("GET", url).get("values") or []))


def _sheets_append(a1_range: str, row: list[Any]) -> str:
    encoded = quote(a1_range, safe="")
    url = f"https://sheets.googleapis.com/v4/spreadsheets/{_spreadsheet_id()}/values/{encoded}:append"
    result = _google_request("POST", url, params={
        "valueInputOption": "USER_ENTERED", "insertDataOption": "INSERT_ROWS",
    }, json_body={"values": [row]})
    updated_range = str((result.get("updates") or {}).get("updatedRange") or "")
    if not updated_range:
        raise RuntimeError("Google Sheets no devolvió updatedRange tras el append.")
    return updated_range


def _row_dict(headers: list[Any], row: list[Any]) -> dict[str, Any]:
    values = list(row) + [""] * max(0, len(headers) - len(row))
    return {str(headers[i]): values[i] for i in range(len(headers))}


def _load_students() -> list[dict[str, str]]:
    rows = _sheets_get("ALUMNOS!A1:G500")
    if not rows:
        raise RuntimeError("La pestaña ALUMNOS está vacía o no se pudo leer.")
    headers = [str(x) for x in rows[0]]
    expected = ["Alumno_ID", "Apellidos y nombres", "Grado", "Sección", "Código/ID externo"]
    if headers[:5] != expected:
        raise RuntimeError("La estructura de ALUMNOS no coincide con la bitácora esperada.")
    out = []
    for raw in rows[1:]:
        row = list(raw) + [""] * (7 - len(raw))
        if not str(row[0]).strip():
            continue
        out.append({
            "alumno_id": str(row[0]).strip(), "nombre": str(row[1]).strip(),
            "grado": str(row[2]).strip(), "seccion": str(row[3]).strip(),
            "alucod": str(row[4]).strip(), "estado": str(row[5]).strip(),
            "fecha_alta": str(row[6]).strip(),
        })
    return out


def _resolve_student(data: dict[str, Any]) -> dict[str, Any]:
    query = str(data.get("student") or data.get("estudiante") or data.get("alumno_id") or data.get("alucod") or "").strip()
    if not query:
        raise ValueError("Debes indicar student/estudiante, alumno_id o alucod.")
    grade = _grade_norm(data.get("grado"))
    section = _section_norm(data.get("seccion"))
    students = _load_students()
    filtered = [s for s in students if (not grade or _grade_norm(s["grado"]) == grade) and (not section or _section_norm(s["seccion"]) == section)]
    nq = _norm(query)
    exact = [s for s in filtered if nq and nq in {_norm(s["alumno_id"]), _norm(s["alucod"]), _norm(s["nombre"])}]
    if len(exact) == 1:
        return {"status": "resolved", "student": exact[0]}
    if len(exact) > 1:
        return {"status": "ambiguous", "candidates": exact}
    wanted = set(nq.split())
    fuzzy = [s for s in filtered if wanted and wanted.issubset(set(_norm(s["nombre"]).split()))]
    if len(fuzzy) == 1:
        return {"status": "resolved", "student": fuzzy[0]}
    if len(fuzzy) > 1:
        return {"status": "ambiguous", "candidates": fuzzy}
    return {"status": "not_found", "query": query, "grado": grade, "seccion": section}


def _require_resolved(data: dict[str, Any]) -> dict[str, str]:
    result = _resolve_student(data)
    if result.get("status") != "resolved":
        raise ValueError("No se puede escribir porque el estudiante no quedó resuelto de forma única: " + json.dumps(result, ensure_ascii=False))
    return dict(result["student"])


def _pick(value: Any, allowed: set[str], field_name: str, *, default: str = "") -> str:
    text = str(value or "").strip()
    if not text:
        return default
    normalized = {_norm(item): item for item in allowed}
    match = normalized.get(_norm(text))
    if not match:
        raise ValueError(f"{field_name} inválido: {text}. Valores permitidos: {sorted(allowed)}")
    return match


def _date_value(data: dict[str, Any]) -> str:
    value = str(data.get("fecha") or "").strip()
    if not value:
        return _now().strftime("%d/%m/%Y")
    if not re.fullmatch(r"\d{2}/\d{2}/\d{4}", value):
        raise ValueError("fecha debe usar formato DD/MM/YYYY.")
    return value


def _time_value(data: dict[str, Any]) -> str:
    value = str(data.get("hora") or "").strip()
    if not value:
        return ""
    if not re.fullmatch(r"(?:[01]\d|2[0-3]):[0-5]\d", value):
        raise ValueError("hora debe usar formato HH:MM de 24 horas.")
    return value


def _parse_date(value: Any, field_name: str) -> date | None:
    text = str(value or "").strip()
    if not text:
        return None
    for pattern in ("%d/%m/%Y", "%Y-%m-%d"):
        try:
            return datetime.strptime(text, pattern).date()
        except ValueError:
            continue
    raise ValueError(f"{field_name} debe usar DD/MM/YYYY o YYYY-MM-DD.")


def _history_date_range(data: dict[str, Any]) -> tuple[date | None, date | None]:
    start = _parse_date(
        data.get("fecha_desde", data.get("date_from", data.get("desde"))),
        "fecha_desde",
    )
    end = _parse_date(
        data.get("fecha_hasta", data.get("date_to", data.get("hasta"))),
        "fecha_hasta",
    )
    if start and end and start > end:
        raise ValueError("fecha_desde no puede ser posterior a fecha_hasta.")
    return start, end


def _row_date(record: dict[str, Any]) -> date | None:
    try:
        return _parse_date(record.get("Fecha"), "Fecha")
    except ValueError:
        return None


def _in_date_range(record: dict[str, Any], start: date | None, end: date | None) -> bool:
    if not start and not end:
        return True
    current = _row_date(record)
    if current is None:
        return False
    return (not start or current >= start) and (not end or current <= end)


def _sort_records(records: list[dict[str, Any]]) -> list[dict[str, Any]]:
    def key(record: dict[str, Any]) -> tuple[date, str, str]:
        return (
            _row_date(record) or date.min,
            str(record.get("Hora") or ""),
            str(record.get("Registro_ID") or ""),
        )

    return sorted(records, key=key)


def _record_id(prefix: str, alumno_id: str) -> str:
    return f"{prefix}-{_now():%Y%m%d-%H%M%S%f}-{alumno_id}"


def _preview_observation(data: dict[str, Any]) -> tuple[dict[str, Any], list[Any]]:
    student = _require_resolved(data)
    description = str(data.get("descripcion_objetiva") or data.get("descripcion") or "").strip()
    if not description:
        raise ValueError("descripcion_objetiva es obligatoria.")
    record = {
        "Registro_ID": _record_id("BIT", student["alumno_id"]),
        "Fecha": _date_value(data), "Hora": _time_value(data),
        "Alumno_ID": student["alumno_id"], "Estudiante": student["nombre"],
        "Grado": student["grado"], "Sección": student["seccion"],
        "Tipo de registro": _pick(data.get("tipo"), ALLOWED_TYPES, "tipo", default="Observación"),
        "Categoría": _pick(data.get("categoria"), ALLOWED_CATEGORIES, "categoria", default="Otro"),
        "Descripción objetiva": description,
        "Impacto en aprendizaje/convivencia": str(data.get("impacto") or "").strip(),
        "Acción docente": str(data.get("accion_docente") or "").strip(),
        "Seguimiento": str(data.get("seguimiento") or "").strip(),
        "Nivel de importancia": _pick(data.get("nivel_importancia"), ALLOWED_IMPORTANCE, "nivel_importancia", default="Media"),
        "Comunicación a familia": _pick(data.get("comunicacion_familia"), ALLOWED_YES_NO, "comunicacion_familia", default=""),
        "Comunicación a tutor/orientación": _pick(data.get("comunicacion_tutor"), ALLOWED_YES_NO, "comunicacion_tutor", default=""),
        "Evidencia o referencia": str(data.get("evidencia") or "").strip(),
        "Registrado por": str(data.get("registrado_por") or "Docente de Matemática").strip(),
    }
    return record, list(record.values())


def _preview_academic(data: dict[str, Any]) -> tuple[dict[str, Any], list[Any]]:
    student = _require_resolved(data)
    observations = str(data.get("observaciones") or "").strip()
    if not observations:
        raise ValueError("observaciones es obligatorio para un registro académico.")
    level = str(data.get("nivel_cualitativo") or "").strip().upper()
    if level and level not in {"A", "B", "C"}:
        raise ValueError("nivel_cualitativo solo puede ser A, B o C.")
    score = data.get("nota_20", "")
    if score not in ("", None):
        try:
            numeric = float(score)
        except Exception as exc:
            raise ValueError("nota_20 debe ser numérica.") from exc
        if numeric < 0 or numeric > 20:
            raise ValueError("nota_20 debe estar entre 0 y 20.")
        score = int(numeric) if numeric.is_integer() else numeric
    else:
        score = ""
    source_map = {_norm("Classroom"): "Classroom", _norm("SIEweb"): "SIEweb", _norm("Otro"): "Otro"}
    source = source_map.get(_norm(data.get("fuente") or "Otro"))
    if not source:
        raise ValueError("fuente solo puede ser Classroom, SIEweb u Otro.")
    record = {
        "Registro_ID": _record_id("ACD", student["alumno_id"]),
        "Fecha": _date_value(data), "Alumno_ID": student["alumno_id"],
        "Estudiante": student["nombre"], "Grado": student["grado"],
        "Sección": student["seccion"],
        "Actividad/Evidencia": str(data.get("actividad_evidencia") or "").strip(),
        "Competencia": str(data.get("competencia") or "").strip(),
        "Capacidad/Desempeño": str(data.get("capacidad_desempeno") or "").strip(),
        "Nota /20": score, "Nivel cualitativo": level, "Fuente": source,
        "Observaciones": observations,
    }
    return record, list(record.values())


def _verify_saved(updated_range: str, record_id: str) -> dict[str, Any]:
    rows = _sheets_get(updated_range)
    if not rows or str(rows[0][0] if rows[0] else "") != record_id:
        raise RuntimeError(f"No se pudo verificar la persistencia del registro {record_id} en {updated_range}.")
    return {"verified": True, "updated_range": updated_range, "row": rows[0]}


def _history(data: dict[str, Any]) -> dict[str, Any]:
    student = _require_resolved(data)
    limit = max(1, min(int(data.get("limit") or 100), 300))
    start, end = _history_date_range(data)
    behavior_rows = _sheets_get("BITÁCORA!A1:R3000")
    bh = behavior_rows[0] if behavior_rows else []
    all_behavior = [
        _row_dict(bh, row)
        for row in behavior_rows[1:]
        if len(row) >= 4 and str(row[3]).strip() == student["alumno_id"]
    ]
    behavior = _sort_records([
        record for record in all_behavior if _in_date_range(record, start, end)
    ])
    academic_rows = _sheets_get("ACADÉMICO!A1:M3000")
    ah = academic_rows[0] if academic_rows else []
    all_academic = [
        _row_dict(ah, row)
        for row in academic_rows[1:]
        if len(row) >= 3 and str(row[2]).strip() == student["alumno_id"]
    ]
    academic = _sort_records([
        record for record in all_academic if _in_date_range(record, start, end)
    ])
    return {
        "student": student, "bitacora": behavior[-limit:], "academico": academic[-limit:],
        "counts": {
            "bitacora": len(behavior),
            "academico": len(academic),
            "bitacora_total_sin_filtro": len(all_behavior),
            "academico_total_sin_filtro": len(all_academic),
        },
        "scope": {
            "fecha_desde": start.strftime("%d/%m/%Y") if start else None,
            "fecha_hasta": end.strftime("%d/%m/%Y") if end else None,
            "limit": limit,
            "chronological": True,
        },
        "source": {
            "spreadsheet_title": SPREADSHEET_TITLE,
            "spreadsheet_id": _spreadsheet_id(),
            "spreadsheet_url": _spreadsheet_url(),
        },
    }


def _student_report(data: dict[str, Any]) -> dict[str, Any]:
    history = _history(data)
    behavior = list(history.get("bitacora") or [])
    academic = list(history.get("academico") or [])
    history["summary"] = {
        "tipos_bitacora": dict(Counter(
            str(row.get("Tipo de registro") or "Sin tipo") for row in behavior
        )),
        "categorias_bitacora": dict(Counter(
            str(row.get("Categoría") or "Sin categoría") for row in behavior
        )),
        "niveles_importancia": dict(Counter(
            str(row.get("Nivel de importancia") or "Sin nivel") for row in behavior
        )),
        "niveles_academicos": dict(Counter(
            str(row.get("Nivel cualitativo") or "Sin nivel") for row in academic
        )),
    }
    history["report_rules"] = [
        "Redactar únicamente con los registros devueltos.",
        "Separar fortalezas, observaciones/incidencias, seguimiento y evidencia académica.",
        "Citar Fecha y Registro_ID en cada hecho relevante.",
        "No convertir ausencia de registros en una afirmación absoluta sobre la conducta.",
        "No atribuir al estudiante registros de sección con Alumno_ID vacío.",
    ]
    return history


def dispatch(action: str, data: dict[str, Any], confirmed: bool = False) -> dict[str, Any]:
    """Despachador único para el tool nativo y la ruta compatible estable."""
    act = str(action or "").strip().lower()
    aliases = {
        "bitacora_policy": "policy",
        "bitacora_status": "status",
        "bitacora_resolve_student": "resolve_student",
        "bitacora_student_history": "student_history",
        "bitacora_student_report": "student_report",
        "bitacora_append_observation": "append_observation",
        "bitacora_append_academic": "append_academic",
    }
    act = aliases.get(act, act)
    if act == "policy":
        return {
            "policy": BITACORA_POLICY,
            "spreadsheet_id": _spreadsheet_id(),
            "spreadsheet_url": _spreadsheet_url(),
        }
    if act == "status":
        return {
            "ok": True,
            "available": True,
            "spreadsheet_title": SPREADSHEET_TITLE,
            "spreadsheet_id": _spreadsheet_id(),
            "spreadsheet_url": _spreadsheet_url(),
            "tabs": {
                "ALUMNOS": _sheets_get("ALUMNOS!A1:G2")[:1],
                "BITÁCORA": _sheets_get("BITÁCORA!A1:R2")[:1],
                "ACADÉMICO": _sheets_get("ACADÉMICO!A1:M2")[:1],
            },
            "reads": ["policy", "status", "resolve_student", "student_history", "student_report"],
            "writes": ["append_observation", "append_academic"],
            "timezone": "America/Lima",
            "append_only": True,
        }
    if act == "resolve_student":
        return _resolve_student(data)
    if act == "student_history":
        return _history(data)
    if act == "student_report":
        return _student_report(data)
    if act == "append_observation":
        record, row = _preview_observation(data)
        if not confirmed:
            return {
                "requires_confirmation": True,
                "preview": record,
                "note": "Una orden explícita del usuario con BITÁCORA permite repetir con confirmed=true.",
                "spreadsheet_url": _spreadsheet_url(),
            }
        updated_range = _sheets_append("BITÁCORA!A:R", row)
        return {
            "ok": True,
            "saved": True,
            "kind": "BITÁCORA",
            "record": record,
            "verification": _verify_saved(updated_range, record["Registro_ID"]),
            "spreadsheet_url": _spreadsheet_url(),
        }
    if act == "append_academic":
        record, row = _preview_academic(data)
        if not confirmed:
            return {
                "requires_confirmation": True,
                "preview": record,
                "note": "Una orden explícita del usuario con BITÁCORA permite repetir con confirmed=true.",
                "spreadsheet_url": _spreadsheet_url(),
            }
        updated_range = _sheets_append("ACADÉMICO!A:M", row)
        return {
            "ok": True,
            "saved": True,
            "kind": "ACADÉMICO",
            "record": record,
            "verification": _verify_saved(updated_range, record["Registro_ID"]),
            "spreadsheet_url": _spreadsheet_url(),
        }
    raise ValueError(
        "action inválida. Usa policy, status, resolve_student, student_history, "
        "student_report, append_observation o append_academic."
    )


def install(mcp) -> None:
    if getattr(mcp, "_sieroom_bitacora_installed", False):
        return
    try:
        current = str(getattr(mcp, "instructions", "") or "").strip()
        if BITACORA_POLICY not in current:
            combined = (current + "\n\n" + BITACORA_POLICY).strip()
            # Mantener sincronizada la propiedad pública y el Server interno.
            # server.py lee mcp.instructions más adelante al anexar otras políticas.
            try:
                setattr(mcp, "instructions", combined)
            except Exception:
                pass
            if hasattr(mcp, "_mcp_server"):
                mcp._mcp_server.instructions = combined
    except Exception as exc:
        print(f"SieRoom Bitácora: no se pudo anexar la política a instructions: {exc}", flush=True)

    @mcp.tool()
    def bitacora_docente(action: str, payload_json: str = "{}", confirmed: bool = False) -> dict[str, Any]:
        """Consulta y registra en BITÁCORA DOCENTE – MATEMÁTICA 2026. Lecturas: policy, status, resolve_student, student_history y student_report; estos dos últimos admiten fecha_desde/fecha_hasta. Escrituras append_observation y append_academic agregan una sola fila y verifican persistencia. Requieren confirmed=true; una orden explícita del usuario con “BITÁCORA: ...” o “registra en la bitácora...” constituye autorización para confirmed=true."""
        return dispatch(action, _parse_payload(payload_json), confirmed)

    setattr(mcp, "_sieroom_bitacora_installed", True)
    print("SieRoom Bitácora: herramienta bitacora_docente instalada.", flush=True)
