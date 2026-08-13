from __future__ import annotations

import json
from datetime import date, time
from typing import Any

from mcp.server.fastmcp import FastMCP
from mcp.server.auth.settings import AuthSettings
from pydantic import AnyHttpUrl

from auth import Auth0TokenVerifier

from classroom import ClassroomClient
from config import settings
from sieweb import SieWebClient

if not settings.auth0_issuer or not settings.auth0_audience:
    raise RuntimeError(
        "Falta configurar AUTH0_ISSUER y AUTH0_AUDIENCE. "
        "El servidor remoto se niega a iniciar sin autenticación OAuth."
    )

mcp = FastMCP(
    "Santa Rita Escolar",
    host=settings.mcp_host,
    port=settings.mcp_port,
    streamable_http_path="/mcp",
    instructions=(
        "Integra Google Classroom y SieWeb de Santa Rita de Casia. Para lecturas usa los "
        "identificadores estables devueltos por las herramientas. Antes de escribir notas, "
        "criterios, conclusiones o mensajes, resume exactamente el cambio al usuario y solo "
        "ejecuta la herramienta de escritura cuando el usuario haya autorizado ese cambio."
    ),
    token_verifier=Auth0TokenVerifier(
        issuer=settings.auth0_issuer, audience=settings.auth0_audience
    ),
    auth=AuthSettings(
        issuer_url=AnyHttpUrl(settings.auth0_issuer.rstrip("/") + "/"),
        resource_server_url=AnyHttpUrl(settings.mcp_resource_url),
        required_scopes=[settings.auth0_required_scope],
    ),
)

classroom = ClassroomClient()
sieweb = SieWebClient()


def _ok(data: Any) -> str:
    return json.dumps(data, ensure_ascii=False, default=str)


# ---------------- Google Classroom ----------------
@mcp.tool()
def classroom_list_courses(active_only: bool = True) -> str:
    """Lista los cursos de Google Classroom donde la cuenta autenticada es docente."""
    return _ok(classroom.list_courses(active_only=active_only))


@mcp.tool()
def classroom_list_students(course_id: str) -> str:
    """Lista estudiantes y correos de un curso de Classroom."""
    return _ok(classroom.list_students(course_id))


@mcp.tool()
def classroom_list_coursework(course_id: str, include_drafts: bool = True) -> str:
    """Lista tareas/trabajos de clase de un curso de Classroom."""
    return _ok(classroom.list_coursework(course_id, include_drafts=include_drafts))


@mcp.tool()
def classroom_list_submissions(course_id: str, course_work_id: str) -> str:
    """Lista entregas y estado de cada estudiante para una tarea de Classroom."""
    return _ok(classroom.list_submissions(course_id, course_work_id))


@mcp.tool()
def classroom_missing_students(course_id: str, course_work_id: str) -> str:
    """Devuelve estudiantes cuya entrega no está TURNED_IN ni RETURNED."""
    return _ok(classroom.missing_students(course_id, course_work_id))


@mcp.tool()
def classroom_create_assignment(
    course_id: str,
    title: str,
    description: str = "",
    max_points: float | None = None,
    due_date_iso: str | None = None,
    due_time_hhmm: str | None = None,
    topic_id: str | None = None,
    publish: bool = False,
    confirmed: bool = False,
) -> str:
    """Crea una tarea. Requiere confirmed=true después de que el usuario confirme el resumen."""
    preview = {
        "course_id": course_id,
        "title": title,
        "description": description,
        "max_points": max_points,
        "due_date": due_date_iso,
        "due_time": due_time_hhmm,
        "topic_id": topic_id,
        "state": "PUBLISHED" if publish else "DRAFT",
    }
    if not confirmed:
        return _ok({"requires_confirmation": True, "preview": preview})
    due_date = date.fromisoformat(due_date_iso) if due_date_iso else None
    due_time = time.fromisoformat(due_time_hhmm) if due_time_hhmm else None
    return _ok(
        classroom.create_coursework(
            course_id,
            title=title,
            description=description,
            max_points=max_points,
            due_date=due_date,
            due_time=due_time,
            topic_id=topic_id,
            publish=publish,
        )
    )


@mcp.tool()
def classroom_grade_submission(
    course_id: str,
    course_work_id: str,
    submission_id: str,
    grade: float,
    return_to_student: bool = False,
    confirmed: bool = False,
) -> str:
    """Asigna nota a una entrega. Requiere confirmed=true tras confirmación del usuario."""
    preview = {
        "course_id": course_id,
        "course_work_id": course_work_id,
        "submission_id": submission_id,
        "grade": grade,
        "return_to_student": return_to_student,
    }
    if not confirmed:
        return _ok({"requires_confirmation": True, "preview": preview})
    return _ok(
        classroom.grade_submission(
            course_id,
            course_work_id,
            submission_id,
            grade=grade,
            return_to_student=return_to_student,
        )
    )


# ---------------- SieWeb ----------------
@mcp.tool()
def sieweb_list_messages(folder_id: int = 1, search: str = "") -> str:
    """Lista mensajes de SieWeb. folder_id=1 corresponde a la bandeja observada."""
    return _ok(sieweb.list_messages(folder_id=folder_id, search=search))


@mcp.tool()
def sieweb_read_message(message_id: int, folder_id: int = 1) -> str:
    """Lee el detalle completo de un mensaje de SieWeb por ID."""
    return _ok(sieweb.get_message(message_id, folder_id=folder_id))


@mcp.tool()
def sieweb_reply_message(
    recipient_codes: list[str],
    subject: str,
    html_message: str,
    reply_to_message_id: int,
    confirmed: bool = False,
) -> str:
    """Responde un mensaje de SieWeb. Requiere confirmed=true después de confirmación."""
    preview = {
        "recipient_codes": recipient_codes,
        "subject": subject,
        "reply_to_message_id": reply_to_message_id,
        "html_message": html_message,
    }
    if not confirmed:
        return _ok({"requires_confirmation": True, "preview": preview})
    return _ok(
        sieweb.send_reply(
            recipient_codes=recipient_codes,
            subject=subject,
            html_message=html_message,
            reply_to_message_id=reply_to_message_id,
        )
    )


@mcp.tool()
def sieweb_get_gradebook(
    class_period_id: int,
    root_content_id: int,
    extra_params_json: str = "{}",
) -> str:
    """Lee el registro de notas. extra_params_json permite completar parámetros si SieWeb los exige."""
    extra = json.loads(extra_params_json or "{}")
    return _ok(
        sieweb.get_gradebook(
            class_period_id=class_period_id,
            root_content_id=root_content_id,
            extra_params=extra,
        )
    )


@mcp.tool()
def sieweb_update_grades(
    year: str,
    course_code: str,
    class_period_id: int,
    period: int,
    section_ng_json: str,
    records_json: str,
    class_name: str = "",
    confirmed: bool = False,
) -> str:
    """Actualiza una o varias notas de SieWeb. Requiere confirmación explícita."""
    section_ng = json.loads(section_ng_json)
    records = json.loads(records_json)
    preview = {
        "year": year,
        "course_code": course_code,
        "class_period_id": class_period_id,
        "period": period,
        "section_ng": section_ng,
        "records": records,
        "class_name": class_name,
    }
    if not confirmed:
        return _ok({"requires_confirmation": True, "preview": preview})
    return _ok(
        sieweb.update_grades(
            year=year,
            course_code=course_code,
            class_period_id=class_period_id,
            period=period,
            section_ng=section_ng,
            records=records,
            class_name=class_name or None,
            notify=bool(class_name),
        )
    )


@mcp.tool()
def sieweb_get_criteria(
    class_id: int,
    class_period_id: int,
    root_content_id: int,
    id_ambito: int = 518,
    extra_params_json: str = "{}",
) -> str:
    """Lee competencias, capacidades, desempeños y evidencias de SieWeb."""
    extra = json.loads(extra_params_json or "{}")
    return _ok(
        sieweb.get_criteria(
            class_id=class_id,
            class_period_id=class_period_id,
            root_content_id=root_content_id,
            id_ambito=id_ambito,
            extra_params=extra,
        )
    )


@mcp.tool()
def sieweb_upsert_criteria(
    class_id: int,
    records_json: str,
    replica_json: str,
    confirmed: bool = False,
) -> str:
    """Crea o edita criterios/desempeños usando HyoClaseContenido/insertar. Requiere confirmación."""
    records = json.loads(records_json)
    replica = json.loads(replica_json)
    preview = {"class_id": class_id, "records": records, "replica": replica}
    if not confirmed:
        return _ok({"requires_confirmation": True, "preview": preview})
    return _ok(sieweb.upsert_criteria(class_id=class_id, records=records, replica=replica))


@mcp.tool()
def sieweb_login_status() -> str:
    """Inicia/valida la sesión de SieWeb y devuelve un resumen seguro sin tokens."""
    return _ok(sieweb.login())


@mcp.tool()
def sieweb_get_conclusion(
    person_id: int,
    class_content_id: int,
    ng: str,
) -> str:
    """Lee la conclusión descriptiva de un alumno para un criterio de SieWeb."""
    return _ok(
        sieweb.get_conclusion(
            person_id=person_id,
            class_content_id=class_content_id,
            ng=ng,
        )
    )


@mcp.tool()
def sieweb_save_descriptive_conclusion(
    person_id: int,
    class_content_id: int,
    grade: str,
    did_well: str,
    needs_improvement: str,
    suggestion: str,
    confirmed: bool = False,
) -> str:
    """Guarda conclusión descriptiva SOLO para B/C y con 3 partes: logro, mejora y sugerencia."""
    grade_norm = (grade or "").strip().upper()
    if grade_norm not in {"B", "C"}:
        return _ok(
            {
                "error": "Las conclusiones descriptivas solo se permiten para estudiantes con B o C.",
                "grade": grade_norm,
            }
        )

    did_well = did_well.strip().rstrip(". ")
    needs_improvement = needs_improvement.strip().rstrip(". ")
    suggestion = suggestion.strip().rstrip(". ")
    if not did_well or not needs_improvement or not suggestion:
        return _ok(
            {
                "error": (
                    "Faltan partes de la conclusión. Debe incluir: lo que hizo bien, "
                    "lo que debe mejorar y una sugerencia para el estudiante."
                )
            }
        )

    comment = (
        f"Logra {did_well}. "
        f"Debe mejorar {needs_improvement}. "
        f"Se recomienda {suggestion}."
    )
    if len(comment) > 500:
        return _ok(
            {
                "error": "La conclusión supera el límite de 500 caracteres de SieWeb.",
                "characters": len(comment),
                "preview": comment,
            }
        )

    preview = {
        "person_id": person_id,
        "class_content_id": class_content_id,
        "grade": grade_norm,
        "characters": len(comment),
        "comment": comment,
    }
    if not confirmed:
        return _ok({"requires_confirmation": True, "preview": preview})

    return _ok(
        sieweb.update_conclusion(
            person_id=person_id,
            class_content_id=class_content_id,
            comment=comment,
            comment2="",
        )
    )


if __name__ == "__main__":
    mcp.run(transport="streamable-http")
