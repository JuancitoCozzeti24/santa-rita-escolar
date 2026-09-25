from __future__ import annotations

from datetime import date
from typing import Any
from urllib.parse import quote

import profe_johnny_brain as brain
import profe_johnny_identity_v3 as identity
import profe_johnny_mobile_v2 as mobile
from bitacora import _google_request, dispatch as bitacora_dispatch

API_VERSION = "2026-09-24-identity-v5"


def _course_for_student(student: dict[str, str]):
    courses = [
        course
        for course in brain._client.list_courses(active_only=True)
        if mobile._mobile_course_matches(course, student["grade"])
        and mobile._section_matches(course, student["grade"], student["section"])
    ]
    target_name = identity._norm(student["full_name"])
    for course in courses:
        course_id = str(course.get("id") or "")
        if not course_id:
            continue
        try:
            roster_rows = brain._client.list_students(course_id)
        except Exception:
            roster_rows = []
        for roster in roster_rows:
            if identity._norm(roster.get("name")) == target_name:
                return course, roster
    return (courses[0] if courses else None), None


def _ensure_family_tab() -> None:
    spreadsheet_id = identity.FAMILY_SHEET_ID
    metadata_url = f"https://sheets.googleapis.com/v4/spreadsheets/{spreadsheet_id}"
    data = _google_request("GET", metadata_url, params={"fields": "sheets.properties.title"})
    titles = {
        str(((sheet or {}).get("properties") or {}).get("title") or "")
        for sheet in (data.get("sheets") or [])
    }
    if identity.FAMILY_TAB not in titles:
        _google_request(
            "POST",
            metadata_url + ":batchUpdate",
            json_body={"requests": [{"addSheet": {"properties": {"title": identity.FAMILY_TAB}}}]},
        )
        header_url = (
            f"https://sheets.googleapis.com/v4/spreadsheets/{spreadsheet_id}/values/"
            f"{quote(identity.FAMILY_TAB + '!A1:E1', safe='')}"
        )
        _google_request(
            "PUT",
            header_url,
            params={"valueInputOption": "RAW"},
            json_body={"values": [["family_code", "student_key", "label", "active", "created_at"]]},
        )


def _write_family_link(family_code: str, student_key: str, label: str = "") -> None:
    student = identity._roster_record(student_key)
    if not student:
        raise ValueError("student_not_found")
    _ensure_family_tab()
    if any(
        row["family_code"] == family_code and row["student_key"] == student_key
        for row in identity._family_rows()
    ):
        return
    url = (
        f"https://sheets.googleapis.com/v4/spreadsheets/{identity.FAMILY_SHEET_ID}/values/"
        f"{quote(identity.FAMILY_TAB + '!A:E', safe='')}:append"
    )
    _google_request(
        "POST",
        url,
        params={"valueInputOption": "RAW", "insertDataOption": "INSERT_ROWS"},
        json_body={"values": [[family_code, student_key, label, "ACTIVO", brain._now_lima().isoformat()]]},
    )


def _institutional_context() -> str:
    blocks: list[str] = []
    try:
        core, _ = brain._core_context(
            "horario calendario calendarizacion evaluacion examen tarea actividad semana colegio"
        )
        if core:
            blocks.append("## INFORMACIÓN GENERAL E INSTITUCIONAL\n" + core)
    except Exception:
        pass
    try:
        for doc in brain._load_core_kb():
            name = str(doc.get("name") or "")
            if "calendar" not in brain._norm(name):
                continue
            text = str(doc.get("text") or "").strip()
            if text:
                blocks.append(
                    "## CALENDARIZACIÓN INSTITUCIONAL COMPLETA\n"
                    + f"Documento: {name}\n"
                    + text[:22000]
                )
            break
    except Exception:
        pass
    return "\n\n".join(blocks)


def _bitacora_context(
    summary: dict[str, Any],
    start_date: date | None,
    end_date: date | None,
    role: str,
) -> str:
    if role not in {"family", "owner"}:
        return (
            "## BITÁCORA DOCENTE\n"
            "El perfil estudiante no tiene acceso a la bitácora docente. "
            "Solo puede consultar su información académica."
        )

    student = summary.get("student") or {}
    payload: dict[str, Any] = {
        "student": str(student.get("display_name") or ""),
        "grado": str(student.get("grade") or ""),
        "seccion": str(student.get("section") or ""),
        "limit": 80,
    }
    if start_date:
        payload["fecha_desde"] = start_date.isoformat()
    if end_date:
        payload["fecha_hasta"] = end_date.isoformat()

    try:
        history = bitacora_dispatch("student_history", payload, False)
    except Exception as exc:
        summary["bitacora_status"] = {
            "available": False,
            "error": f"{type(exc).__name__}: {exc}",
        }
        return (
            "## BITÁCORA DOCENTE\n"
            "No fue posible consultar la bitácora en este momento. "
            "No inventes incidencias ni observaciones."
        )

    records = list(history.get("bitacora") or [])
    summary["bitacora_status"] = {
        "available": True,
        "records": len(records),
        "scope": history.get("scope") or {},
    }
    lines = [
        "## BITÁCORA DOCENTE DEL ESTUDIANTE AUTORIZADO",
        f"Registros encontrados en el periodo consultado: {len(records)}.",
    ]
    if not records:
        lines.append(
            "No se encontraron incidencias u observaciones conductuales registradas "
            "para este estudiante dentro del periodo consultado."
        )
        return "\n".join(lines)

    target_name = str(student.get("display_name") or "")
    for row in records:
        def safe(value: Any) -> str:
            text = str(value or "").strip()
            if role == "family":
                return brain._redact_other_students(text, target_name)
            return text

        date_text = safe(row.get("Fecha"))
        kind = safe(row.get("Tipo de registro"))
        category = safe(row.get("Categoría"))
        description = safe(row.get("Descripción objetiva"))
        impact = safe(row.get("Impacto en aprendizaje/convivencia"))
        action = safe(row.get("Acción docente"))
        follow = safe(row.get("Seguimiento"))

        lines.append(
            f"- {date_text} | tipo={kind} | categoría={category} | "
            f"hecho={description} | impacto={impact} | acción={action} | seguimiento={follow}"
        )

    lines.extend([
        "INTERPRETACIÓN PARA FAMILIAS:",
        (
            "Si el rol es family, interpreta estos registros con lenguaje psicopedagógico, "
            "descriptivo y constructivo. Explica qué ocurrió, qué impacto tuvo y cómo puede "
            "acompañarse la mejora. No reveles nombres de otros estudiantes."
        ),
        (
            "No diagnostiques, no atribuyas intenciones y no conviertas una observación puntual "
            "en una etiqueta permanente sobre el estudiante."
        ),
    ])
    return "\n".join(lines)


def _private_context(
    student_key: str,
    start_date: date | None = None,
    end_date: date | None = None,
    role: str = "student",
):
    summary = identity._student_classroom_summary(
        student_key,
        start_date=start_date,
        end_date=end_date,
    )
    progress = summary.get("progress") or {}
    period = summary.get("period") or {}
    lines = [
        "## CLASSROOM PRIVADO DEL USUARIO AUTENTICADO",
        f"Estudiante: {summary['student']['display_name']} | {summary['student']['grade']}.º {summary['student']['section']}",
        (
            "Periodo Classroom: "
            f"desde={period.get('start')} | hasta={period.get('end')}"
        ),
        (
            "Resumen Classroom: "
            f"total={progress.get('total', 0)} | entregadas={progress.get('submitted', 0)} | "
            f"pendientes={progress.get('pending', 0)} | tardías={progress.get('late', 0)} | "
            f"calificadas={progress.get('graded', 0)} | promedio={progress.get('average_percent')}%"
        ),
    ]
    for item in summary.get("activities") or []:
        lines.append(
            f"- {item['title']} | límite={item['due']} | estado={item.get('state')} | "
            f"nota={item.get('grade')} / {item.get('max_points')} | tardía={item.get('late')}"
        )

    lines.append(_bitacora_context(summary, start_date, end_date, role))

    lines.extend([
        "## POLÍTICA DE PRIVACIDAD ACADÉMICA",
        "Las notas exactas de Classroom sí pueden mostrarse al propio estudiante o a su familia autenticada. Nunca reveles datos de otros estudiantes.",
        "El perfil estudiante NO puede acceder a la bitácora docente.",
        "El perfil familia puede recibir información de bitácora únicamente sobre su hijo vinculado y redactada con enfoque psicopedagógico.",
        "## POLÍTICA SIEWEB/CIEWEB",
        "Para estudiantes y familias, cualquier información de SIEweb/CIEweb disponible debe convertirse en orientación pedagógica sin revelar letra o nota cruda. Para owner sí puede mostrarse el dato disponible. Si SIEweb no está en el contexto, no lo inventes.",
    ])
    institutional = _institutional_context()
    if institutional:
        lines.append(institutional)
    return "\n".join(lines), summary

def _install_bootstrap_contract() -> None:
    if getattr(mobile, "_identity_v4_bootstrap_patched", False):
        return
    original = mobile._bootstrap_payload

    def payload():
        data = original()
        data["api_version"] = API_VERSION
        data["mode"] = "verified_role_based_read_only"
        data.setdefault("features", {}).update({
            "verified_student_login": True,
            "verified_family_login": True,
            "owner_login": True,
            "secure_chat": True,
            "student_private_classroom": True,
            "classroom_progress_summary": True,
            "owner_natural_student_lookup": True,
            "sieweb_raw_hidden_from_students": True,
        })
        data.setdefault("endpoints", {}).update({
            "auth": "/profe-johnny/v1/auth",
            "me": "/profe-johnny/v1/me",
            "secure_chat": "/profe-johnny/v1/secure-chat",
            "student_summary": "/profe-johnny/v1/student-summary",
        })
        return data

    mobile._bootstrap_payload = payload
    setattr(mobile, "_identity_v4_bootstrap_patched", True)


def install(mcp: Any) -> None:
    if getattr(mcp, "_profe_johnny_identity_v4_installed", False):
        return
    identity.API_VERSION = API_VERSION
    identity._course_for_student = _course_for_student
    identity._write_family_link = _write_family_link
    identity._private_context = _private_context
    _install_bootstrap_contract()
    identity.install(mcp)
    setattr(mcp, "_profe_johnny_identity_v4_installed", True)
    print(
        "PROFE JOHNNY APP Identity v4: identidad verificada, sección exacta, familias e información institucional activadas.",
        flush=True,
    )
