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


# ---------------- Classroom ampliado ----------------
@mcp.tool()
def classroom_get_course(course_id: str) -> str:
    """Obtiene el detalle de un curso de Classroom."""
    return _ok(classroom.get_course(course_id))

@mcp.tool()
def classroom_list_teachers(course_id: str) -> str:
    """Lista docentes de un curso de Classroom."""
    return _ok(classroom.list_teachers(course_id))

@mcp.tool()
def classroom_list_topics(course_id: str) -> str:
    """Lista temas/topics de un curso de Classroom."""
    return _ok(classroom.list_topics(course_id))

@mcp.tool()
def classroom_create_topic(course_id: str, name: str, confirmed: bool = False) -> str:
    """Crea un tema en Classroom. Requiere confirmed=true."""
    if not confirmed:
        return _ok({"requires_confirmation": True, "preview": {"course_id": course_id, "name": name}})
    return _ok(classroom.create_topic(course_id, name))

@mcp.tool()
def classroom_list_announcements(course_id: str, include_drafts: bool = True) -> str:
    """Lista anuncios de Classroom."""
    return _ok(classroom.list_announcements(course_id, include_drafts=include_drafts))

@mcp.tool()
def classroom_create_announcement(course_id: str, text: str, publish: bool = False, confirmed: bool = False) -> str:
    """Crea un anuncio en Classroom; por defecto queda borrador. Requiere confirmación."""
    preview = {"course_id": course_id, "text": text, "state": "PUBLISHED" if publish else "DRAFT"}
    if not confirmed:
        return _ok({"requires_confirmation": True, "preview": preview})
    return _ok(classroom.create_announcement(course_id, text=text, publish=publish))

@mcp.tool()
def classroom_get_coursework(course_id: str, course_work_id: str) -> str:
    """Lee una tarea completa de Classroom, incluidos materiales y configuración."""
    return _ok(classroom.get_coursework(course_id, course_work_id))

@mcp.tool()
def classroom_list_materials(course_id: str, include_drafts: bool = True) -> str:
    """Lista materiales publicados o borradores de un curso."""
    return _ok(classroom.list_coursework_materials(course_id, include_drafts=include_drafts))

@mcp.tool()
def classroom_get_submission(course_id: str, course_work_id: str, submission_id: str) -> str:
    """Lee una entrega completa, incluidos adjuntos e historial cuando la API los expone."""
    return _ok(classroom.get_submission(course_id, course_work_id, submission_id))

@mcp.tool()
def classroom_course_progress(course_id: str, include_drafts: bool = False) -> str:
    """Resume por alumno entregadas, devueltas, pendientes, tardías y calificadas en un curso."""
    return _ok(classroom.course_progress(course_id, include_drafts=include_drafts))

@mcp.tool()
def classroom_update_assignment(course_id: str, course_work_id: str, updates_json: str, confirmed: bool = False) -> str:
    """Edita una tarea creada por esta integración. Requiere confirmación."""
    updates = json.loads(updates_json or "{}")
    if not confirmed:
        return _ok({"requires_confirmation": True, "preview": {"course_id": course_id, "course_work_id": course_work_id, "updates": updates}})
    return _ok(classroom.patch_coursework(course_id, course_work_id, updates))

@mcp.tool()
def classroom_delete_assignment(course_id: str, course_work_id: str, confirmed: bool = False) -> str:
    """Elimina una tarea creada por esta integración. Acción destructiva; requiere confirmación."""
    if not confirmed:
        return _ok({"requires_confirmation": True, "destructive": True, "preview": {"course_id": course_id, "course_work_id": course_work_id}})
    return _ok(classroom.delete_coursework(course_id, course_work_id))

@mcp.tool()
def classroom_batch_grade(course_id: str, course_work_id: str, grades_json: str,
                          return_to_student: bool = False, confirmed: bool = False) -> str:
    """Califica varias entregas. grades_json: [{submission_id o user_id, grade}]. Requiere confirmación."""
    grades = json.loads(grades_json or "[]")
    if not confirmed:
        return _ok({"requires_confirmation": True, "preview": {"course_id": course_id, "course_work_id": course_work_id, "return_to_student": return_to_student, "grades": grades}})
    return _ok(classroom.batch_grade(course_id, course_work_id, grades, return_to_student=return_to_student))

@mcp.tool()
def sieweb_resolve_class_context(section: str, period: int, course_code: str = "05", id_ambito: int | None = None) -> str:
    """Resuelve 2.º A/5.º A + período a ID_CLASE, ID_CLASE_PERIODO e ID_CONTENIDO de SieWeb."""
    return _ok(sieweb.resolve_class_context(section=section, period=period, course_code=course_code, id_ambito=id_ambito))

@mcp.tool()
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

@mcp.tool()
def sieweb_search_recipients(query: str, recipient_type: str = "any", ngs: str = "", limit: int = 30) -> str:
    """Busca destinatarios de Mensajería. recipient_type: student/alumno, family/familia, teacher/docente o any."""
    return _ok(sieweb.search_messaging_users(query=query, recipient_type=recipient_type, ngs=ngs, limit=limit))

@mcp.tool()
def sieweb_send_message(recipient_codes: list[str], subject: str, html_message: str,
                        confirmed: bool = False) -> str:
    """Envía un mensaje NUEVO en SieWeb. Requiere confirmed=true tras mostrar destinatarios, asunto y texto."""
    preview = {"recipient_codes": recipient_codes, "subject": subject, "html_message": html_message}
    if not confirmed:
        return _ok({"requires_confirmation": True, "preview": preview})
    return _ok(sieweb.send_message(recipient_codes=recipient_codes, subject=subject, html_message=html_message))

# ---------------- SieWeb ampliado ----------------
@mcp.tool()
def sieweb_gradebook_summary(class_period_id: int, root_content_id: int, extra_params_json: str = "{}") -> str:
    """Devuelve contexto de clase, alumnos, criterios, IDs y notas en una forma compacta."""
    extra = json.loads(extra_params_json or "{}")
    return _ok(sieweb.get_gradebook_summary(class_period_id=class_period_id, root_content_id=root_content_id, extra_params=extra))

@mcp.tool()
def sieweb_find_students(class_period_id: int, root_content_id: int, query: str, extra_params_json: str = "{}") -> str:
    """Busca alumnos en el registro de SieWeb por nombre o código."""
    extra = json.loads(extra_params_json or "{}")
    summary = sieweb.get_gradebook_summary(class_period_id=class_period_id, root_content_id=root_content_id, extra_params=extra)
    return _ok(sieweb.find_students_in_gradebook(summary, query))

@mcp.tool()
def sieweb_find_criteria(class_period_id: int, root_content_id: int, query: str, extra_params_json: str = "{}") -> str:
    """Busca competencias/capacidades/desempeños por texto o ID dentro del registro."""
    extra = json.loads(extra_params_json or "{}")
    summary = sieweb.get_gradebook_summary(class_period_id=class_period_id, root_content_id=root_content_id, extra_params=extra)
    return _ok(sieweb.find_criteria_in_gradebook(summary, query))

@mcp.tool()
def sieweb_get_conclusions_batch(targets_json: str) -> str:
    """Lee conclusiones de varios alumnos/criterios. targets=[{person_id,class_content_id,ng}]."""
    return _ok(sieweb.get_conclusions_batch(json.loads(targets_json or "[]")))

@mcp.tool()
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

@mcp.tool()
def sieweb_build_grade_records(class_period_id: int, root_content_id: int, header_id: int,
                               grades_by_student_code_json: str, extra_params_json: str = "{}") -> str:
    """Construye registros de HyoClasenota/actualizar desde {codigoAlumno: nota}, sin escribir todavía."""
    extra = json.loads(extra_params_json or "{}")
    grade_map = json.loads(grades_by_student_code_json or "{}")
    summary = sieweb.get_gradebook_summary(class_period_id=class_period_id, root_content_id=root_content_id, extra_params=extra)
    return _ok(sieweb.build_grade_records(summary, header_id=header_id, grades_by_student_code={str(k): str(v) for k,v in grade_map.items()}))

# ---------------- Flujos Classroom <-> SieWeb ----------------
@mcp.tool()
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

@mcp.tool()
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


@mcp.tool()
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
