from __future__ import annotations

import json
from datetime import date, time
from typing import Any

from mcp.server.fastmcp import FastMCP, Image
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
        "identificadores estables devueltos por las herramientas. En Classroom distingue TAREA "
        "(courseWork) de MATERIAL DE CLASE (courseWorkMaterial): nunca sustituyas un material por "
        "una tarea. Puedes crear y publicar tareas, materiales y anuncios, y adjuntar archivos de "
        "Google Drive mediante su ID/URL o enlaces web. Si el usuario nombra un archivo de Drive sin "
        "dar ID/URL, usa el conector Google Drive de ChatGPT para resolverlo y después llama a la "
        "herramienta Classroom correspondiente. Para CALIFICACIONES distingue draftGrade (provisional) de assignedGrade "
        "(visible al alumno); devolver una entrega no finaliza automáticamente la nota en la API, así que usa las herramientas "
        "de finalización/devolución. Para CIEWEB/SIEWEB, sí puedes CREAR CORREOS NUEVOS y ENVIARLOS sin que exista un hilo previo: "
        "usa sieweb_messaging con action=compose_new para preparar y action=send_new para el envío real mediante "
        "HyoMensajeria/enviarMensaje. Para responder un hilo existente usa action=reply. No confundas correo nuevo con respuesta. Antes de cualquier escritura o acción destructiva, "
        "resume exactamente el cambio al usuario y solo ejecuta cuando haya autorizado ese cambio. Los comentarios privados de entregas no existen en la API oficial: "
        "no simules esa acción con anuncios ni otros recursos."
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


# ---------------- Google Classroom v0.6.2 ----------------
def _confirmation(preview: dict[str, Any], confirmed: bool, *, destructive: bool = False) -> str | None:
    if confirmed:
        return None
    return _ok({"requires_confirmation": True, "destructive": destructive, "preview": preview})


def _json_obj(raw: str, default: Any) -> Any:
    if raw is None or raw == "":
        return default
    value = json.loads(raw)
    return value


def _require_confirm(action: str, payload: dict[str, Any], confirmed: bool, *, destructive_actions: set[str], write_actions: set[str]) -> str | None:
    if action not in write_actions:
        return None
    return _confirmation({"action": action, **payload}, confirmed, destructive=action in destructive_actions)


@mcp.tool()
def classroom_capabilities() -> str:
    """Resume el control práctico de Classroom expuesto por este conector y los límites de la API oficial."""
    return _ok({
        "version": "0.6.2",
        "tool_design": "Acciones agrupadas por recurso para reducir errores de selección de herramienta.",
        "implemented": {
            "courses": ["list/get/create/update/delete", "aliases", "gradebookSettings", "gradingPeriodSettings"],
            "roster": ["students", "teachers", "invitations"],
            "topics": ["list/create/update/delete"],
            "announcements": ["list/get/create/publish/schedule/update/modifyAssignees/delete", "Drive/link attachments on create"],
            "coursework": [
                "assignments", "short-answer questions", "multiple-choice questions",
                "list/get/create/publish/schedule/update/modifyAssignees/delete",
                "due date/time", "max points", "topic", "grading period", "submission modification mode",
                "Drive/link attachments on create", "associatedWithDeveloper diagnostics",
            ],
            "materials": ["list/get/create/publish/schedule/update/delete", "Drive/link attachments on create"],
            "submissions": ["list/get", "state", "late", "draft/assigned grades", "rubric grades", "history", "missing/progress"],
            "submission_attachments": [
                "list Drive/link attachments", "download/export teacher-accessible Drive files",
                "extract text from PDF/DOCX/XLSX/PPTX/text", "render image/PDF pages for visual review",
                "create/list/reply/resolve Google Drive file comments"
            ],
            "grading": [
                "set draft grade", "set final grade", "grade and return", "batch grade", "return one/many",
                "attempt safe grade clearing", "diagnose write eligibility",
            ],
            "rubrics": ["list/get/create/update/delete", "read criterion grades from submissions"],
            "student_groups": ["list/create/update/delete", "list/add/remove members"],
            "profiles_guardians": ["user profile", "capability checks", "guardians list/get/delete", "guardian invitations list/get/create/cancel"],
        },
        "official_api_limits": {
            "private_submission_comments": "No hay endpoint oficial para leer o escribir comentarios privados nativos de una entrega. v0.6.2 ofrece comentarios en el archivo de Drive como canal de retroalimentación alternativo.",
            "stream_announcement_comments": "No hay endpoint oficial de Classroom para leer/escribir comentarios del tablón/anuncios. Sí se pueden crear, editar, programar y borrar anuncios.",
            "overall_course_grade": "La API no expone la nota global calculada como campo editable; puede calcularse localmente con datos disponibles.",
            "rubric_criterion_scores": "Los puntajes por criterio pueden leerse en StudentSubmission, pero no escribirse mediante la API.",
            "associated_project_rule": "Editar/eliminar CourseWork y modificar/devolver StudentSubmissions puede exigir que el trabajo haya sido creado por el mismo proyecto OAuth.",
            "normal_material_attachments_after_creation": "Los adjuntos normales de CourseWork no forman parte de los campos patchables de la API estable.",
            "grade_clear": "Google documenta actualización de draftGrade/assignedGrade, no un ejemplo explícito de borrado; el conector intenta FieldMask y si falla lo reporta sin inventar una alternativa.",
            "push_notifications": "La API soporta registrations hacia Google Cloud Pub/Sub, pero este paquete no activa ese flujo porque requiere configurar un topic Pub/Sub y un consumidor adicional.",
            "classroom_addon_attachments": "Los AddOnAttachments son una arquitectura de Classroom Add-ons distinta de los adjuntos Drive/link normales y requieren scopes/tokens específicos; no se habilitan en este MCP general.",
            "drive_scope": "Para revisar cualquier archivo entregado y crear comentarios en esos archivos, el refresh token debe incluir https://www.googleapis.com/auth/drive.",
        },
    })


@mcp.tool()
def classroom_google_auth_status() -> str:
    """Verifica scopes OAuth actuales sin exponer access/refresh tokens."""
    return _ok(classroom.oauth_scope_status())


@mcp.tool()
def classroom_courses(action: str, course_id: str = "", payload_json: str = "{}", confirmed: bool = False) -> str:
    """Cursos. action: list|get|gradebook_settings|create|update|delete|list_aliases|create_alias|delete_alias|get_grading_periods|update_grading_periods. payload_json lleva parámetros adicionales."""
    action = action.strip().lower()
    p = _json_obj(payload_json, {})
    writes = {"create", "update", "delete", "create_alias", "delete_alias", "update_grading_periods"}
    destructive = {"delete", "delete_alias"}
    pending = _require_confirm(action, {"course_id": course_id, "payload": p}, confirmed, destructive_actions=destructive, write_actions=writes)
    if pending: return pending
    if action == "list": return _ok(classroom.list_courses(active_only=bool(p.get("active_only", True))))
    if action == "get": return _ok(classroom.get_course(course_id))
    if action == "gradebook_settings":
        c = classroom.get_course(course_id); return _ok({"course_id": course_id, "gradebookSettings": c.get("gradebookSettings")})
    if action == "create": return _ok(classroom.create_course(
        name=p["name"], owner_id=p.get("owner_id", "me"), section=p.get("section", ""),
        description_heading=p.get("description_heading", ""), description=p.get("description", ""),
        room=p.get("room", ""), subject=p.get("subject", ""), course_state=p.get("course_state")))
    if action == "update": return _ok(classroom.update_course(course_id, p.get("updates", {}), clear_fields=p.get("clear_fields", [])))
    if action == "delete": return _ok(classroom.delete_course(course_id))
    if action == "list_aliases": return _ok(classroom.list_aliases(course_id))
    if action == "create_alias": return _ok(classroom.create_alias(course_id, p["alias"]))
    if action == "delete_alias": return _ok(classroom.delete_alias(course_id, p["alias"]))
    if action == "get_grading_periods": return _ok(classroom.get_grading_period_settings(course_id))
    if action == "update_grading_periods": return _ok(classroom.update_grading_period_settings(
        course_id, p.get("settings", p), update_mask=p.get("update_mask", "gradingPeriods,applyToExistingCoursework")))
    raise ValueError(f"Acción de cursos no soportada: {action}")


@mcp.tool()
def classroom_roster(action: str, course_id: str = "", user_id: str = "", invitation_id: str = "", payload_json: str = "{}", confirmed: bool = False) -> str:
    """Personas e invitaciones. action: list/get/add/remove_student|list/get/add/remove_teacher|get/list/create/delete/accept_invitation."""
    action = action.strip().lower(); p = _json_obj(payload_json, {})
    writes = {"add_student", "remove_student", "add_teacher", "remove_teacher", "create_invitation", "delete_invitation", "accept_invitation"}
    destructive = {"remove_student", "remove_teacher", "delete_invitation"}
    pending = _require_confirm(action, {"course_id": course_id, "user_id": user_id, "invitation_id": invitation_id, "payload": p}, confirmed, destructive_actions=destructive, write_actions=writes)
    if pending: return pending
    if action == "list_students": return _ok(classroom.list_students(course_id))
    if action == "get_student": return _ok(classroom.get_student(course_id, user_id))
    if action == "add_student": return _ok(classroom.add_student(course_id, user_id, p.get("enrollment_code")))
    if action == "remove_student": return _ok(classroom.remove_student(course_id, user_id))
    if action == "list_teachers": return _ok(classroom.list_teachers(course_id))
    if action == "get_teacher": return _ok(classroom.get_teacher(course_id, user_id))
    if action == "add_teacher": return _ok(classroom.add_teacher(course_id, user_id))
    if action == "remove_teacher": return _ok(classroom.remove_teacher(course_id, user_id))
    if action == "get_invitation": return _ok(classroom.get_invitation(invitation_id))
    if action == "list_invitations": return _ok(classroom.list_invitations(course_id=course_id or p.get("course_id"), user_id=user_id or p.get("user_id")))
    if action == "create_invitation": return _ok(classroom.create_invitation(course_id, user_id, p["role"]))
    if action == "delete_invitation": return _ok(classroom.delete_invitation(invitation_id))
    if action == "accept_invitation": return _ok(classroom.accept_invitation(invitation_id))
    raise ValueError(f"Acción de roster no soportada: {action}")


@mcp.tool()
def classroom_topics(action: str, course_id: str, topic_id: str = "", payload_json: str = "{}", confirmed: bool = False) -> str:
    """Temas. action: list|get|create|update|delete. payload_json usa name para create/update."""
    action = action.strip().lower(); p = _json_obj(payload_json, {})
    writes = {"create", "update", "delete"}; destructive = {"delete"}
    pending = _require_confirm(action, {"course_id": course_id, "topic_id": topic_id, "payload": p}, confirmed, destructive_actions=destructive, write_actions=writes)
    if pending: return pending
    if action == "list": return _ok(classroom.list_topics(course_id))
    if action == "get": return _ok(classroom.get_topic(course_id, topic_id))
    if action == "create": return _ok(classroom.create_topic(course_id, p["name"]))
    if action == "update": return _ok(classroom.update_topic(course_id, topic_id, p["name"]))
    if action == "delete": return _ok(classroom.delete_topic(course_id, topic_id))
    raise ValueError(f"Acción de topics no soportada: {action}")


@mcp.tool()
def classroom_announcements(action: str, course_id: str, announcement_id: str = "", payload_json: str = "{}", confirmed: bool = False) -> str:
    """Anuncios. action: list|get|create|update|modify_assignees|delete. create admite text,publish,materials,scheduled_time,student_ids."""
    action = action.strip().lower(); p = _json_obj(payload_json, {})
    writes = {"create", "update", "modify_assignees", "delete"}; destructive = {"delete"}
    pending = _require_confirm(action, {"course_id": course_id, "announcement_id": announcement_id, "payload": p}, confirmed, destructive_actions=destructive, write_actions=writes)
    if pending: return pending
    if action == "list": return _ok(classroom.list_announcements(course_id, include_drafts=bool(p.get("include_drafts", True))))
    if action == "get": return _ok(classroom.get_announcement(course_id, announcement_id))
    if action == "create": return _ok(classroom.create_announcement(
        course_id, text=p["text"], publish=bool(p.get("publish", False)), materials=p.get("materials", []),
        scheduled_time=p.get("scheduled_time"), student_ids=p.get("student_ids", [])))
    if action == "update": return _ok(classroom.patch_announcement(course_id, announcement_id, p.get("updates", {}), clear_fields=p.get("clear_fields", [])))
    if action == "modify_assignees": return _ok(classroom.modify_announcement_assignees(
        course_id, announcement_id, assignee_mode=p.get("assignee_mode", "ALL_STUDENTS"),
        add_student_ids=p.get("add_student_ids", []), remove_student_ids=p.get("remove_student_ids", [])))
    if action == "delete": return _ok(classroom.delete_announcement(course_id, announcement_id))
    raise ValueError(f"Acción de anuncios no soportada: {action}")


@mcp.tool()
def classroom_coursework(action: str, course_id: str, course_work_id: str = "", payload_json: str = "{}", confirmed: bool = False) -> str:
    """Tareas/preguntas. action: list|get|diagnose|create|update|modify_assignees|delete. create soporta ASSIGNMENT, SHORT_ANSWER_QUESTION y MULTIPLE_CHOICE_QUESTION, adjuntos, tema, fecha, puntos y publicación/programación."""
    action = action.strip().lower(); p = _json_obj(payload_json, {})
    writes = {"create", "update", "modify_assignees", "delete"}; destructive = {"delete"}
    pending = _require_confirm(action, {"course_id": course_id, "course_work_id": course_work_id, "payload": p}, confirmed, destructive_actions=destructive, write_actions=writes)
    if pending: return pending
    if action == "list": return _ok(classroom.list_coursework(course_id, include_drafts=bool(p.get("include_drafts", True))))
    if action == "get": return _ok(classroom.get_coursework(course_id, course_work_id))
    if action == "diagnose": return _ok(classroom.diagnose_coursework_control(course_id, course_work_id))
    if action == "create":
        due_date = date.fromisoformat(p["due_date"]) if p.get("due_date") else None
        due_time = time.fromisoformat(p["due_time"]) if p.get("due_time") else None
        return _ok(classroom.create_coursework_item(
            course_id, title=p["title"], description=p.get("description", ""), work_type=p.get("work_type", "ASSIGNMENT"),
            max_points=p.get("max_points"), due_date=due_date, due_time=due_time, topic_id=p.get("topic_id"),
            publish=bool(p.get("publish", False)), materials=p.get("materials", []), scheduled_time=p.get("scheduled_time"),
            student_ids=p.get("student_ids", []), multiple_choice_choices=p.get("multiple_choice_choices", []),
            submission_modification_mode=p.get("submission_modification_mode"), grading_period_id=p.get("grading_period_id")))
    if action == "update": return _ok(classroom.patch_coursework(course_id, course_work_id, p.get("updates", {}), clear_fields=p.get("clear_fields", [])))
    if action == "modify_assignees": return _ok(classroom.modify_coursework_assignees(
        course_id, course_work_id, assignee_mode=p.get("assignee_mode", "ALL_STUDENTS"),
        add_student_ids=p.get("add_student_ids", []), remove_student_ids=p.get("remove_student_ids", [])))
    if action == "delete": return _ok(classroom.delete_coursework(course_id, course_work_id))
    raise ValueError(f"Acción de coursework no soportada: {action}")


@mcp.tool()
def classroom_materials(action: str, course_id: str, material_id: str = "", payload_json: str = "{}", confirmed: bool = False) -> str:
    """Material de clase. action: list|get|create|update|delete. create admite title,description,materials(Drive/link),topic_id,publish,scheduled_time,student_ids."""
    action = action.strip().lower(); p = _json_obj(payload_json, {})
    writes = {"create", "update", "delete"}; destructive = {"delete"}
    pending = _require_confirm(action, {"course_id": course_id, "material_id": material_id, "payload": p}, confirmed, destructive_actions=destructive, write_actions=writes)
    if pending: return pending
    if action == "list": return _ok(classroom.list_coursework_materials(course_id, include_drafts=bool(p.get("include_drafts", True))))
    if action == "get": return _ok(classroom.get_coursework_material(course_id, material_id))
    if action == "create": return _ok(classroom.create_coursework_material(
        course_id, title=p["title"], description=p.get("description", ""), materials=p.get("materials", []),
        topic_id=p.get("topic_id"), publish=bool(p.get("publish", False)), scheduled_time=p.get("scheduled_time"),
        student_ids=p.get("student_ids", [])))
    if action == "update": return _ok(classroom.patch_coursework_material(course_id, material_id, p.get("updates", {}), clear_fields=p.get("clear_fields", [])))
    if action == "delete": return _ok(classroom.delete_coursework_material(course_id, material_id))
    raise ValueError(f"Acción de materiales no soportada: {action}")


@mcp.tool()
def classroom_submissions(action: str, course_id: str, course_work_id: str = "", submission_id: str = "", payload_json: str = "{}", confirmed: bool = False) -> str:
    """Entregas y archivos enviados. action: list|get|missing|course_progress|diagnose|files_list|inspect_text|comment_file|list_file_comments|reply_file_comment|resolve_file_comment. Para una foto/PDF visual usa classroom_attachment_image."""
    action = action.strip().lower(); p = _json_obj(payload_json, {})
    if action == "list": return _ok(classroom.list_submissions(course_id, course_work_id))
    if action == "get": return _ok(classroom.get_submission(course_id, course_work_id, submission_id))
    if action == "missing": return _ok(classroom.missing_students(course_id, course_work_id))
    if action == "course_progress": return _ok(classroom.course_progress(course_id, include_drafts=bool(p.get("include_drafts", False))))
    if action == "diagnose": return _ok(classroom.diagnose_coursework_control(course_id, course_work_id))

    file_action_map = {
        "files_list": "list",
        "inspect_text": "inspect_text",
        "comment_file": "comment",
        "list_file_comments": "list_comments",
        "reply_file_comment": "reply_comment",
        "resolve_file_comment": "resolve_comment",
    }
    if action in file_action_map:
        if not submission_id:
            raise ValueError("submission_id es obligatorio para revisar archivos entregados.")
        return classroom_submission_files(
            file_action_map[action],
            course_id,
            course_work_id,
            submission_id,
            attachment_index=int(p.get("attachment_index", 0)),
            payload_json=json.dumps(p, ensure_ascii=False),
            confirmed=confirmed,
        )
    raise ValueError(f"Acción de entregas no soportada: {action}")


@mcp.tool()
def classroom_grades(action: str, course_id: str, course_work_id: str, submission_id: str = "", payload_json: str = "{}", confirmed: bool = False) -> str:
    """Calificaciones y devoluciones. action: set_draft|set_final|grade_and_return|clear|return|batch_grade|batch_return. Siempre confirma antes de escribir."""
    action = action.strip().lower(); p = _json_obj(payload_json, {})
    writes = {"set_draft", "set_final", "grade_and_return", "clear", "return", "batch_grade", "batch_return"}
    destructive = {"clear"}
    pending = _require_confirm(action, {"course_id": course_id, "course_work_id": course_work_id, "submission_id": submission_id, "payload": p}, confirmed, destructive_actions=destructive, write_actions=writes)
    if pending: return pending
    if action == "set_draft": return _ok(classroom.patch_submission_grades(course_id, course_work_id, submission_id, draft_grade=float(p["grade"])))
    if action == "set_final": return _ok(classroom.patch_submission_grades(course_id, course_work_id, submission_id, draft_grade=float(p["grade"]), assigned_grade=float(p["grade"])))
    if action == "grade_and_return": return _ok(classroom.grade_submission(course_id, course_work_id, submission_id, grade=float(p["grade"]), return_to_student=True))
    if action == "clear": return _ok(classroom.clear_submission_grade(course_id, course_work_id, submission_id, which=p.get("which", "all")))
    if action == "return": return _ok(classroom.return_submission(course_id, course_work_id, submission_id, finalize_draft=bool(p.get("finalize_draft", True))))
    if action == "batch_grade": return _ok(classroom.batch_grade(course_id, course_work_id, p.get("grades", []), mode=p.get("mode", "final"), return_to_student=bool(p.get("return_to_student", False))))
    if action == "batch_return": return _ok(classroom.batch_return(course_id, course_work_id, [str(x) for x in p.get("submission_ids", [])], finalize_draft=bool(p.get("finalize_draft", True))))
    raise ValueError(f"Acción de calificaciones no soportada: {action}")


@mcp.tool()
def classroom_rubrics(action: str, course_id: str, course_work_id: str, rubric_id: str = "", payload_json: str = "{}", confirmed: bool = False) -> str:
    """Rúbricas. action: list|get|create|update|delete. La API no permite escribir puntajes por criterio en la entrega."""
    action = action.strip().lower(); p = _json_obj(payload_json, {})
    writes = {"create", "update", "delete"}; destructive = {"delete"}
    pending = _require_confirm(action, {"course_id": course_id, "course_work_id": course_work_id, "rubric_id": rubric_id, "payload": p}, confirmed, destructive_actions=destructive, write_actions=writes)
    if pending: return pending
    pv = p.get("preview_version")
    if action == "list": return _ok(classroom.list_rubrics(course_id, course_work_id, pv))
    if action == "get": return _ok(classroom.get_rubric(course_id, course_work_id, rubric_id, pv))
    if action == "create": return _ok(classroom.create_rubric(course_id, course_work_id, criteria=p.get("criteria", []), preview_version=pv))
    if action == "update": return _ok(classroom.update_rubric(course_id, course_work_id, rubric_id, criteria=p.get("criteria", []), preview_version=pv))
    if action == "delete": return _ok(classroom.delete_rubric(course_id, course_work_id, rubric_id, pv))
    raise ValueError(f"Acción de rúbricas no soportada: {action}")


@mcp.tool()
def classroom_student_groups(action: str, course_id: str, group_id: str = "", user_id: str = "", payload_json: str = "{}", confirmed: bool = False) -> str:
    """Grupos de estudiantes. action: list|create|update|delete|list_members|add_member|remove_member."""
    action = action.strip().lower(); p = _json_obj(payload_json, {})
    writes = {"create", "update", "delete", "add_member", "remove_member"}; destructive = {"delete", "remove_member"}
    pending = _require_confirm(action, {"course_id": course_id, "group_id": group_id, "user_id": user_id, "payload": p}, confirmed, destructive_actions=destructive, write_actions=writes)
    if pending: return pending
    pv = p.get("preview_version")
    if action == "list": return _ok(classroom.list_student_groups(course_id, pv))
    if action == "create": return _ok(classroom.create_student_group(course_id, p["title"], pv))
    if action == "update": return _ok(classroom.update_student_group(course_id, group_id, p["title"], pv))
    if action == "delete": return _ok(classroom.delete_student_group(course_id, group_id, pv))
    if action == "list_members": return _ok(classroom.list_student_group_members(course_id, group_id, pv))
    if action == "add_member": return _ok(classroom.add_student_group_member(course_id, group_id, user_id, pv))
    if action == "remove_member": return _ok(classroom.remove_student_group_member(course_id, group_id, user_id, pv))
    raise ValueError(f"Acción de grupos no soportada: {action}")



@mcp.tool()
def classroom_profiles_guardians(action: str, student_id: str = "", guardian_id: str = "", invitation_id: str = "", payload_json: str = "{}", confirmed: bool = False) -> str:
    """Perfiles y tutores. action: get_profile|check_capability|list_guardians|get_guardian|delete_guardian|list_invitations|get_invitation|create_invitation|cancel_invitation. Para administrar tutores se necesita scope guardianlinks.students."""
    action = action.strip().lower(); p = _json_obj(payload_json, {})
    writes = {"delete_guardian", "create_invitation", "cancel_invitation"}; destructive = {"delete_guardian", "cancel_invitation"}
    pending = _require_confirm(action, {"student_id": student_id, "guardian_id": guardian_id, "invitation_id": invitation_id, "payload": p}, confirmed, destructive_actions=destructive, write_actions=writes)
    if pending: return pending
    if action == "get_profile": return _ok(classroom.get_user_profile(p.get("user_id", student_id or "me")))
    if action == "check_capability": return _ok(classroom.check_user_capability(
        p["capability"], user_id=p.get("user_id", "me"), preview_version=p.get("preview_version", "V1_20240930_PREVIEW")))
    if action == "list_guardians": return _ok(classroom.list_guardians(student_id, invited_email_address=p.get("invited_email_address")))
    if action == "get_guardian": return _ok(classroom.get_guardian(student_id, guardian_id))
    if action == "delete_guardian": return _ok(classroom.delete_guardian(student_id, guardian_id))
    if action == "list_invitations": return _ok(classroom.list_guardian_invitations(
        student_id, invited_email_address=p.get("invited_email_address"), states=p.get("states")))
    if action == "get_invitation": return _ok(classroom.get_guardian_invitation(student_id, invitation_id))
    if action == "create_invitation": return _ok(classroom.create_guardian_invitation(student_id, p["invited_email_address"]))
    if action == "cancel_invitation": return _ok(classroom.cancel_guardian_invitation(student_id, invitation_id))
    raise ValueError(f"Acción de perfiles/tutores no soportada: {action}")

# ---- aliases de alta frecuencia para compatibilidad y selección robusta ----

def classroom_create_announcement(
    course_id: str,
    text: str,
    materials_json: str = "[]",
    publish: bool = False,
    scheduled_time: str | None = None,
    student_ids_json: str = "[]",
    confirmed: bool = False,
) -> str:
    """Crea una publicación de ANUNCIO en el tablón de Classroom. Admite archivos de Drive/enlaces al crear. Requiere confirmación."""
    materials = _json_obj(materials_json, [])
    student_ids = _json_obj(student_ids_json, [])
    preview = {
        "course_id": course_id,
        "text": text,
        "materials": materials,
        "publish": publish,
        "scheduled_time": scheduled_time,
        "student_ids": student_ids,
    }
    pending = _confirmation(preview, confirmed)
    if pending:
        return pending
    return _ok(classroom.create_announcement(
        course_id,
        text=text,
        publish=publish,
        materials=materials,
        scheduled_time=scheduled_time,
        student_ids=student_ids,
    ))


def classroom_submission_files(
    action: str,
    course_id: str,
    course_work_id: str,
    submission_id: str,
    attachment_index: int = 0,
    payload_json: str = "{}",
    confirmed: bool = False,
) -> str:
    """Archivos entregados y feedback sobre el archivo. action: list|inspect_text|comment|list_comments|reply_comment|resolve_comment. Los comentarios se escriben en Google Drive, NO como comentario privado nativo de Classroom."""
    action = action.strip().lower()
    p = _json_obj(payload_json, {})
    if action == "list":
        return _ok(classroom.list_submission_attachments(
            course_id, course_work_id, submission_id,
            include_drive_metadata=bool(p.get("include_drive_metadata", True)),
        ))
    if action == "inspect_text":
        return _ok(classroom.inspect_submission_attachment_text(
            course_id, course_work_id, submission_id, attachment_index,
            max_chars=int(p.get("max_chars", 50000)),
        ))

    # Operaciones de comentarios de Drive son escrituras y requieren confirmación.
    if action in {"comment", "reply_comment", "resolve_comment"} and not confirmed:
        return _ok({
            "requires_confirmation": True,
            "preview": {
                "action": action,
                "course_id": course_id,
                "course_work_id": course_work_id,
                "submission_id": submission_id,
                "attachment_index": attachment_index,
                "payload": p,
                "channel": "Google Drive file comments (not Classroom private comments)",
            },
        })

    if action == "comment":
        return _ok(classroom.comment_on_submission_attachment(
            course_id, course_work_id, submission_id, attachment_index, str(p["content"])
        ))

    attachment = classroom._submission_attachment(course_id, course_work_id, submission_id, attachment_index)
    drive = attachment.get("driveFile") or {}
    file_id = str(drive.get("id") or "")
    if not file_id:
        raise ValueError("El adjunto seleccionado no es un archivo de Drive.")
    if action == "list_comments":
        return _ok(classroom.list_drive_comments(file_id, include_deleted=bool(p.get("include_deleted", False))))
    if action == "reply_comment":
        return _ok(classroom.reply_drive_comment(file_id, str(p["comment_id"]), str(p.get("content") or ""), resolve=False))
    if action == "resolve_comment":
        return _ok(classroom.reply_drive_comment(file_id, str(p["comment_id"]), str(p.get("content") or ""), resolve=True))
    raise ValueError(f"Acción de archivos/feedback no soportada: {action}")


@mcp.tool(structured_output=False)
def classroom_attachment_image(
    course_id: str,
    course_work_id: str,
    submission_id: str,
    attachment_index: int = 0,
    page: int = 1,
    max_side: int = 1800,
) -> tuple[str, Image]:
    """Devuelve a ChatGPT una foto entregada por el alumno o una página renderizada de un PDF para revisión visual."""
    info, png = classroom.render_submission_attachment_image(
        course_id, course_work_id, submission_id, attachment_index,
        page=page, max_side=max_side,
    )
    return (_ok(info), Image(data=png, format="png"))

def classroom_list_courses(active_only: bool = True) -> str:
    """Lista cursos activos. Alias estable de lectura."""
    return _ok(classroom.list_courses(active_only=active_only))


def classroom_create_assignment(course_id: str, title: str, description: str = "", max_points: float | None = None,
                                due_date_iso: str | None = None, due_time_hhmm: str | None = None,
                                topic_id: str | None = None, publish: bool = False, materials_json: str = "[]",
                                confirmed: bool = False) -> str:
    """Crea una TAREA. Permite descripción y adjuntos Drive/link. Exige confirmación."""
    materials = _json_obj(materials_json, [])
    preview = {"course_id": course_id, "title": title, "description": description, "max_points": max_points,
               "due_date": due_date_iso, "due_time": due_time_hhmm, "topic_id": topic_id, "publish": publish, "materials": materials}
    pending = _confirmation(preview, confirmed)
    if pending: return pending
    return _ok(classroom.create_coursework_item(
        course_id, title=title, description=description, work_type="ASSIGNMENT", max_points=max_points,
        due_date=date.fromisoformat(due_date_iso) if due_date_iso else None,
        due_time=time.fromisoformat(due_time_hhmm) if due_time_hhmm else None,
        topic_id=topic_id, publish=publish, materials=materials))


def classroom_create_material(course_id: str, title: str, description: str = "", materials_json: str = "[]",
                              topic_id: str | None = None, publish: bool = False, confirmed: bool = False) -> str:
    """Crea una publicación real de MATERIAL DE CLASE con descripción y adjuntos Drive/link. Exige confirmación."""
    materials = _json_obj(materials_json, [])
    preview = {"course_id": course_id, "title": title, "description": description, "materials": materials, "topic_id": topic_id, "publish": publish}
    pending = _confirmation(preview, confirmed)
    if pending: return pending
    return _ok(classroom.create_coursework_material(course_id, title=title, description=description, materials=materials, topic_id=topic_id, publish=publish))


def classroom_list_submissions(course_id: str, course_work_id: str) -> str:
    """Lista entregas y notas de un trabajo. Alias estable de lectura."""
    return _ok(classroom.list_submissions(course_id, course_work_id))


def classroom_grade_submission(course_id: str, course_work_id: str, submission_id: str, grade: float,
                               return_to_student: bool = False, confirmed: bool = False) -> str:
    """Pone nota final (draftGrade+assignedGrade) y opcionalmente devuelve la entrega. Exige confirmación."""
    preview = {"course_id": course_id, "course_work_id": course_work_id, "submission_id": submission_id,
               "grade": grade, "return_to_student": return_to_student}
    pending = _confirmation(preview, confirmed)
    if pending: return pending
    return _ok(classroom.grade_submission(course_id, course_work_id, submission_id, grade=grade, return_to_student=return_to_student))


# ---------------- SieWeb ----------------

@mcp.tool()
def sieweb_messaging(action: str, payload_json: str = "{}", confirmed: bool = False) -> str:
    """Mensajería completa de SieWeb. action: capabilities|list|read|search_recipients|compose_new|send_new|reply. send_new CREA Y ENVÍA un correo nuevo sin hilo previo; reply responde uno existente. Escrituras requieren confirmed=true."""
    action = action.strip().lower(); p = _json_obj(payload_json, {})
    if action == "capabilities":
        return _ok({
            "version": "0.6.2",
            "list_inbox": True, "read_message": True, "reply_existing_message": True,
            "search_recipients": True, "compose_new_email": True, "send_new_email": True,
            "new_email_requires_existing_thread": False,
            "endpoint": "/lms/api/HyoMensajeria/enviarMensaje",
            "note": "send_new no usa idEdition ni response; crea y envía un mensaje nuevo de SieWeb."
        })
    if action == "list":
        return _ok(sieweb.list_messages(folder_id=int(p.get("folder_id", 1)), search=str(p.get("search", ""))))
    if action == "read":
        return _ok(sieweb.get_message(int(p["message_id"]), folder_id=int(p.get("folder_id", 1))))
    if action == "search_recipients":
        return _ok(sieweb.search_messaging_users(
            query=str(p.get("query", "")),
            recipient_type=str(p.get("recipient_type", "any")),
            ngs=str(p.get("ngs", "")),
            limit=int(p.get("limit", 30)),
        ))

    if action in {"compose_new", "send_new"}:
        codes, resolved, problem = _resolve_sieweb_email_recipients(
            p.get("recipient_codes") or [],
            str(p.get("recipient_query", "")),
            str(p.get("recipient_type", "any")),
            str(p.get("ngs", "")),
        )
        if problem: return _ok(problem)
        subject = str(p.get("subject", ""))
        message = str(p.get("message", p.get("html_message", "")))
        message_is_html = bool(p.get("message_is_html", bool(p.get("html_message"))))
        draft = sieweb.compose_message(
            recipient_codes=codes, subject=subject,
            html_message=message if message_is_html else "",
            plain_text="" if message_is_html else message,
        )
        if action == "compose_new":
            return _ok({
                "created": True, "sent": False, "type": "new_sieweb_email",
                "resolved_recipients": resolved, "draft": draft,
                "next_action": "Llama sieweb_messaging action=send_new con confirmed=true tras aprobación."
            })
        preview = {
            "type": "new_sieweb_email", "recipient_codes": codes,
            "resolved_recipients": resolved, "subject": draft["asunto"], "html_message": draft["mensaje"]
        }
        if not confirmed: return _ok({"requires_confirmation": True, "preview": preview})
        return _ok(sieweb.send_message(
            recipient_codes=codes, subject=subject,
            html_message=message if message_is_html else "",
            plain_text="" if message_is_html else message,
        ))

    if action == "reply":
        codes = [str(x).strip() for x in (p.get("recipient_codes") or []) if str(x).strip()]
        if not codes: raise ValueError("recipient_codes es obligatorio para responder un mensaje existente.")
        preview = {
            "recipient_codes": codes, "subject": str(p.get("subject", "")),
            "reply_to_message_id": int(p["reply_to_message_id"]),
            "html_message": str(p.get("html_message", p.get("message", ""))),
        }
        if not confirmed: return _ok({"requires_confirmation": True, "preview": preview})
        return _ok(sieweb.send_reply(
            recipient_codes=codes, subject=preview["subject"],
            html_message=preview["html_message"], reply_to_message_id=preview["reply_to_message_id"]
        ))
    raise ValueError(f"Acción de mensajería SieWeb no soportada: {action}")


@mcp.tool()
def sieweb_academics(action: str, payload_json: str = "{}", confirmed: bool = False) -> str:
    """Registro académico de SieWeb agrupado. action: login_status|resolve_class_context|gradebook|gradebook_by_section|gradebook_summary|find_students|find_criteria|get_criteria|upsert_criteria|update_grades|build_grade_records|get_conclusion|get_conclusions_batch|save_conclusion|save_conclusions_batch."""
    action = action.strip().lower(); p = _json_obj(payload_json, {})
    if action == "login_status": return sieweb_login_status()
    if action == "resolve_class_context": return sieweb_resolve_class_context(str(p["section"]), int(p["period"]), str(p.get("course_code", "05")), p.get("id_ambito"))
    if action == "gradebook": return sieweb_get_gradebook(int(p["class_period_id"]), int(p["root_content_id"]), json.dumps(p.get("extra_params", {}), ensure_ascii=False))
    if action == "gradebook_by_section": return sieweb_gradebook_by_section(str(p["section"]), int(p["period"]), str(p.get("course_code", "05")), p.get("id_ambito"), json.dumps(p.get("extra_params", {}), ensure_ascii=False))
    if action == "gradebook_summary": return sieweb_gradebook_summary(int(p["class_period_id"]), int(p["root_content_id"]), json.dumps(p.get("extra_params", {}), ensure_ascii=False))
    if action == "find_students": return sieweb_find_students(int(p["class_period_id"]), int(p["root_content_id"]), str(p["query"]), json.dumps(p.get("extra_params", {}), ensure_ascii=False))
    if action == "find_criteria": return sieweb_find_criteria(int(p["class_period_id"]), int(p["root_content_id"]), str(p["query"]), json.dumps(p.get("extra_params", {}), ensure_ascii=False))
    if action == "get_criteria": return sieweb_get_criteria(int(p["class_id"]), int(p["class_period_id"]), int(p["root_content_id"]), int(p.get("id_ambito", 518)), json.dumps(p.get("extra_params", {}), ensure_ascii=False))
    if action == "upsert_criteria": return sieweb_upsert_criteria(int(p["class_id"]), json.dumps(p.get("records", []), ensure_ascii=False), json.dumps(p.get("replica", {}), ensure_ascii=False), confirmed)
    if action == "update_grades": return sieweb_update_grades(str(p["year"]), str(p["course_code"]), int(p["class_period_id"]), int(p["period"]), json.dumps(p["section_ng"], ensure_ascii=False), json.dumps(p.get("records", []), ensure_ascii=False), str(p.get("class_name", "")), confirmed)
    if action == "build_grade_records": return sieweb_build_grade_records(int(p["class_period_id"]), int(p["root_content_id"]), int(p["header_id"]), json.dumps(p.get("grades_by_student_code", {}), ensure_ascii=False), json.dumps(p.get("extra_params", {}), ensure_ascii=False))
    if action == "get_conclusion": return sieweb_get_conclusion(int(p["person_id"]), int(p["class_content_id"]), str(p["ng"]))
    if action == "get_conclusions_batch": return sieweb_get_conclusions_batch(json.dumps(p.get("targets", []), ensure_ascii=False))
    if action == "save_conclusion": return sieweb_save_descriptive_conclusion(int(p["person_id"]), int(p["class_content_id"]), str(p["grade"]), str(p["did_well"]), str(p["needs_improvement"]), str(p["suggestion"]), confirmed)
    if action == "save_conclusions_batch": return sieweb_save_conclusions_batch(json.dumps(p.get("records", []), ensure_ascii=False), confirmed)
    raise ValueError(f"Acción académica SieWeb no soportada: {action}")


@mcp.tool()
def workflow_school(action: str, payload_json: str = "{}") -> str:
    """Flujos Classroom↔SieWeb. action: match_roster|missing_with_sieweb_ids|missing_to_sieweb_recipients."""
    action = action.strip().lower(); p = _json_obj(payload_json, {})
    extra = json.dumps(p.get("extra_params", {}), ensure_ascii=False)
    if action == "match_roster": return workflow_match_classroom_sieweb_roster(str(p["course_id"]), int(p["class_period_id"]), int(p["root_content_id"]), extra)
    if action == "missing_with_sieweb_ids": return workflow_missing_classroom_with_sieweb_ids(str(p["course_id"]), str(p["course_work_id"]), int(p["class_period_id"]), int(p["root_content_id"]), extra)
    if action == "missing_to_sieweb_recipients": return workflow_missing_classroom_to_sieweb_recipients(str(p["course_id"]), str(p["course_work_id"]), str(p["section"]), int(p["period"]), str(p.get("course_code", "05")), extra)
    raise ValueError(f"Flujo escolar no soportado: {action}")

def sieweb_list_messages(folder_id: int = 1, search: str = "") -> str:
    """Lista mensajes de SieWeb. folder_id=1 corresponde a la bandeja observada."""
    return _ok(sieweb.list_messages(folder_id=folder_id, search=search))


def sieweb_read_message(message_id: int, folder_id: int = 1) -> str:
    """Lee el detalle completo de un mensaje de SieWeb por ID."""
    return _ok(sieweb.get_message(message_id, folder_id=folder_id))


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


def sieweb_login_status() -> str:
    """Inicia/valida la sesión de SieWeb y devuelve un resumen seguro sin tokens."""
    return _ok(sieweb.login())


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

def sieweb_resolve_class_context(section: str, period: int, course_code: str = "05", id_ambito: int | None = None) -> str:
    """Resuelve 2.º A/5.º A + período a ID_CLASE, ID_CLASE_PERIODO e ID_CONTENIDO de SieWeb."""
    return _ok(sieweb.resolve_class_context(section=section, period=period, course_code=course_code, id_ambito=id_ambito))

def sieweb_gradebook_by_section(section: str, period: int, course_code: str = "05", id_ambito: int | None = None,
                                extra_params_json: str = "{}") -> str:
    """Lee el registro usando nombres naturales de sección/período; 05=Matemática."""
    ctx = sieweb.resolve_class_context(section=section, period=period, course_code=course_code, id_ambito=id_ambito)
    extra = json.loads(extra_params_json or "{}")
    extra.setdefault("idPeriodoAnt", ctx.get("idPeriodoAnt", 0))
    gradebook = sieweb.get_gradebook(
        class_period_id=ctx["idClasePeriodo"],
        root_content_id=ctx["idContenido"],
        extra_params=extra,
    )
    return _ok({"context": ctx, "gradebook": sieweb.summarize_gradebook(gradebook)})

def sieweb_capabilities() -> str:
    """Indica explícitamente las capacidades de CIEWEB/SIEWEB disponibles en esta versión."""
    return _ok({
        "version": "0.6.2",
        "messaging": {
            "list_inbox": True,
            "read_message": True,
            "reply_existing_message": True,
            "search_recipients": True,
            "create_new_email": True,
            "send_new_email": True,
            "new_email_requires_existing_thread": False,
            "new_email_endpoint": "/lms/api/HyoMensajeria/enviarMensaje",
            "recipient_directory_endpoint": "/lms/api/HyoUsuario/obtListaUsuariosIntranet?isMensajeria=true",
        },
        "note": "Un correo nuevo no usa idEdition ni response. SieWeb crea el registro definitivo al enviarlo.",
    })


def _resolve_sieweb_email_recipients(
    recipient_codes: list[str] | None,
    recipient_query: str,
    recipient_type: str,
    ngs: str,
) -> tuple[list[str], list[dict[str, Any]], dict[str, Any] | None]:
    codes = [str(x).strip() for x in (recipient_codes or []) if str(x).strip()]
    resolved: list[dict[str, Any]] = []
    if codes:
        return codes, resolved, None
    if not recipient_query.strip():
        return [], [], {"error": "Debes proporcionar recipient_codes o recipient_query."}
    resolved = sieweb.search_messaging_users(
        query=recipient_query, recipient_type=recipient_type, ngs=ngs, limit=30
    )
    if len(resolved) != 1:
        return [], resolved, {
            "requires_recipient_selection": True,
            "query": recipient_query,
            "recipient_type": recipient_type,
            "ngs": ngs,
            "matches": resolved,
            "note": "Selecciona exactamente un USUCOD o vuelve a llamar con recipient_codes.",
        }
    return [str(resolved[0].get("USUCOD") or "")], resolved, None


def sieweb_create_email(
    subject: str,
    message: str,
    recipient_codes: list[str] | None = None,
    recipient_query: str = "",
    recipient_type: str = "any",
    ngs: str = "",
    message_is_html: bool = False,
) -> str:
    """CREA/COMPONE un correo NUEVO de CIEWEB/SIEWEB sin enviarlo. Puede resolver el destinatario por nombre. Devuelve el payload exacto listo para enviar; no necesita un mensaje previo."""
    codes, resolved, problem = _resolve_sieweb_email_recipients(
        recipient_codes, recipient_query, recipient_type, ngs
    )
    if problem:
        return _ok(problem)
    payload = sieweb.compose_message(
        recipient_codes=codes,
        subject=subject,
        html_message=message if message_is_html else "",
        plain_text="" if message_is_html else message,
    )
    return _ok({
        "created": True,
        "sent": False,
        "type": "new_sieweb_email",
        "resolved_recipients": resolved,
        "draft": payload,
        "next_action": "Para enviarlo llama a sieweb_send_new_email con los mismos destinatarios/asunto/mensaje y confirmed=true después de la aprobación del usuario.",
    })


def sieweb_send_new_email(
    subject: str,
    message: str,
    recipient_codes: list[str] | None = None,
    recipient_query: str = "",
    recipient_type: str = "any",
    ngs: str = "",
    message_is_html: bool = False,
    confirmed: bool = False,
) -> str:
    """ENVÍA un correo NUEVO de CIEWEB/SIEWEB. No es respuesta a un hilo. Resuelve destinatarios por nombre o USUCOD y usa el endpoint real enviarMensaje. Requiere confirmed=true para escribir."""
    codes, resolved, problem = _resolve_sieweb_email_recipients(
        recipient_codes, recipient_query, recipient_type, ngs
    )
    if problem:
        return _ok(problem)
    payload = sieweb.compose_message(
        recipient_codes=codes,
        subject=subject,
        html_message=message if message_is_html else "",
        plain_text="" if message_is_html else message,
    )
    preview = {
        "type": "new_sieweb_email",
        "recipient_codes": codes,
        "resolved_recipients": resolved,
        "subject": payload["asunto"],
        "html_message": payload["mensaje"],
    }
    if not confirmed:
        return _ok({"requires_confirmation": True, "preview": preview})
    return _ok(sieweb.send_message(
        recipient_codes=codes,
        subject=subject,
        html_message=message if message_is_html else "",
        plain_text="" if message_is_html else message,
    ))


def sieweb_search_recipients(query: str, recipient_type: str = "any", ngs: str = "", limit: int = 30) -> str:
    """Busca destinatarios de Mensajería. recipient_type: student/alumno, family/familia, teacher/docente o any."""
    return _ok(sieweb.search_messaging_users(query=query, recipient_type=recipient_type, ngs=ngs, limit=limit))

def sieweb_send_message(recipient_codes: list[str], subject: str, html_message: str,
                        confirmed: bool = False) -> str:
    """Compatibilidad: envía un mensaje NUEVO en SieWeb. Preferir sieweb_send_new_email para nuevos correos."""
    preview = {"recipient_codes": recipient_codes, "subject": subject, "html_message": html_message}
    if not confirmed:
        return _ok({"requires_confirmation": True, "preview": preview})
    return _ok(sieweb.send_message(recipient_codes=recipient_codes, subject=subject, html_message=html_message))


def sieweb_new_message(
    subject: str,
    html_message: str,
    recipient_codes: list[str] | None = None,
    recipient_query: str = "",
    recipient_type: str = "any",
    ngs: str = "",
    confirmed: bool = False,
) -> str:
    """Compatibilidad: crea/envía un mensaje NUEVO. Preferir sieweb_create_email + sieweb_send_new_email."""
    codes = [str(x).strip() for x in (recipient_codes or []) if str(x).strip()]
    resolved = []
    if not codes and recipient_query.strip():
        resolved = sieweb.search_messaging_users(
            query=recipient_query, recipient_type=recipient_type, ngs=ngs, limit=20
        )
        if len(resolved) != 1:
            return _ok({
                "requires_recipient_selection": True,
                "query": recipient_query,
                "recipient_type": recipient_type,
                "ngs": ngs,
                "matches": resolved,
                "note": "Selecciona exactamente un USUCOD o vuelve a llamar con recipient_codes.",
            })
        codes = [str(resolved[0].get("USUCOD") or "")]
    if not codes:
        raise ValueError("Debes proporcionar recipient_codes o recipient_query.")
    preview = {
        "recipient_codes": codes,
        "resolved_recipients": resolved,
        "subject": subject,
        "html_message": html_message,
        "type": "new_sieweb_message",
    }
    if not confirmed:
        return _ok({"requires_confirmation": True, "preview": preview})
    return _ok(sieweb.send_message(recipient_codes=codes, subject=subject, html_message=html_message))

# ---------------- SieWeb ampliado ----------------
def sieweb_gradebook_summary(class_period_id: int, root_content_id: int, extra_params_json: str = "{}") -> str:
    """Devuelve contexto de clase, alumnos, criterios, IDs y notas en una forma compacta."""
    extra = json.loads(extra_params_json or "{}")
    return _ok(sieweb.get_gradebook_summary(class_period_id=class_period_id, root_content_id=root_content_id, extra_params=extra))

def sieweb_find_students(class_period_id: int, root_content_id: int, query: str, extra_params_json: str = "{}") -> str:
    """Busca alumnos en el registro de SieWeb por nombre o código."""
    extra = json.loads(extra_params_json or "{}")
    summary = sieweb.get_gradebook_summary(class_period_id=class_period_id, root_content_id=root_content_id, extra_params=extra)
    return _ok(sieweb.find_students_in_gradebook(summary, query))

def sieweb_find_criteria(class_period_id: int, root_content_id: int, query: str, extra_params_json: str = "{}") -> str:
    """Busca competencias/capacidades/desempeños por texto o ID dentro del registro."""
    extra = json.loads(extra_params_json or "{}")
    summary = sieweb.get_gradebook_summary(class_period_id=class_period_id, root_content_id=root_content_id, extra_params=extra)
    return _ok(sieweb.find_criteria_in_gradebook(summary, query))

def sieweb_get_conclusions_batch(targets_json: str) -> str:
    """Lee conclusiones de varios alumnos/criterios. targets=[{person_id,class_content_id,ng}]."""
    return _ok(sieweb.get_conclusions_batch(json.loads(targets_json or "[]")))

def sieweb_save_conclusions_batch(records_json: str, confirmed: bool = False) -> str:
    """Guarda varias conclusiones B/C; cada record incluye comment ya estructurado. Requiere confirmación."""
    records = json.loads(records_json or "[]")
    # validación previa de estructura mínima
    bad = []
    for r in records:
        grade = str(r.get("grade") or "").upper()
        comment = str(r.get("comment") or "")
        if grade not in {"B","C"} or not comment or len(comment) > 500:
            bad.append({"record": r, "reason": "grade debe ser B/C y comment debe tener 1-500 caracteres"})
    if bad:
        return _ok({"error": "Hay conclusiones inválidas.", "invalid": bad})
    if not confirmed:
        return _ok({"requires_confirmation": True, "preview": records})
    return _ok(sieweb.update_conclusions_batch(records))

def sieweb_build_grade_records(class_period_id: int, root_content_id: int, header_id: int,
                               grades_by_student_code_json: str, extra_params_json: str = "{}") -> str:
    """Construye registros de HyoClasenota/actualizar desde {codigoAlumno: nota}, sin escribir todavía."""
    extra = json.loads(extra_params_json or "{}")
    grade_map = json.loads(grades_by_student_code_json or "{}")
    summary = sieweb.get_gradebook_summary(class_period_id=class_period_id, root_content_id=root_content_id, extra_params=extra)
    return _ok(sieweb.build_grade_records(summary, header_id=header_id, grades_by_student_code={str(k): str(v) for k,v in grade_map.items()}))

# ---------------- Flujos Classroom <-> SieWeb ----------------
def workflow_match_classroom_sieweb_roster(course_id: str, class_period_id: int, root_content_id: int,
                                           extra_params_json: str = "{}") -> str:
    """Cruza alumnos de Classroom con SieWeb por el código del correo institucional (antes de @) vs alucod."""
    extra = json.loads(extra_params_json or "{}")
    c_students = classroom.list_students(course_id)
    summary = sieweb.get_gradebook_summary(class_period_id=class_period_id, root_content_id=root_content_id, extra_params=extra)
    s_by_code = {str(s.get("alucod") or ""): s for s in summary.get("students") or []}
    matched, unmatched_classroom = [], []
    for cs in c_students:
        email = str(cs.get("email") or "")
        code = email.split("@", 1)[0] if "@" in email else ""
        sw = s_by_code.get(code)
        if sw:
            matched.append({"code": code, "classroom": cs, "sieweb": {k: sw.get(k) for k in ("idPersona","alucod","nomcomp","ngs","nemo","numord")}})
        else:
            unmatched_classroom.append(cs)
    matched_codes = {m["code"] for m in matched}
    unmatched_sieweb = [{k:s.get(k) for k in ("idPersona","alucod","nomcomp","ngs","nemo","numord")} for s in summary.get("students") or [] if str(s.get("alucod") or "") not in matched_codes]
    return _ok({"matched": matched, "unmatched_classroom": unmatched_classroom, "unmatched_sieweb": unmatched_sieweb, "counts": {"matched": len(matched), "classroom_only": len(unmatched_classroom), "sieweb_only": len(unmatched_sieweb)}})

def workflow_missing_classroom_with_sieweb_ids(course_id: str, course_work_id: str,
                                               class_period_id: int, root_content_id: int,
                                               extra_params_json: str = "{}") -> str:
    """Devuelve quienes no entregaron en Classroom y, cuando se puede, su idPersona/alucod/ngs de SieWeb."""
    extra = json.loads(extra_params_json or "{}")
    missing = classroom.missing_students(course_id, course_work_id)
    summary = sieweb.get_gradebook_summary(class_period_id=class_period_id, root_content_id=root_content_id, extra_params=extra)
    s_by_code = {str(s.get("alucod") or ""): s for s in summary.get("students") or []}
    out = []
    for cs in missing:
        email = str(cs.get("email") or "")
        code = email.split("@", 1)[0] if "@" in email else ""
        sw = s_by_code.get(code)
        out.append({"code": code, "classroom": cs, "sieweb": ({k: sw.get(k) for k in ("idPersona","alucod","nomcomp","ngs","nemo","numord")} if sw else None)})
    return _ok({"missing": out, "count": len(out), "matched_to_sieweb": sum(1 for x in out if x["sieweb"])})


def workflow_missing_classroom_to_sieweb_recipients(course_id: str, course_work_id: str,
                                                     section: str, period: int,
                                                     course_code: str = "05",
                                                     extra_params_json: str = "{}") -> str:
    """Cruza pendientes de Classroom con el registro y el USUCOD de mensajería del alumno en SieWeb."""
    ctx = sieweb.resolve_class_context(section=section, period=period, course_code=course_code)
    extra = json.loads(extra_params_json or "{}")
    missing = classroom.missing_students(course_id, course_work_id)
    extra.setdefault("idPeriodoAnt", ctx.get("idPeriodoAnt", 0))
    summary = sieweb.get_gradebook_summary(
        class_period_id=ctx["idClasePeriodo"], root_content_id=ctx["idContenido"], extra_params=extra
    )
    s_by_code = {str(st.get("alucod") or ""): st for st in summary.get("students") or []}
    directory = sieweb.list_messaging_users().get("json") or []
    msg_by_code = {}
    for row in directory:
        code = str(row.get("USUCOD") or "")
        if not code or str(row.get("TIPCOD") or "") != "005":
            continue
        prev = msg_by_code.get(code)
        if prev is None or (row.get("NGS") and not prev.get("NGS")):
            msg_by_code[code] = row
    out = []
    for cs in missing:
        email = str(cs.get("email") or "")
        alucod = email.split("@", 1)[0] if "@" in email else ""
        sw = s_by_code.get(alucod)
        recipient = msg_by_code.get("A" + alucod) if alucod else None
        out.append({
            "code": alucod,
            "classroom": cs,
            "sieweb": ({k: sw.get(k) for k in ("idPersona", "alucod", "nomcomp", "ngs", "nemo", "numord")} if sw else None),
            "messaging_student": recipient,
        })
    return _ok({"context": ctx, "missing": out, "count": len(out),
                "with_student_recipient": sum(1 for x in out if x["messaging_student"])})


if __name__ == "__main__":
    mcp.run(transport="streamable-http")
