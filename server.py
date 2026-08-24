from __future__ import annotations

import json
import secrets
from datetime import date, time
from typing import Any
from urllib.parse import urlsplit

from mcp.server.fastmcp import FastMCP, Image
from mcp.server.auth.settings import AuthSettings
from pydantic import AnyHttpUrl

from auth import Auth0TokenVerifier

from classroom import ClassroomClient, ClassroomError
from config import settings
from sieweb import SieWebClient
from bridge import ClassroomBridgeQueue
from starlette.requests import Request
from starlette.responses import JSONResponse

if not settings.auth0_issuer or not settings.auth0_audience:
    raise RuntimeError(
        "Falta configurar AUTH0_ISSUER y AUTH0_AUDIENCE. "
        "El servidor remoto se niega a iniciar sin autenticación OAuth."
    )

mcp = FastMCP(
    "SieRoom SRC",
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
        "de finalización/devolución. Para CIEWEB/SIEWEB, sí puedes CREAR CORREOS NUEVOS y ENVIARLOS sin que exista un hilo previo. "
        "Soporta tanto la herramienta agrupada sieweb_messaging como los nombres de compatibilidad "
        "sieweb_list_messages, sieweb_read_message, sieweb_search_recipients, sieweb_create_email, "
        "sieweb_send_new_email y sieweb_reply_message. Para correo nuevo usa sieweb_create_email para preparar "
        "y sieweb_send_new_email para enviar, o sieweb_messaging action=compose_new/send_new. El envío real usa "
        "HyoMensajeria/enviarMensaje. Para responder un hilo existente usa action=reply. No confundas correo nuevo con respuesta. "
        "Para PADRES/FAMILIAS DE SECCIONES COMPLETAS (por ejemplo 2.º A y 2.º B), NO uses resolve_class_context, idClase ni idAmbito: "
        "usa sieweb_resolve_family_group para previsualizar o sieweb_send_section_email para enviar. Esas acciones resuelven directamente "
        "NGS -> alumnos TIPCOD=005 -> familias TIPCOD=004 desde el directorio de Mensajería. "
        "Para GUARDAR NOTAS EN SIEWEB usa preferentemente sieweb_academics action=save_grades_verified: esa acción relee la matrícula real, "
        "preserva la estructura original de cada celda, detiene el lote si falta un alumno/desempeño y verifica la persistencia después del PUT. "
        "Para transferir una calificación oficial de Classroom a un desempeño SIEweb usa workflow_school action=classroom_grades_to_sieweb; "
        "ese flujo bloquea Nivel de Logro y solo admite desempeños nivelEva=3. Para replicar desempeños entre secciones usa action=replicate_performances (v0.7.15 reproduce el modal oficial, lee la matrícula completa sin el falso filtro individual y nunca reintenta un POST ambiguo): "
        "debe resolver los IDs internos de cada sección por separado y nunca copiar IDs de 2.º A a 2.º B. "
        "No construyas manualmente registros mínimos para HyoClasenota/actualizar. Antes de cualquier escritura o acción destructiva, "
        "resume exactamente el cambio al usuario y solo ejecuta cuando haya autorizado ese cambio. "
        "Los comentarios privados nativos de entregas se manejan mediante el puente local de navegador SieRoom Classroom Bridge; "
        "no se guardan cookies ni tokens de Google en Render. Para un flujo de retroalimentación privada usa classroom_private_feedback. "
        "v0.8.3 permite leer y publicar comentarios privados, calificar y devolver bajo una cuenta docente verificada y confirma la entrega destino. "
        "Si se solicita comentar, calificar y devolver, primero prepara/revisa la retroalimentación, luego encola el comentario privado y deja que el puente lo publique; "
        "solo después el servidor aplica la nota/devolución oficial configurada para ese trabajo."
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
bridge_queue = ClassroomBridgeQueue()



def _bridge_auth_ok(request: Request) -> bool:
    expected = str(settings.classroom_bridge_secret or "")
    provided = str(request.headers.get("x-sieroom-bridge-secret") or "")
    return bool(expected) and bool(provided) and secrets.compare_digest(expected, provided)


def _bridge_unauthorized() -> JSONResponse:
    return JSONResponse({"ok": False, "error": "bridge_unauthorized"}, status_code=401)


def _normalized_classroom_path(value: Any) -> str | None:
    """Compara destinos de Classroom ignorando authuser y el prefijo /u/N."""
    try:
        parsed = urlsplit(str(value or ""))
    except Exception:
        return None
    if parsed.hostname != "classroom.google.com":
        return None
    parts = [part for part in parsed.path.split("/") if part]
    if len(parts) >= 2 and parts[0] == "u" and parts[1].isdigit():
        parts = parts[2:]
    return "/" + "/".join(parts)


def _classroom_target_matches(actual_url: Any, expected_url: Any) -> bool:
    actual = _normalized_classroom_path(actual_url)
    expected = _normalized_classroom_path(expected_url)
    return bool(actual and expected and actual == expected)


@mcp.custom_route("/bridge/v1/status", methods=["GET"])
async def classroom_bridge_http_status(request: Request):
    if not _bridge_auth_ok(request):
        return _bridge_unauthorized()
    return JSONResponse({
        "ok": True,
        "version": "0.8.3",
        "bridge": "SieRoom Classroom Bridge",
        "queue": bridge_queue.stats(),
    })


@mcp.custom_route("/bridge/v1/reset", methods=["POST"])
async def classroom_bridge_http_reset(request: Request):
    """Desatasca trabajos reclamados por una pestaña/puente que quedó colgado.

    No elimina los trabajos `queued` ni el historial. Por defecto solo devuelve
    `claimed` a `queued`. `retry_failed=true` es opcional y explícito.
    """
    if not _bridge_auth_ok(request):
        return _bridge_unauthorized()
    try:
        body = await request.json()
    except Exception:
        body = {}
    retry_failed = bool((body or {}).get("retry_failed", False))
    result = bridge_queue.reset_active(retry_failed=retry_failed)
    return JSONResponse({
        **result,
        "version": "0.8.3",
        "message": "Cola desatascada. Los trabajos activos se conservaron y pueden procesarse de nuevo.",
    })


@mcp.custom_route("/bridge/v1/next", methods=["GET"])
async def classroom_bridge_http_next(request: Request):
    if not _bridge_auth_ok(request):
        return _bridge_unauthorized()
    raw_capabilities = str(request.headers.get("X-SieRoom-Bridge-Capabilities") or "")
    capabilities = {
        item.strip().lower()
        for item in raw_capabilities.split(",")
        if item.strip()
    }
    allowed_operations = {"post_private_comment"}
    verified_read_capability = "verified_private_comment_read_v3"
    read_capable = (
        "read_private_comments" in capabilities
        and verified_read_capability in capabilities
    )
    if read_capable:
        allowed_operations.add("read_private_comments")
    job = bridge_queue.next_job(allowed_operations=allowed_operations)
    if not job:
        read_waiting = bridge_queue.has_queued_operation("read_private_comments")
        return JSONResponse({
            "ok": True,
            "job": None,
            "read_waiting_for_compatible_bridge": bool(
                read_waiting and not read_capable
            ),
            "required_capability": (
                verified_read_capability
                if read_waiting and not read_capable
                else None
            ),
        })
    return JSONResponse({"ok": True, "job": job.public()})


@mcp.custom_route("/bridge/v1/jobs/{job_id}/complete", methods=["POST"])
async def classroom_bridge_http_complete(request: Request):
    if not _bridge_auth_ok(request):
        return _bridge_unauthorized()
    job_id = str(request.path_params.get("job_id") or "")
    job = bridge_queue.get(job_id)
    if not job:
        return JSONResponse({"ok": False, "error": "job_not_found"}, status_code=404)
    try:
        body = await request.json()
    except Exception:
        body = {}
    if job.operation == "read_private_comments":
        result = body if isinstance(body, dict) else {}
        comments = result.get("comments")
        count = result.get("count")
        method = str(result.get("method") or "")
        private_section_verified = result.get("private_section_verified") is True
        structured_fallback_verified = result.get("structured_fallback_verified") is True
        target_verified = _classroom_target_matches(
            result.get("url"), job.submission_url
        )
        ui_only_texts = {
            "instrucciones",
            "trabajo de los alumnos",
            "more_vert",
            "more_vert más opciones",
            "más opciones",
        }

        valid_comments = isinstance(comments, list)
        if valid_comments:
            for comment in comments:
                if not isinstance(comment, dict):
                    valid_comments = False
                    break
                text = " ".join(str(comment.get("text") or "").split()).strip()
                markers = comment.get("markers")
                structured = comment.get("structuredFeedback")
                if (
                    not text
                    or text.lower() in ui_only_texts
                    or not isinstance(markers, list)
                    or any(not isinstance(marker, str) for marker in markers)
                    or not isinstance(structured, bool)
                ):
                    valid_comments = False
                    break

        valid_source = private_section_verified
        if structured_fallback_verified:
            valid_source = bool(comments) and all(
                isinstance(comment, dict)
                and comment.get("structuredFeedback") is True
                and len(comment.get("markers") or []) >= 2
                for comment in comments
            )
        valid_read_result = (
            result.get("ok") is True
            and result.get("operation") == "read_private_comments"
            and method == "dom-v0.8.3-read"
            and target_verified
            and valid_comments
            and valid_source
            and isinstance(count, int)
            and not isinstance(count, bool)
            and count == len(comments)
        )
        if not valid_read_result:
            incompatible = result.get("ok") is True
            failed = bridge_queue.mark_failed(
                job_id,
                str(
                    result.get("error")
                    or (
                        (
                            "bridge_target_mismatch: la lectura no corresponde a la entrega solicitada."
                            if result.get("url") and not target_verified
                            else "bridge_incompatible_read_result: actualiza y recarga SieRoom Bridge v0.8.3."
                        )
                        if incompatible
                        else "El puente no pudo leer los comentarios privados."
                    )
                ),
                bridge_result=result,
            )
            return JSONResponse({"ok": False, "job": failed.public()}, status_code=409)
        done = bridge_queue.mark_completed(job_id, bridge_result=result)
        return JSONResponse({"ok": True, "job": done.public()})
    result = body if isinstance(body, dict) else {}
    if result.get("browser_followup_done") is True:
        validation_errors: list[str] = []
        if not _classroom_target_matches(result.get("url"), job.submission_url):
            validation_errors.append("entrega_distinta")
        comment_result = result.get("comment") if isinstance(result.get("comment"), dict) else {}
        if job.comment and comment_result.get("ok") is not True:
            validation_errors.append("comentario_no_confirmado")
        if job.grade is not None:
            if result.get("browser_grade_applied") is not True:
                validation_errors.append("nota_no_confirmada")
            else:
                try:
                    if abs(float(result.get("browser_grade")) - float(job.grade)) > 1e-9:
                        validation_errors.append("nota_distinta")
                except (TypeError, ValueError):
                    validation_errors.append("nota_invalida")
        if job.return_after_comment and result.get("browser_returned") is not True:
            validation_errors.append("devolucion_no_confirmada")
        if validation_errors:
            failed = bridge_queue.mark_failed(
                job_id,
                "browser_followup_incomplete: " + ",".join(validation_errors),
                bridge_result=result,
            )
            return JSONResponse({"ok": False, "job": failed.public()}, status_code=409)
        done = bridge_queue.mark_completed(
            job_id,
            bridge_result=result,
            classroom_result={
                "mode": "local_browser",
                "teacher_account_guard": True,
                "grade_applied": bool(result.get("browser_grade_applied")),
                "returned": bool(result.get("browser_returned")),
            },
        )
        return JSONResponse({"ok": True, "job": done.public()})

    bridge_queue.mark_comment_posted(job_id, bridge_result=result)
    followup: dict[str, Any] = {}
    try:
        if job.grade is not None:
            followup["grade_and_return"] = classroom.grade_submission(
                job.course_id, job.course_work_id, job.submission_id,
                grade=job.grade, return_to_student=job.return_after_comment,
            )
        elif job.return_after_comment:
            followup["return"] = classroom.return_submission(
                job.course_id, job.course_work_id, job.submission_id, finalize_draft=True
            )
        done = bridge_queue.mark_completed(job_id, classroom_result=followup)
        return JSONResponse({"ok": True, "job": done.public()})
    except Exception as exc:
        partial = bridge_queue.mark_partial_failure(job_id, str(exc), classroom_result=followup)
        return JSONResponse({"ok": False, "partial": True, "job": partial.public()}, status_code=207)


@mcp.custom_route("/bridge/v1/jobs/{job_id}/fail", methods=["POST"])
async def classroom_bridge_http_fail(request: Request):
    if not _bridge_auth_ok(request):
        return _bridge_unauthorized()
    job_id = str(request.path_params.get("job_id") or "")
    job = bridge_queue.get(job_id)
    if not job:
        return JSONResponse({"ok": False, "error": "job_not_found"}, status_code=404)
    try:
        body = await request.json()
    except Exception:
        body = {}
    default_error = (
        "El puente no pudo leer los comentarios privados."
        if job.operation == "read_private_comments"
        else "El puente no pudo publicar el comentario privado."
    )
    error = str((body or {}).get("error") or default_error)
    failed = bridge_queue.mark_failed(job_id, error, bridge_result=body if isinstance(body, dict) else {})
    return JSONResponse({"ok": True, "job": failed.public()})


def _ok(data: Any) -> str:
    return json.dumps(data, ensure_ascii=False, default=str)


# ---------------- Google Classroom v0.7.3 ----------------
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


# ---------------- SieWeb: herramientas explícitas de compatibilidad v0.7.3 ----------------
# Estas herramientas se registran al inicio para que clientes que conservaron nombres de
# versiones anteriores no reciban "Unknown tool" después de un deploy/reconexión.

@mcp.tool()
def sieweb_capabilities() -> str:
    """Capacidades de mensajería SieWeb. Confirma lectura, respuesta y creación/envío de correos nuevos."""
    return _ok({
        "version": "0.8.3",
        "list_inbox": True,
        "read_message": True,
        "reply_existing_message": True,
        "search_recipients": True,
        "create_new_email": True,
        "send_new_email": True,
        "new_email_requires_existing_thread": False,
        "new_email_endpoint": "/lms/api/HyoMensajeria/enviarMensaje",
        "resolve_families_by_section": True,
        "send_mass_email_by_section": True,
        "section_group_requires_class_ids": False,
        "compatibility_aliases": [
            "sieweb_list_messages", "sieweb_read_message", "sieweb_search_recipients",
            "sieweb_create_email", "sieweb_send_new_email", "sieweb_reply_message",
            "sieweb_resolve_family_group", "sieweb_send_section_email", "sieweb_messaging"
        ],
    })


@mcp.tool()
def sieweb_list_messages(folder_id: int = 1, search: str = "") -> str:
    """Lista mensajes de SieWeb. Herramienta explícita mantenida por compatibilidad."""
    return _ok(sieweb.list_messages(folder_id=folder_id, search=search))


@mcp.tool()
def sieweb_read_message(message_id: int, folder_id: int = 1) -> str:
    """Lee un mensaje de SieWeb por ID. Herramienta explícita mantenida por compatibilidad."""
    return _ok(sieweb.get_message(message_id, folder_id=folder_id))


@mcp.tool()
def sieweb_search_recipients(query: str, recipient_type: str = "any", ngs: str = "", limit: int = 30) -> str:
    """Busca destinatarios de SieWeb por nombre/código. Si la consulta pide padres/familias de secciones completas (p. ej. 2.º A y 2.º B), resuelve el grupo directamente por NGS; NO requiere idClase ni idAmbito."""
    sections = sieweb.extract_section_codes(query)
    direct_type = str(recipient_type or "").strip().lower()
    qn = sieweb._normalize_text(query)
    family_group = bool(sections) and (
        direct_type in {"family", "familia", "parent", "apoderado"}
        or any(word in qn for word in ("PADRES", "FAMILIA", "FAMILIAS", "APODERADOS"))
    )
    if family_group:
        group = sieweb.resolve_family_recipients_by_sections(sections)
        return _ok({
            "mode": "family_group_by_section",
            "requires_class_context": False,
            **group,
        })
    return _ok(sieweb.search_messaging_users(query=query, recipient_type=recipient_type, ngs=ngs, limit=limit))


@mcp.tool()
def sieweb_resolve_family_group(sections: list[str] | None = None, query: str = "") -> str:
    """Resuelve TODOS los destinatarios familia de una o varias secciones (ej. ['2A','2B']). Usa exclusivamente el directorio de Mensajería: NGS de alumnos TIPCOD=005 y usuarios familia TIPCOD=004. No necesita ni acepta idClase/idAmbito. No envía nada."""
    wanted: list[str] = []
    for item in (sections or []):
        code = sieweb._normalize_section(str(item))
        if code and code not in wanted:
            wanted.append(code)
    for code in sieweb.extract_section_codes(query):
        if code not in wanted:
            wanted.append(code)
    if not wanted:
        return _ok({
            "error": "Indica al menos una sección, por ejemplo 2A y 2B.",
            "requires_class_context": False,
        })
    group = sieweb.resolve_family_recipients_by_sections(wanted)
    return _ok({
        "mode": "family_group_by_section",
        "requires_class_context": False,
        **group,
    })


@mcp.tool()
def sieweb_send_section_email(
    sections: list[str],
    subject: str,
    message: str,
    message_is_html: bool = False,
    confirmed: bool = False,
) -> str:
    """Prepara o ENVÍA un correo NUEVO masivo a todas las familias de las secciones indicadas. Ej.: sections=['2A','2B']. Resuelve NGS->alumnos->familias dentro del directorio de Mensajería y jamás pide idClase/idAmbito. Con confirmed=false solo muestra la previsualización; confirmed=true envía un único mensaje masivo."""
    group = sieweb.resolve_family_recipients_by_sections(sections)
    if not group.get("complete") or not group.get("recipient_codes"):
        return _ok({
            "sent": False,
            "requires_recipient_review": True,
            "requires_class_context": False,
            "group_resolution": group,
            "note": "No se envía hasta que todas las familias estén resueltas sin ambigüedad.",
        })
    codes = list(group["recipient_codes"])
    payload = sieweb.compose_message(
        recipient_codes=codes,
        subject=subject,
        html_message=message if message_is_html else "",
        plain_text="" if message_is_html else message,
    )
    preview = {
        "type": "new_sieweb_section_email",
        "sections": group.get("sections"),
        "students_found": group.get("students_found"),
        "unique_family_recipients": group.get("recipient_count"),
        "per_section": group.get("per_section"),
        "recipient_codes": codes,
        "subject": payload["asunto"],
        "html_message": payload["mensaje"],
        "requires_class_context": False,
    }
    if not confirmed:
        return _ok({"requires_confirmation": True, "preview": preview})
    result = sieweb.send_message(
        recipient_codes=codes,
        subject=subject,
        html_message=message if message_is_html else "",
        plain_text="" if message_is_html else message,
    )
    return _ok({
        "sent": True,
        "sections": group.get("sections"),
        "unique_family_recipients": group.get("recipient_count"),
        "per_section": group.get("per_section"),
        "sieweb_result": result,
    })


@mcp.tool()
def sieweb_create_email(
    subject: str,
    message: str,
    recipient_codes: list[str] | None = None,
    recipient_query: str = "",
    recipient_type: str = "any",
    ngs: str = "",
    message_is_html: bool = False,
) -> str:
    """Compone un correo NUEVO en SieWeb sin enviarlo. No requiere hilo previo."""
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
        "next_action": "Tras aprobación, usa sieweb_send_new_email con confirmed=true.",
    })


@mcp.tool()
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
    """Crea Y ENVÍA un correo NUEVO en SieWeb. No requiere hilo previo. Requiere confirmed=true."""
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


@mcp.tool()
def sieweb_reply_message(
    reply_to_message_id: int,
    html_message: str,
    recipient_codes: list[str] | None = None,
    subject: str = "",
    folder_id: int = 1,
    confirmed: bool = False,
) -> str:
    """Responde un hilo existente de SieWeb. Relee el mensaje original y requiere confirmed=true."""
    prepared = sieweb.prepare_reply(
        reply_to_message_id=reply_to_message_id,
        html_message=html_message,
        recipient_codes=recipient_codes,
        subject=subject,
        folder_id=folder_id,
    )
    preview = {
        "recipient_codes": prepared["recipients"],
        "subject": prepared["subject"],
        "reply_to_message_id": prepared["reply_to_message_id"],
        "edition_id": prepared["edition_id"],
        "edition_id_source": prepared["edition_id_source"],
        "html_message": html_message,
    }
    if not confirmed:
        return _ok({"requires_confirmation": True, "preview": preview})
    return _ok(sieweb.send_reply(
        recipient_codes=prepared["recipients"],
        subject=prepared["subject"],
        html_message=html_message,
        reply_to_message_id=reply_to_message_id,
        folder_id=folder_id,
    ))


@mcp.tool()
def classroom_capabilities() -> str:
    """Resume el control práctico de Classroom expuesto por este conector y los límites de la API oficial."""
    return _ok({
        "version": "0.8.3",
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
            "private_feedback_bridge": [
                "read one/all existing private comments through the local browser",
                "queue private native comment", "browser posts in Classroom UI",
                "optional final grade", "optional return after comment",
            ],
            "rubrics": ["list/get/create/update/delete", "read criterion grades from submissions"],
            "student_groups": ["list/create/update/delete", "list/add/remove members"],
            "profiles_guardians": ["user profile", "capability checks", "guardians list/get/delete", "guardian invitations list/get/create/cancel"],
        },
        "official_api_limits": {
            "private_submission_comments": "La API oficial no expone lectura/escritura de comentarios privados. v0.8.3 usa un puente local con lectura verificada, negociación de capacidades, guardia de correo docente y verificación de la entrega destino, sin enviar cookies de Google a Render.",
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
def classroom_private_feedback(
    action: str,
    course_id: str = "",
    course_work_id: str = "",
    submission_id: str = "",
    comment: str = "",
    grade: float | None = None,
    return_after_comment: bool = False,
    job_id: str = "",
    payload_json: str = "{}",
    confirmed: bool = False,
) -> str:
    """Comentarios privados nativos mediante SieRoom Classroom Bridge. action: status|read|read_all|queue|queue_batch|job|list|reset|retry|cancel. read/read_all recuperan comentarios existentes desde la interfaz autenticada. reset desatasca trabajos claimed y conserva los pendientes. queue puede además aplicar grade y devolver DESPUÉS de que el navegador confirme que publicó el comentario. No guarda cookies/tokens de Google en Render."""
    action = action.strip().lower()
    p = _json_obj(payload_json, {})
    if action == "status":
        return _ok({
            "version": "0.8.3",
            "bridge_configured": bool(settings.classroom_bridge_secret),
            "bridge_endpoint": f"{settings.public_base_url}/bridge/v1",
            "queue": bridge_queue.stats(),
            "mode": "local_browser_bridge",
            "google_session_stored_on_render": False,
            "read_private_comments": True,
            "note": "El puente v0.8.3 debe estar abierto en Chrome y configurado con el correo docente correcto de Classroom.",
        })
    if action == "job":
        job = bridge_queue.get(job_id)
        return _ok(job.public() if job else {"error": "job_not_found", "job_id": job_id})
    if action == "list":
        jobs = bridge_queue.recent(int(p.get("limit", 100)))
        if p.get("operation"):
            jobs = [j for j in jobs if j.operation == str(p["operation"])]
        if course_id:
            jobs = [j for j in jobs if j.course_id == str(course_id)]
        if course_work_id:
            jobs = [j for j in jobs if j.course_work_id == str(course_work_id)]
        if p.get("status"):
            jobs = [j for j in jobs if j.status == str(p["status"])]
        return _ok({"jobs": [j.public() for j in jobs], "queue": bridge_queue.stats()})
    if action == "reset":
        retry_failed = bool(p.get("retry_failed", False))
        if not confirmed:
            return _ok({
                "requires_confirmation": True,
                "preview": {
                    "action": "reset_bridge_queue",
                    "retry_failed": retry_failed,
                    "preserve_queued": True,
                    "note": "Libera trabajos claimed atascados sin borrar la cola pendiente.",
                },
            })
        return _ok(bridge_queue.reset_active(retry_failed=retry_failed))
    if action == "retry":
        if not confirmed:
            return _ok({"requires_confirmation": True, "preview": {"action": "retry", "job_id": job_id}})
        job = bridge_queue.retry(job_id)
        return _ok(job.public())
    if action == "cancel":
        if not confirmed:
            return _ok({"requires_confirmation": True, "preview": {"action": "cancel", "job_id": job_id}})
        job = bridge_queue.cancel(job_id)
        return _ok(job.public())
    if action in {"read", "read_all"}:
        if not settings.classroom_bridge_secret:
            return _ok({
                "error": "CLASSROOM_BRIDGE_SECRET no está configurado en Render.",
                "bridge_configured": False,
                "next_step": "Configura CLASSROOM_BRIDGE_SECRET y el mismo valor en la extensión SieRoom Classroom Bridge.",
            })
        prepared: list[tuple[str, str, str, str]] = []
        if action == "read":
            sub = classroom.get_submission(course_id, course_work_id, submission_id)
            url = str(sub.get("alternateLink") or "")
            if not url:
                raise ClassroomError("Classroom no devolvió alternateLink para esta entrega; el puente necesita ese vínculo web.")
            prepared.append((str(course_id), str(course_work_id), str(submission_id), url))
        else:
            if not course_id or not course_work_id:
                raise ValueError("read_all requiere course_id y course_work_id.")
            for sub in classroom.list_submissions(course_id, course_work_id):
                sid = str(sub.get("id") or "")
                url = str(sub.get("alternateLink") or "")
                if sid and url:
                    prepared.append((str(course_id), str(course_work_id), sid, url))
            if not prepared:
                raise ClassroomError("La tarea no devolvió entregas con alternateLink para leer.")
        preview = {
            "action": "read_private_comments" if action == "read" else "read_all_private_comments",
            "count": len(prepared),
            "course_id": str(course_id),
            "course_work_id": str(course_work_id),
            "submission_ids": [row[2] for row in prepared],
            "sequence": ["open_submission_in_local_browser", "read_private_comment_panel", "return_comments_to_sieroom"],
            "no_classroom_write": True,
        }
        if not confirmed:
            return _ok({"requires_confirmation": True, "preview": preview})
        jobs = [
            bridge_queue.enqueue(
                course_id=cid,
                course_work_id=cwid,
                submission_id=sid,
                submission_url=url,
                operation="read_private_comments",
            ).public()
            for cid, cwid, sid, url in prepared
        ]
        return _ok({"queued": True, "operation": "read_private_comments", "count": len(jobs), "jobs": jobs})
    if action == "queue":
        if not settings.classroom_bridge_secret:
            return _ok({
                "error": "CLASSROOM_BRIDGE_SECRET no está configurado en Render.",
                "bridge_configured": False,
                "next_step": "Configura CLASSROOM_BRIDGE_SECRET y el mismo valor en la extensión SieRoom Classroom Bridge.",
            })
        sub = classroom.get_submission(course_id, course_work_id, submission_id)
        url = str(sub.get("alternateLink") or "")
        if not url:
            raise ClassroomError("Classroom no devolvió alternateLink para esta entrega; el puente necesita ese vínculo web.")
        preview = {
            "action": "queue_private_comment",
            "course_id": course_id,
            "course_work_id": course_work_id,
            "submission_id": submission_id,
            "submission_url": url,
            "comment": comment,
            "grade": grade,
            "return_after_comment": return_after_comment,
            "sequence": ["post_private_comment_in_browser", "apply_grade_if_requested", "return_submission_if_requested"],
            "experimental": True,
        }
        if not confirmed:
            return _ok({"requires_confirmation": True, "preview": preview})
        job = bridge_queue.enqueue(
            course_id=course_id, course_work_id=course_work_id, submission_id=submission_id,
            submission_url=url, comment=comment, grade=grade, return_after_comment=return_after_comment,
        )
        return _ok({"queued": True, "job": job.public()})
    if action == "queue_batch":
        items = p.get("items") or []
        if not isinstance(items, list) or not items:
            raise ValueError("payload_json debe contener items: [...] para queue_batch.")
        previews = []
        prepared = []
        for row in items:
            cid = str(row.get("course_id") or course_id)
            cwid = str(row.get("course_work_id") or course_work_id)
            sid = str(row.get("submission_id") or "")
            text = str(row.get("comment") or "").strip()
            row_grade = row.get("grade")
            row_return = bool(row.get("return_after_comment", return_after_comment))
            sub = classroom.get_submission(cid, cwid, sid)
            url = str(sub.get("alternateLink") or "")
            if not url:
                raise ClassroomError(f"La entrega {sid} no tiene alternateLink.")
            previews.append({"course_id": cid, "course_work_id": cwid, "submission_id": sid, "comment": text, "grade": row_grade, "return_after_comment": row_return})
            prepared.append((cid, cwid, sid, url, text, row_grade, row_return))
        if not confirmed:
            return _ok({"requires_confirmation": True, "preview": {"action": "queue_batch", "count": len(previews), "items": previews}})
        jobs = []
        for cid, cwid, sid, url, text, row_grade, row_return in prepared:
            jobs.append(bridge_queue.enqueue(
                course_id=cid, course_work_id=cwid, submission_id=sid, submission_url=url,
                comment=text, grade=row_grade, return_after_comment=row_return,
            ).public())
        return _ok({"queued": True, "count": len(jobs), "jobs": jobs})
    raise ValueError(f"Acción de comentarios privados no soportada: {action}")


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
    """Mensajería completa de SieWeb. action: capabilities|list|read|search_recipients|compose_new|send_new|prepare_reply|reply. send_new CREA Y ENVÍA un correo nuevo sin hilo previo; reply responde uno existente. Escrituras requieren confirmed=true."""
    action = action.strip().lower(); p = _json_obj(payload_json, {})
    if action == "capabilities":
        return _ok({
            "version": "0.8.3",
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

    if action in {"prepare_reply", "reply"}:
        message_id = int(p.get("reply_to_message_id", p.get("message_id", 0)))
        html_message = str(p.get("html_message", p.get("message", "")))
        folder_id = int(p.get("folder_id", 1))
        prepared = sieweb.prepare_reply(
            reply_to_message_id=message_id,
            html_message=html_message,
            recipient_codes=p.get("recipient_codes") or None,
            subject=str(p.get("subject", "")),
            folder_id=folder_id,
        )
        preview = {
            "recipient_codes": prepared["recipients"],
            "subject": prepared["subject"],
            "reply_to_message_id": prepared["reply_to_message_id"],
            "edition_id": prepared["edition_id"],
            "edition_id_source": prepared["edition_id_source"],
            "html_message": html_message,
        }
        if action == "prepare_reply":
            return _ok({"prepared": True, "sent": False, "preview": preview})
        if not confirmed:
            return _ok({"requires_confirmation": True, "preview": preview})
        return _ok(sieweb.send_reply(
            recipient_codes=prepared["recipients"],
            subject=prepared["subject"],
            html_message=html_message,
            reply_to_message_id=message_id,
            folder_id=folder_id,
        ))
    raise ValueError(f"Acción de mensajería SieWeb no soportada: {action}")


@mcp.tool()
def sieweb_academics(action: str, payload_json: str = "{}", confirmed: bool = False) -> str:
    """Registro académico de SieWeb agrupado. action: login_status|resolve_class_context|gradebook|gradebook_by_section|gradebook_summary|find_students|find_criteria|get_criteria|criteria_write_preflight|upsert_criteria_verified|build_grade_records|save_grades_verified|update_grades|get_conclusion|get_conclusions_batch|save_conclusion|save_conclusions_batch. v0.7.15 crea desempeños con el contrato nativo del modal y lee la matrícula completa sin objInfoRegIndividual[alucod]=False; verifica Competencia→Capacidad→Desempeño y bloquea Nivel de Logro. Para notas nuevas prefiere save_grades_verified."""
    action = action.strip().lower(); p = _json_obj(payload_json, {})
    if action == "login_status": return sieweb_login_status()
    if action == "resolve_class_context": return sieweb_resolve_class_context(str(p["section"]), int(p["period"]), str(p.get("course_code", "05")), p.get("id_ambito"))
    if action == "gradebook": return sieweb_get_gradebook(int(p["class_period_id"]), int(p["root_content_id"]), json.dumps(p.get("extra_params", {}), ensure_ascii=False))
    if action == "gradebook_by_section": return sieweb_gradebook_by_section(str(p["section"]), int(p["period"]), str(p.get("course_code", "05")), p.get("id_ambito"), json.dumps(p.get("extra_params", {}), ensure_ascii=False))
    if action == "gradebook_summary": return sieweb_gradebook_summary(int(p["class_period_id"]), int(p["root_content_id"]), json.dumps(p.get("extra_params", {}), ensure_ascii=False))
    if action == "find_students": return sieweb_find_students(int(p["class_period_id"]), int(p["root_content_id"]), str(p["query"]), json.dumps(p.get("extra_params", {}), ensure_ascii=False))
    if action == "find_criteria": return sieweb_find_criteria(int(p["class_period_id"]), int(p["root_content_id"]), str(p["query"]), json.dumps(p.get("extra_params", {}), ensure_ascii=False))
    if action == "get_criteria": return sieweb_get_criteria(int(p["class_id"]), int(p["class_period_id"]), int(p["root_content_id"]), int(p.get("id_ambito", 518)), json.dumps(p.get("extra_params", {}), ensure_ascii=False))
    if action == "criteria_write_preflight":
        if p.get("id_ambito") in (None, ""):
            return _ok({"error":"v0.7.15 requiere id_ambito explícito para el preflight de escritura; resuelve primero la sección con resolve_class_context.","blocked":True})
        return sieweb_criteria_write_preflight(int(p["class_id"]), int(p["class_period_id"]), int(p["root_content_id"]), int(p["id_ambito"]), json.dumps(p.get("extra_params", {}), ensure_ascii=False))
    if action == "upsert_criteria":
        return _ok({"error":"ACCIÓN LEGADA DESHABILITADA EN v0.7.15: upsert_criteria no reproduce el modal oficial. Usa criteria_write_preflight y upsert_criteria_verified con id_ambito explícito.","blocked":True})
    if action == "upsert_criteria_verified":
        if p.get("id_ambito") in (None, ""):
            return _ok({"error":"v0.7.15 bloqueó la escritura porque falta id_ambito. No se usará un ámbito silencioso de otra sección.","blocked":True})
        return sieweb_upsert_criteria_verified_tool(int(p["class_id"]), int(p["class_period_id"]), int(p["root_content_id"]), int(p["id_ambito"]), json.dumps(p.get("records", []), ensure_ascii=False), json.dumps(p.get("expected", []), ensure_ascii=False), json.dumps(p.get("replica", {}), ensure_ascii=False), json.dumps(p.get("extra_params", {}), ensure_ascii=False), confirmed)
    if action == "save_grades_verified": return sieweb_save_grades_verified(str(p["year"]), str(p["course_code"]), int(p["class_period_id"]), int(p["root_content_id"]), int(p["period"]), json.dumps(p["section_ng"], ensure_ascii=False), int(p["header_id"]), json.dumps(p.get("grades_by_student_code", {}), ensure_ascii=False), str(p.get("class_name", "")), json.dumps(p.get("extra_params", {}), ensure_ascii=False), confirmed)
    if action == "update_grades": return sieweb_update_grades(str(p["year"]), str(p["course_code"]), int(p["class_period_id"]), int(p["period"]), json.dumps(p["section_ng"], ensure_ascii=False), json.dumps(p.get("records", []), ensure_ascii=False), str(p.get("class_name", "")), confirmed)
    if action == "build_grade_records": return sieweb_build_grade_records(int(p["class_period_id"]), int(p["root_content_id"]), int(p["header_id"]), json.dumps(p.get("grades_by_student_code", {}), ensure_ascii=False), json.dumps(p.get("extra_params", {}), ensure_ascii=False))
    if action == "get_conclusion": return sieweb_get_conclusion(int(p["person_id"]), int(p["class_content_id"]), str(p["ng"]))
    if action == "get_conclusions_batch": return sieweb_get_conclusions_batch(json.dumps(p.get("targets", []), ensure_ascii=False))
    if action == "save_conclusion": return sieweb_save_descriptive_conclusion(int(p["person_id"]), int(p["class_content_id"]), str(p["grade"]), str(p["did_well"]), str(p["needs_improvement"]), str(p["suggestion"]), confirmed)
    if action == "save_conclusions_batch": return sieweb_save_conclusions_batch(json.dumps(p.get("records", []), ensure_ascii=False), confirmed)
    raise ValueError(f"Acción académica SieWeb no soportada: {action}")


@mcp.tool()
def workflow_school(action: str, payload_json: str = "{}") -> str:
    """Flujos Classroom↔SieWeb. action: match_roster|missing_with_sieweb_ids|missing_to_sieweb_recipients|classroom_grades_to_sieweb|replicate_performances."""
    action = action.strip().lower(); p = _json_obj(payload_json, {})
    extra = json.dumps(p.get("extra_params", {}), ensure_ascii=False)
    if action == "match_roster": return workflow_match_classroom_sieweb_roster(str(p["course_id"]), int(p["class_period_id"]), int(p["root_content_id"]), extra)
    if action == "missing_with_sieweb_ids": return workflow_missing_classroom_with_sieweb_ids(str(p["course_id"]), str(p["course_work_id"]), int(p["class_period_id"]), int(p["root_content_id"]), extra)
    if action == "missing_to_sieweb_recipients": return workflow_missing_classroom_to_sieweb_recipients(str(p["course_id"]), str(p["course_work_id"]), str(p["section"]), int(p["period"]), str(p.get("course_code", "05")), extra)
    if action == "classroom_grades_to_sieweb": return workflow_classroom_grades_to_sieweb(p)
    if action == "replicate_performances": return workflow_replicate_performances(p)
    raise ValueError(f"Flujo escolar no soportado: {action}")

def sieweb_list_messages(folder_id: int = 1, search: str = "") -> str:
    """Lista mensajes de SieWeb. folder_id=1 corresponde a la bandeja observada."""
    return _ok(sieweb.list_messages(folder_id=folder_id, search=search))


def sieweb_read_message(message_id: int, folder_id: int = 1) -> str:
    """Lee el detalle completo de un mensaje de SieWeb por ID."""
    return _ok(sieweb.get_message(message_id, folder_id=folder_id))


def sieweb_reply_message(
    reply_to_message_id: int,
    html_message: str,
    recipient_codes: list[str] | None = None,
    subject: str = "",
    folder_id: int = 1,
    confirmed: bool = False,
) -> str:
    """Alias de compatibilidad para responder un mensaje de SieWeb."""
    prepared = sieweb.prepare_reply(
        reply_to_message_id=reply_to_message_id,
        html_message=html_message,
        recipient_codes=recipient_codes,
        subject=subject,
        folder_id=folder_id,
    )
    preview = {
        "recipient_codes": prepared["recipients"],
        "subject": prepared["subject"],
        "reply_to_message_id": prepared["reply_to_message_id"],
        "edition_id": prepared["edition_id"],
        "edition_id_source": prepared["edition_id_source"],
        "html_message": html_message,
    }
    if not confirmed:
        return _ok({"requires_confirmation": True, "preview": preview})
    return _ok(
        sieweb.send_reply(
            recipient_codes=prepared["recipients"],
            subject=prepared["subject"],
            html_message=html_message,
            reply_to_message_id=reply_to_message_id,
            folder_id=folder_id,
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


def sieweb_save_grades_verified(
    year: str,
    course_code: str,
    class_period_id: int,
    root_content_id: int,
    period: int,
    section_ng_json: str,
    header_id: int,
    grades_by_student_code_json: str,
    class_name: str = "",
    extra_params_json: str = "{}",
    confirmed: bool = False,
) -> str:
    """Guarda notas SIEweb desde la matrícula real y verifica persistencia. Requiere confirmed=true."""
    section_ng = json.loads(section_ng_json or "[]")
    grade_map = {
        str(k).strip(): str(v).strip().upper()
        for k, v in json.loads(grades_by_student_code_json or "{}").items()
        if str(k).strip()
    }
    extra = json.loads(extra_params_json or "{}")
    if not grade_map:
        raise ValueError("grades_by_student_code no puede estar vacío.")

    summary = sieweb.get_gradebook_summary(
        class_period_id=class_period_id,
        root_content_id=root_content_id,
        extra_params=extra,
    )
    records = sieweb.build_grade_records(
        summary,
        header_id=header_id,
        grades_by_student_code=grade_map,
    )
    preview = {
        "year": year,
        "course_code": course_code,
        "class_period_id": class_period_id,
        "root_content_id": root_content_id,
        "period": period,
        "header_id": header_id,
        "section_ng": section_ng,
        "class_name": class_name,
        "requested_count": len(grade_map),
        "prepared_count": len(records),
        "changes": [
            {
                "alucod": str(record.get("alucod") or ""),
                "idPersona": record.get("idPersona"),
                "idNota": record.get("idNota"),
                "notaNue": record.get("notaNue"),
                "preserved_fields": sorted(record.keys()),
            }
            for record in records
        ],
    }
    if not confirmed:
        return _ok({
            "requires_confirmation": True,
            "safe_mode": "save_grades_verified",
            "preview": preview,
        })

    return _ok(
        sieweb.save_grades_verified(
            year=year,
            course_code=course_code,
            class_period_id=class_period_id,
            root_content_id=root_content_id,
            period=period,
            section_ng=section_ng,
            header_id=header_id,
            grades_by_student_code=grade_map,
            class_name=class_name or None,
            extra_params=extra,
            notify=bool(class_name),
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
    """Actualiza notas con registros ya construidos (bajo nivel). Para un guardado nuevo usa save_grades_verified. Requiere confirmación explícita."""
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
        "version": "0.8.3",
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
    direct_type = str(recipient_type or "").strip().lower()
    family_types = {"family", "familia", "parent", "apoderado"}

    # Destinatarios grupales por sección: "padres de familia de 2A y 2B".
    # No se busca esa frase literalmente en el directorio; se resuelven primero los alumnos
    # por NGS y luego sus usuarios de familia TIPCOD=004.
    sections = sieweb.extract_section_codes(recipient_query)
    query_norm = sieweb._normalize_text(recipient_query)
    looks_like_family_group = bool(sections) and (
        direct_type in family_types
        or any(word in query_norm for word in ("PADRES", "FAMILIA", "FAMILIAS", "APODERADOS"))
    )
    if looks_like_family_group:
        group = sieweb.resolve_family_recipients_by_sections(sections)
        if group.get("complete") and group.get("recipient_codes"):
            group_resolved = [
                {
                    "USUCOD": item.get("family_code"),
                    "USUNOM": item.get("family_name"),
                    "TIPCOD": "004",
                    "NGS": item.get("section"),
                    "student": item.get("student"),
                    "match": item.get("match"),
                }
                for item in group.get("resolved", [])
            ]
            return list(group["recipient_codes"]), group_resolved, None
        return [], group.get("resolved", []), {
            "requires_recipient_selection": True,
            "group_resolution": group,
            "note": "No se envía mientras exista algún alumno sin familia resuelta o una coincidencia ambigua. Revisa el diagnóstico y corrige solo esos casos.",
        }

    resolved = sieweb.search_messaging_users(
        query=recipient_query, recipient_type=recipient_type, ngs=ngs, limit=30
    )

    # Si se pide familia por el nombre completo del estudiante, el directorio de familias
    # puede guardar solo los apellidos. Intentar resolver primero al estudiante y luego
    # buscar la familia por sus apellidos, sin inventar códigos ni relaciones numéricas.
    if len(resolved) != 1 and direct_type in family_types:
        students = sieweb.search_messaging_users(
            query=recipient_query, recipient_type="student", ngs=ngs, limit=10
        )
        if len(students) == 1:
            student_name = str(students[0].get("USUNOM") or "").strip()
            surname_part = student_name.split(",", 1)[0].strip() if "," in student_name else " ".join(student_name.split()[:2])
            if surname_part:
                family_matches = sieweb.search_messaging_users(
                    query=surname_part, recipient_type="family", ngs=ngs, limit=30
                )
                if len(family_matches) == 1:
                    resolved = family_matches

    if len(resolved) != 1:
        return [], resolved, {
            "requires_recipient_selection": True,
            "query": recipient_query,
            "recipient_type": recipient_type,
            "ngs": ngs,
            "matches": resolved,
            "note": "Selecciona exactamente un USUCOD o vuelve a llamar con recipient_codes. No se inventan destinatarios.",
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
    """CREA/COMPONE un correo NUEVO de SieWeb sin enviarlo. Acepta un destinatario individual o grupos naturales como 'padres de familia de 2A y 2B'; para grupos resuelve alumnos por NGS y familias por el directorio real. No necesita hilo previo."""
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

def sieweb_criteria_write_preflight(class_id: int, class_period_id: int, root_content_id: int,
                                    id_ambito: int, extra_params_json: str = "{}") -> str:
    """Diagnóstico SOLO LECTURA ligado al idAmbito exacto que luego usará la escritura."""
    extra=json.loads(extra_params_json or "{}")
    raw=sieweb.get_criteria(class_id=class_id,class_period_id=class_period_id,
                            root_content_id=root_content_id,id_ambito=id_ambito,extra_params=extra)
    model=sieweb.extract_criteria_editor_model(raw)
    replica=sieweb.extract_replica_from_editor(raw,None)
    summary=sieweb.get_gradebook_summary(class_period_id=class_period_id, root_content_id=root_content_id, extra_params=extra)
    info=summary.get("class") or {}
    context_ok=(
        str(info.get("idClase") or class_id)==str(class_id) and
        str(info.get("idClasePeriodo") or class_period_id)==str(class_period_id) and
        str(info.get("idContenidoPrin") or root_content_id)==str(root_content_id)
    )
    rows=[]
    first_capacity=None
    for path,row in sieweb._walk_criterion_tree(model["rows"]):
        desc=sieweb._criterion_description(row)
        if not desc: continue
        if first_capacity is None and str(sieweb._criterion_level(row))=="2":
            first_capacity=row
        rows.append({
            "path":list(path),
            "id":sieweb._criterion_content_id(row),
            "class_content_id":sieweb._criterion_class_content_id(row),
            "parent_id":sieweb._criterion_parent(row),
            "level":sieweb._criterion_level(row),
            "description":desc,
            "llave":row.get("LLAVE") or row.get("llave"),
            "flExiste":row.get("flExiste"),
            "schema_score":sieweb._criterion_row_score(row),
        })
    native_replica=None; native_replica_error=None
    try:
        if first_capacity is None:
            raise ValueError("No se encontró una capacidad real para validar paramDatosReplica.")
        native_replica=sieweb.build_native_replica_context(
            raw=raw,class_info=info,parent=first_capacity,
            criteria_context=dict(getattr(sieweb,"_last_criteria_context",{}) or {}),supplied={},
        )
    except Exception as exc:
        native_replica_error=str(exc)
    return _ok({
        "read_only":True,
        "safe_to_write_probe":bool(rows) and context_ok and native_replica is not None,
        "idAmbito":int(id_ambito),
        "CURSOCOD":((getattr(sieweb, "_last_criteria_context", {}) or {}).get("CURSOCOD")),
        "context_ok":context_ok,
        "context":{
            "requested":{"idClase":class_id,"idClasePeriodo":class_period_id,"idContenido":root_content_id,"idAmbito":int(id_ambito)},
            "gradebook":{"idClase":info.get("idClase"),"idClasePeriodo":info.get("idClasePeriodo"),"idContenido":info.get("idContenidoPrin"),"nomSalon":info.get("nomSalon")},
        },
        "editor_model_path":model["path"],
        "editor_model_score":model["score"],
        "editor_root_count":len(model["rows"]),
        "editor_node_count":sum(1 for _ in sieweb._walk_criterion_tree(model["rows"])),
        "criterion_rows":rows,
        "replica_type":type(replica).__name__ if replica is not None else None,
        "replica_present":replica is not None,
        "native_replica_ready":native_replica is not None,
        "native_replica_context":native_replica,
        "native_replica_error":native_replica_error,
        "native_write_contract":"defaultDataContenido+paramDatosReplica",
        "native_post_keys":["registros","idClase","datosReplica"],
        "note":"v0.7.15: solo lectura; valida idAmbito/CURSOCOD, matrícula completa y el árbol Competencia→Capacidad→Desempeño antes de reproducir el modal oficial.",
    })


def sieweb_upsert_criteria_verified_tool(class_id: int, class_period_id: int, root_content_id: int,
                                         id_ambito: int, records_json: str, expected_json: str, replica_json: str = "{}",
                                         extra_params_json: str = "{}", confirmed: bool = False) -> str:
    """Alta/edición segura de criterios ligada al idAmbito exacto y con verificación doble."""
    records=json.loads(records_json or "[]")
    expected=json.loads(expected_json or "[]")
    replica=json.loads(replica_json or "{}")
    extra=json.loads(extra_params_json or "{}")
    preview={"class_id":class_id,"class_period_id":class_period_id,"root_content_id":root_content_id,
             "id_ambito":int(id_ambito),"records":records,"expected":expected,
             "mode":"ui-native-modal-coursecode-roster-v0.7.15","context_guard":"exact-ambito-native-modal-roster-v0.7.15"}
    if not confirmed:
        return _ok({"requires_confirmation":True,"preview":preview})
    return _ok(sieweb.upsert_criteria_verified(
        class_id=class_id,class_period_id=class_period_id,root_content_id=root_content_id,
        id_ambito=int(id_ambito),records=records,replica=replica,expected=expected,extra_params=extra))


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
    matched, unmatched_classroom = [], []
    matched_actual_codes=set()
    for cs in c_students:
        email = str(cs.get("email") or "")
        code = email.split("@", 1)[0] if "@" in email else ""
        matches=sieweb._students_matching_code(summary,code)
        sw=matches[0] if len(matches)==1 else None
        if sw:
            matched_actual_codes.add(str(sw.get("alucod") or ""))
            matched.append({"code": code, "classroom": cs, "sieweb": {k: sw.get(k) for k in ("idPersona","alucod","nomcomp","ngs","nemo","numord")}})
        else:
            unmatched_classroom.append(cs)
    unmatched_sieweb = [{k:s.get(k) for k in ("idPersona","alucod","nomcomp","ngs","nemo","numord")} for s in summary.get("students") or [] if str(s.get("alucod") or "") not in matched_actual_codes]
    return _ok({"matched": matched, "unmatched_classroom": unmatched_classroom, "unmatched_sieweb": unmatched_sieweb, "counts": {"matched": len(matched), "classroom_only": len(unmatched_classroom), "sieweb_only": len(unmatched_sieweb)}})

def workflow_missing_classroom_with_sieweb_ids(course_id: str, course_work_id: str,
                                               class_period_id: int, root_content_id: int,
                                               extra_params_json: str = "{}") -> str:
    """Devuelve quienes no entregaron en Classroom y, cuando se puede, su idPersona/alucod/ngs de SieWeb."""
    extra = json.loads(extra_params_json or "{}")
    missing = classroom.missing_students(course_id, course_work_id)
    summary = sieweb.get_gradebook_summary(class_period_id=class_period_id, root_content_id=root_content_id, extra_params=extra)
    out = []
    for cs in missing:
        email = str(cs.get("email") or "")
        code = email.split("@", 1)[0] if "@" in email else ""
        matches=sieweb._students_matching_code(summary,code)
        sw=matches[0] if len(matches)==1 else None
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
        classroom_code = email.split("@", 1)[0] if "@" in email else ""
        matches=sieweb._students_matching_code(summary,classroom_code)
        sw=matches[0] if len(matches)==1 else None
        actual_alucod=str((sw or {}).get("alucod") or "").strip()
        recipient = msg_by_code.get("A" + actual_alucod.lstrip("A")) if actual_alucod else None
        alucod = actual_alucod or classroom_code
        out.append({
            "code": alucod,
            "classroom": cs,
            "sieweb": ({k: sw.get(k) for k in ("idPersona", "alucod", "nomcomp", "ngs", "nemo", "numord")} if sw else None),
            "messaging_student": recipient,
        })
    return _ok({"context": ctx, "missing": out, "count": len(out),
                "with_student_recipient": sum(1 for x in out if x["messaging_student"])})


def _classroom_grade_to_sieweb_level(value: Any, mapping: dict[str, Any] | None = None) -> str:
    """Convierte 0–20 a AD/A/B/C. Umbrales configurables; por defecto AD 18+, A 15+, B 11+, C <=10."""
    cfg = {"AD": 18, "A": 15, "B": 11}
    cfg.update(mapping or {})
    n = float(value)
    if n >= float(cfg["AD"]): return "AD"
    if n >= float(cfg["A"]): return "A"
    if n >= float(cfg["B"]): return "B"
    return "C"


def workflow_classroom_grades_to_sieweb(p: dict[str, Any]) -> str:
    """Importa notas oficiales de una tarea Classroom a UN desempeño SIEweb nivel 3.

    Hace match por userId->correo institucional->alucod, protege Nivel de Logro y verifica persistencia.
    confirmed debe venir en payload para escribir.
    """
    course_id=str(p["course_id"]); work_id=str(p["course_work_id"])
    section=str(p["section"]); period=int(p["period"]); course_code=str(p.get("course_code","05"))
    header_id=int(p["header_id"]); confirmed=bool(p.get("confirmed", False))
    ambitos=p.get("id_ambito_by_section") or {}
    ctx=sieweb.resolve_class_context(section=section, period=period, course_code=course_code, id_ambito=p.get("id_ambito") or ambitos.get(section))
    extra=dict(p.get("extra_params") or {}); extra.setdefault("idPeriodoAnt", ctx.get("idPeriodoAnt",0))
    summary=sieweb.get_gradebook_summary(class_period_id=ctx["idClasePeriodo"], root_content_id=ctx["idContenido"], extra_params=extra)
    target=sieweb.assert_performance_target(summary, header_id=header_id, performance_level=int(p.get("performance_level",3)))
    students=classroom.list_students(course_id)
    user_to_code={str(x.get("userId") or x.get("id") or ""): str(x.get("email") or "").split("@",1)[0] for x in students}
    subs=classroom.list_submissions(course_id, work_id)
    grade_map={}; skipped=[]
    for sub in subs:
        raw=sub.get("assignedGrade")
        if raw is None and bool(p.get("allow_draft_grade", False)): raw=sub.get("draftGrade")
        if raw is None:
            skipped.append({"userId":sub.get("userId"),"reason":"no_official_grade"}); continue
        code=user_to_code.get(str(sub.get("userId") or ""),"")
        if not code:
            skipped.append({"userId":sub.get("userId"),"reason":"classroom_student_code_not_resolved"}); continue
        grade_map[code]=_classroom_grade_to_sieweb_level(raw, p.get("grade_thresholds"))
    if not grade_map: raise ValueError("No se encontraron calificaciones de Classroom transferibles.")
    preview={"section":section,"context":ctx,"target_performance":target,"grades":grade_map,"skipped":skipped,
             "protection":"solo nivelEva=3; Nivel de Logro no se modifica"}
    if not confirmed: return _ok({"requires_confirmation":True,"preview":preview})
    class_info=summary.get("class") or {}
    result=sieweb.save_grades_verified(year=str(class_info.get("ano") or p.get("year") or "2026"), course_code=str(class_info.get("cursocod") or course_code),
        class_period_id=int(ctx["idClasePeriodo"]), root_content_id=int(ctx["idContenido"]), period=period,
        section_ng=class_info.get("arrNGS") or p.get("section_ng") or [], header_id=header_id,
        grades_by_student_code=grade_map, class_name=str(ctx.get("nomSalon") or section), extra_params=extra,
        protect_achievement_level=True, performance_level=int(p.get("performance_level",3)))
    return _ok({"preview":preview,"result":result})


def workflow_replicate_performances(p: dict[str, Any]) -> str:
    """Replica desempeños entre secciones resolviendo padres/IDs en cada destino, nunca copiando IDs de origen."""
    source=str(p["source_section"]); targets=[str(x) for x in p.get("target_sections",[])]
    period=int(p["period"]); course_code=str(p.get("course_code","05")); confirmed=bool(p.get("confirmed",False))
    specs=list(p.get("performances") or [])
    if not targets or not specs: raise ValueError("Se requieren target_sections y performances.")
    plan=[]
    for section in targets:
        ambitos=p.get("id_ambito_by_section") or {}
        ctx=sieweb.resolve_class_context(section=section, period=period, course_code=course_code, id_ambito=p.get("id_ambito") or ambitos.get(section))
        extra=dict(p.get("extra_params") or {}); extra.setdefault("idPeriodoAnt",ctx.get("idPeriodoAnt",0))
        summary=sieweb.get_gradebook_summary(class_period_id=ctx["idClasePeriodo"],root_content_id=ctx["idContenido"],extra_params=extra)
        records=[]; expected=[]; existing=[]
        for spec in specs:
            parent_text=str(spec["parent_description"]); desc=str(spec["description"])
            parents=sieweb.find_exact_criterion(summary,description=parent_text,level=int(spec.get("parent_level",2)))
            if len(parents)!=1:
                raise ValueError(f"{section}: no se resolvió de forma única la capacidad padre '{parent_text}'.")
            parent_id=int(parents[0]["id"])
            found=sieweb.find_exact_criterion(summary,description=desc,parent_id=parent_id,level=int(spec.get("level",3)))
            if len(found)>1: raise ValueError(f"{section}: desempeño duplicado '{desc}'.")
            if len(found)==1:
                existing.append(found[0]); continue
            # v0.7.15: solo transportamos intención pedagógica. El upsert relee
            # resCriterios, localiza la Capacidad y construye defaultDataContenido
            # con LLAVE/INDICE y paramDatosReplica exactamente como el modal oficial.
            requested={
                "descripcion":desc,
                "idpadre":parent_id,
                "nivelEva":int(spec.get("level",3)),
            }
            for key,value in dict(spec.get("record") or {}).items():
                if key not in {"id","ID","idClaseContenido","ID_CLASE_CONTENIDO"}:
                    requested[key]=value
            records.append(requested); expected.append({"description":desc,"parent_id":parent_id,"level":int(spec.get("level",3))})
        plan.append({"section":section,"ctx":ctx,"extra":extra,"records":records,"expected":expected,"existing":existing})
    if not confirmed:
        return _ok({"requires_confirmation":True,"source_section":source,"plan":plan,
                    "note":"Los IDs se resuelven independientemente en cada sección; no se toca Nivel de Logro."})
    results=[]
    for item in plan:
        if not item["records"]:
            results.append({"section":item["section"],"already_present":item["existing"],"saved":True}); continue
        ctx=item["ctx"]
        res=sieweb.upsert_criteria_verified(class_id=int(ctx["idClase"]),class_period_id=int(ctx["idClasePeriodo"]),
            root_content_id=int(ctx["idContenido"]),id_ambito=int(ctx["idAmbito"]),
            records=item["records"],replica=p.get("replica") or {},
            expected=item["expected"],extra_params=item["extra"])
        results.append({"section":item["section"],"result":res})
    return _ok({"replicated":True,"results":results})


if __name__ == "__main__":
    mcp.run(transport="streamable-http")
