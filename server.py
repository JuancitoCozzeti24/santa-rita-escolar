from __future__ import annotations

from dataclasses import asdict, dataclass, field
from datetime import datetime, timezone
from threading import RLock, Thread
from urllib.parse import urlsplit
from uuid import uuid4
import secrets as _secrets
import os

from starlette.requests import Request
from starlette.responses import JSONResponse

# Núcleo completo de SieRoom v0.8.7 conservado sin cambios.
from server_core import *  # noqa: F401,F403

# Reactiva el módulo de asistencia/asesoría que ya existe en el repositorio.
from attendance import install as install_attendance


PRIVATE_FEEDBACK_POLICY = """
POLÍTICA PREDETERMINADA DE RETROALIMENTACIÓN PRIVADA EN CLASSROOM:
1. Antes de publicar un comentario privado, SieRoom debe comprobar la entrega. Si ya existe cualquier comentario privado, queda prohibido publicar otro, aunque el texto sea distinto. La escritura solo puede continuar cuando la lectura verificada devuelve exactamente cero comentarios existentes.
2. Salvo que el docente pida expresamente otro formato, la retroalimentación debe redactarse usando solo el primer nombre del estudiante y esta estructura:

{Nombre},
He revisado tu trabajo de manera detallada, y he podido observar lo siguiente:

LO QUE HICISTE BIEN:
{explicar de forma concreta qué resolvió correctamente}

LO QUE DEBES CORREGIR:
{explicar con detalle qué hizo mal, por qué está mal y cómo debe corregirlo}

SUGERENCIAS:
{recomendaciones concretas para evitar repetir los errores y reforzar el aprendizaje}

Tu calificación es {nota} - ({nivel A/B/C})

La parte de corrección debe ser suficientemente detallada para que el estudiante entienda el error y el procedimiento correcto. No inventar errores ni aciertos que no se hayan verificado en la evidencia entregada.
3. SieRoom puede eliminar comentarios privados mediante el navegador local, pero es una acción destructiva. Solo se permite cuando el docente autoriza explícitamente el borrado y el comentario se identifica de forma exacta. Si hay ambigüedad, si el texto cambió, si la cuenta docente no se verifica o si Classroom no ofrece la acción Eliminar para ese comentario, no se borra nada.
""".strip()


# FastMCP v1 expone las instrucciones del servidor a los clientes. Añadimos la
# política aquí para no tocar el núcleo 0.8.7 y para que quede activa en cada
# nueva conexión del complemento.
try:
    current_instructions = str(getattr(mcp, "instructions", "") or "").strip()
    if PRIVATE_FEEDBACK_POLICY not in current_instructions:
        combined = (current_instructions + "\n\n" + PRIVATE_FEEDBACK_POLICY).strip()
        if hasattr(mcp, "_mcp_server"):
            mcp._mcp_server.instructions = combined
        else:
            setattr(mcp, "instructions", combined)
except Exception as exc:
    print(f"SieRoom: no se pudo anexar la política de retroalimentación a instructions: {exc}", flush=True)


@mcp.tool()
def classroom_feedback_policy() -> dict[str, object]:
    """Devuelve la política predeterminada para comentarios privados, duplicados y borrado seguro."""
    return {
        "private_comment_existing_guard": "strict",
        "write_allowed_only_when_existing_comment_count": 0,
        "duplicate_or_second_comment_allowed": False,
        "delete_private_comment": True,
        "delete_requires_explicit_confirmation": True,
        "delete_requires_exact_comment_identity": True,
        "default_template": (
            "{Nombre},\n"
            "He revisado tu trabajo de manera detallada, y he podido observar lo siguiente:\n\n"
            "LO QUE HICISTE BIEN:\n{aciertos}\n\n"
            "LO QUE DEBES CORREGIR:\n{errores y corrección detallada}\n\n"
            "SUGERENCIAS:\n{recomendaciones}\n\n"
            "Tu calificación es {nota} - ({nivel A/B/C})"
        ),
        "rules": [
            "Usar solo el primer nombre del estudiante salvo indicación contraria.",
            "No inventar aciertos ni errores no verificados en la entrega.",
            "Explicar cada error con suficiente detalle para enseñar el procedimiento correcto.",
            "Para borrar, verificar cuenta docente, entrega exacta y comentario exacto; ante cualquier ambigüedad no borrar.",
        ],
    }


# ---------------------------------------------------------------------------
# Cola separada para BORRADO de comentarios privados.
# Se mantiene fuera del núcleo 0.8.7 para no alterar el flujo ya validado de
# lectura/publicación/calificación/devolución. El bridge de borrado solo corre
# cuando la cola normal está vacía.
# ---------------------------------------------------------------------------

def _delete_now() -> datetime:
    return datetime.now(timezone.utc)


def _delete_norm_text(value: object) -> str:
    return " ".join(str(value or "").split()).strip()


def _delete_norm_path(value: object) -> str | None:
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


def _delete_target_matches(actual: object, expected: object) -> bool:
    a = _delete_norm_path(actual)
    e = _delete_norm_path(expected)
    return bool(a and e and a == e)


def _delete_bridge_auth_ok(request: Request) -> bool:
    expected = str(settings.classroom_bridge_secret or "")
    provided = str(request.headers.get("x-sieroom-bridge-secret") or "")
    capability = str(request.headers.get("x-sieroom-delete-capability") or "").strip().lower()
    version = str(request.headers.get("x-sieroom-bridge-version") or "").strip()
    return (
        bool(expected)
        and bool(provided)
        and _secrets.compare_digest(expected, provided)
        and capability == "delete_private_comment_v1"
        and version == "0.8.7"
    )


@dataclass
class _PrivateCommentDeleteJob:
    id: str
    course_id: str
    course_work_id: str
    submission_id: str
    submission_url: str
    comment_text: str
    dom_order: int | None = None
    status: str = "queued"
    created_at: datetime = field(default_factory=_delete_now)
    updated_at: datetime = field(default_factory=_delete_now)
    result: dict[str, object] | None = None
    error: str | None = None

    def public(self) -> dict[str, object]:
        raw = asdict(self)
        raw["created_at"] = self.created_at.isoformat()
        raw["updated_at"] = self.updated_at.isoformat()
        return raw


class _PrivateCommentDeleteQueue:
    def __init__(self) -> None:
        self._lock = RLock()
        self._jobs: dict[str, _PrivateCommentDeleteJob] = {}

    def enqueue(
        self,
        *,
        course_id: str,
        course_work_id: str,
        submission_id: str,
        submission_url: str,
        comment_text: str,
        dom_order: int | None,
    ) -> tuple[_PrivateCommentDeleteJob, bool]:
        text = str(comment_text or "").strip()
        if not text:
            raise ValueError("comment_text no puede estar vacío.")
        with self._lock:
            for existing in self._jobs.values():
                if (
                    existing.status in {"queued", "claimed"}
                    and existing.course_id == str(course_id)
                    and existing.course_work_id == str(course_work_id)
                    and existing.submission_id == str(submission_id)
                    and _delete_norm_text(existing.comment_text) == _delete_norm_text(text)
                    and existing.dom_order == dom_order
                ):
                    return existing, True
            job = _PrivateCommentDeleteJob(
                id=str(uuid4()),
                course_id=str(course_id),
                course_work_id=str(course_work_id),
                submission_id=str(submission_id),
                submission_url=str(submission_url),
                comment_text=text,
                dom_order=dom_order,
            )
            self._jobs[job.id] = job
            return job, False

    def next(self) -> _PrivateCommentDeleteJob | None:
        with self._lock:
            queued = [job for job in self._jobs.values() if job.status == "queued"]
            if not queued:
                return None
            job = sorted(queued, key=lambda item: item.created_at)[0]
            job.status = "claimed"
            job.updated_at = _delete_now()
            return job

    def get(self, job_id: str) -> _PrivateCommentDeleteJob | None:
        with self._lock:
            return self._jobs.get(str(job_id))

    def complete(self, job_id: str, result: dict[str, object]) -> _PrivateCommentDeleteJob:
        with self._lock:
            job = self._jobs[str(job_id)]
            job.status = "completed"
            job.result = dict(result or {})
            job.error = None
            job.updated_at = _delete_now()
            return job

    def fail(self, job_id: str, error: str, result: dict[str, object] | None = None) -> _PrivateCommentDeleteJob:
        with self._lock:
            job = self._jobs[str(job_id)]
            job.status = "failed"
            job.error = str(error)
            job.result = dict(result or {})
            job.updated_at = _delete_now()
            return job

    def stats(self) -> dict[str, int]:
        with self._lock:
            counts: dict[str, int] = {}
            for job in self._jobs.values():
                counts[job.status] = counts.get(job.status, 0) + 1
            counts["work_remaining"] = counts.get("queued", 0) + counts.get("claimed", 0)
            return counts


_private_comment_delete_queue = _PrivateCommentDeleteQueue()

@mcp.custom_route("/bridge/v1/delete/status", methods=["GET"])
async def classroom_private_comment_delete_status(request: Request):
    if not _delete_bridge_auth_ok(request):
        return JSONResponse({"ok": False, "error": "delete_bridge_unauthorized_or_incompatible"}, status_code=401)
    return JSONResponse({
        "ok": True,
        "version": "0.8.7-delete-v1",
        "capability": "delete_private_comment_v1",
        "queue": _private_comment_delete_queue.stats(),
    })


@mcp.custom_route("/bridge/v1/delete/next", methods=["GET"])
async def classroom_private_comment_delete_next(request: Request):
    if not _delete_bridge_auth_ok(request):
        return JSONResponse({"ok": False, "error": "delete_bridge_unauthorized_or_incompatible"}, status_code=401)
    job = _private_comment_delete_queue.next()
    return JSONResponse({"ok": True, "job": job.public() if job else None})


@mcp.custom_route("/bridge/v1/delete/jobs/{job_id}/complete", methods=["POST"])
async def classroom_private_comment_delete_complete(request: Request):
    if not _delete_bridge_auth_ok(request):
        return JSONResponse({"ok": False, "error": "delete_bridge_unauthorized_or_incompatible"}, status_code=401)
    job_id = str(request.path_params.get("job_id") or "")
    job = _private_comment_delete_queue.get(job_id)
    if not job:
        return JSONResponse({"ok": False, "error": "delete_job_not_found"}, status_code=404)
    try:
        result = await request.json()
    except Exception:
        result = {}
    result = result if isinstance(result, dict) else {}

    errors: list[str] = []
    if result.get("ok") is not True or result.get("deleted") is not True:
        errors.append("borrado_no_confirmado")
    if result.get("operation") != "delete_private_comment":
        errors.append("operacion_incompatible")
    if result.get("method") != "dom-v0.8.7-delete-v1":
        errors.append("metodo_incompatible")
    if result.get("teacher_account_verified") is not True:
        errors.append("cuenta_docente_no_verificada")
    if not _delete_target_matches(result.get("url"), job.submission_url):
        errors.append("entrega_distinta")
    if _delete_norm_text(result.get("comment_text")) != _delete_norm_text(job.comment_text):
        errors.append("comentario_distinto")
    if job.dom_order is not None and result.get("dom_order") != job.dom_order:
        errors.append("posicion_distinta")

    if errors:
        failed = _private_comment_delete_queue.fail(
            job_id,
            "delete_verification_failed: " + ",".join(errors),
            result,
        )
        return JSONResponse({"ok": False, "job": failed.public()}, status_code=409)

    done = _private_comment_delete_queue.complete(job_id, result)
    return JSONResponse({"ok": True, "job": done.public()})


@mcp.custom_route("/bridge/v1/delete/jobs/{job_id}/fail", methods=["POST"])
async def classroom_private_comment_delete_fail(request: Request):
    if not _delete_bridge_auth_ok(request):
        return JSONResponse({"ok": False, "error": "delete_bridge_unauthorized_or_incompatible"}, status_code=401)
    job_id = str(request.path_params.get("job_id") or "")
    job = _private_comment_delete_queue.get(job_id)
    if not job:
        return JSONResponse({"ok": False, "error": "delete_job_not_found"}, status_code=404)
    try:
        body = await request.json()
    except Exception:
        body = {}
    body = body if isinstance(body, dict) else {}
    failed = _private_comment_delete_queue.fail(job_id, str(body.get("error") or "delete_failed"), body)
    return JSONResponse({"ok": True, "job": failed.public()})


@mcp.tool()
def classroom_delete_private_comment(
    course_id: str,
    course_work_id: str,
    submission_id: str,
    comment_text: str,
    dom_order: int | None = None,
    confirmed: bool = False,
) -> dict[str, object]:
    """Borra UN comentario privado exacto de Classroom mediante el bridge local. Acción destructiva: requiere confirmed=true. Usa comment_text completo; si existen comentarios idénticos, pasa también dom_order obtenido previamente con classroom_private_feedback action=read. Nunca borra de forma ambigua y solo podrá borrar comentarios para los que Classroom muestre una acción Eliminar bajo la cuenta docente configurada."""
    text = str(comment_text or "").strip()
    if not text:
        raise ValueError("Debes indicar comment_text completo del comentario que se desea borrar.")
    if dom_order is not None and (not isinstance(dom_order, int) or isinstance(dom_order, bool) or dom_order < 0):
        raise ValueError("dom_order debe ser un entero mayor o igual a 0.")

    sub = classroom.get_submission(course_id, course_work_id, submission_id)
    url = str(sub.get("alternateLink") or "")
    if not url:
        raise ClassroomError("Classroom no devolvió alternateLink para esta entrega; no se puede borrar de forma segura.")

    preview = {
        "action": "delete_private_comment",
        "destructive": True,
        "course_id": str(course_id),
        "course_work_id": str(course_work_id),
        "submission_id": str(submission_id),
        "submission_url": url,
        "comment_text": text,
        "dom_order": dom_order,
        "safety": [
            "verificar_cuenta_docente",
            "verificar_entrega_exacta",
            "releer_comentarios_antes_de_borrar",
            "exigir_coincidencia_exacta_de_texto",
            "bloquear_si_hay_ambiguedad",
            "confirmar_visualmente_que_desaparece_exactamente_un_comentario",
        ],
    }
    if not confirmed:
        return {"requires_confirmation": True, "preview": preview}

    job, reused = _private_comment_delete_queue.enqueue(
        course_id=course_id,
        course_work_id=course_work_id,
        submission_id=submission_id,
        submission_url=url,
        comment_text=text,
        dom_order=dom_order,
    )
    return {
        "queued": True,
        "reused_active_job": reused,
        "job": job.public(),
        "note": "El bridge de borrado se ejecuta cuando la cola normal de Classroom queda libre.",
    }














# Transferencia protegida 2.º B: Classroom CUADRILÁTEROS págs. 382,383,404 -> SIEweb CUADRILÁTEROS.
def _transfer_2b_cuadrilateros_worker():
    if not str(os.getenv("SIEROOM_TRANSFER_2B_CUADRILATEROS_TOKEN") or "").strip():
        return
    print("TRANSFER 2B CUAD: inicio protegido.", flush=True)
    try:
        # 1) Resolver el curso de Classroom 2.º B por nombre exacto/canónico.
        courses = classroom.list_courses(active_only=True)
        wanted_course = sieweb._canon_text("MATE 2DO - B")
        course_matches = [
            row for row in courses
            if sieweb._canon_text(row.get("name")) == wanted_course
        ]
        if len(course_matches) != 1:
            print(f"TRANSFER 2B CUAD STOP: curso Classroom coincidencias={len(course_matches)} matches={course_matches}", flush=True)
            return
        course = course_matches[0]
        course_id = str(course.get("id") or "")
        print(f"TRANSFER 2B CUAD CLASSROOM COURSE: id={course_id} name={course.get('name')!r}", flush=True)

        # 2) Resolver la tarea exacta.
        works = classroom.list_coursework(course_id)
        wanted_work = sieweb._canon_text("CUADRILÁTEROS - PÁGS. 382, 383 Y 404")
        work_matches = [
            row for row in works
            if sieweb._canon_text(row.get("title")) == wanted_work
        ]
        if len(work_matches) != 1:
            print(f"TRANSFER 2B CUAD STOP: tarea Classroom coincidencias={len(work_matches)} matches={work_matches}", flush=True)
            return
        work = work_matches[0]
        work_id = str(work.get("id") or "")
        print(f"TRANSFER 2B CUAD CLASSROOM WORK: id={work_id} title={work.get('title')!r}", flush=True)

        # 3) Descubrir idAmbito real de S2B sin asumir 519.
        candidates=[]
        for ambito in range(500, 551):
            try:
                classes_payload=sieweb.list_classes(id_ambito=ambito)
                classes=(classes_payload.get("json") or []) if isinstance(classes_payload,dict) else []
                math=[row for row in classes if str(row.get("CURSOCOD") or "").strip()=="05"]
                if len(math)!=1:
                    continue
                class_id=int(math[0]["ID_CLASE"])
                periods_payload=sieweb.list_class_periods(class_id=class_id)
                periods=(periods_payload.get("json") or []) if isinstance(periods_payload,dict) else []
                p2=next((row for row in periods if int(row.get("PERIODO") or 0)==2),None)
                if not p2:
                    continue
                previous=0
                earlier=[row for row in periods if int(row.get("PERIODO") or 0)<2]
                if earlier:
                    previous=int(max(earlier,key=lambda r:int(r.get("PERIODO") or 0))["ID_CLASE_PERIODO"])
                summary=sieweb.get_gradebook_summary(
                    class_period_id=int(p2["ID_CLASE_PERIODO"]),
                    root_content_id=int(p2["ID_CONTENIDO"]),
                    extra_params={"idPeriodoAnt": previous},
                )
                ngs={sieweb._normalize_section(str(st.get("ngs") or "")) for st in summary.get("students") or [] if str(st.get("ngs") or "").strip()}
                class_name=str((summary.get("class") or {}).get("nomSalon") or "")
                if "S2B" in ngs or sieweb._normalize_section(class_name)=="S2B":
                    candidates.append({
                        "idAmbito":ambito,
                        "idClase":class_id,
                        "idClasePeriodo":int(p2["ID_CLASE_PERIODO"]),
                        "idContenido":int(p2["ID_CONTENIDO"]),
                        "idPeriodoAnt":previous,
                        "summary":summary,
                        "course":math[0],
                        "ngs":sorted(ngs),
                        "class_name":class_name,
                    })
            except Exception:
                continue

        if len(candidates) != 1:
            slim=[{k:v for k,v in x.items() if k!="summary"} for x in candidates]
            print(f"TRANSFER 2B CUAD STOP: contexto S2B ambiguo/no resuelto count={len(candidates)} candidates={slim}", flush=True)
            return
        ctx=candidates[0]
        summary=ctx["summary"]
        print("TRANSFER 2B CUAD SIEWEB CONTEXT: " + repr({k:v for k,v in ctx.items() if k!="summary"}), flush=True)

        # 4) Resolver el desempeño exacto por abreviatura + descripción + nivel.
        target_matches=[]
        for item in summary.get("criteria") or []:
            ab=sieweb._canon_text(item.get("abreviatura") or item.get("desc"))
            desc=sieweb._canon_text(item.get("descripcion"))
            if (
                ab=="cuadrilateros"
                and "clasifica y representa cuadrados rectangulos rombos romboides y trapecios" in desc
                and str(item.get("nivelEva"))=="3"
            ):
                target_matches.append(item)
        if len(target_matches)!=1:
            print(f"TRANSFER 2B CUAD STOP: desempeño exacto coincidencias={len(target_matches)} matches={target_matches}", flush=True)
            return
        target=target_matches[0]
        header_id=int(target["id"])
        print(f"TRANSFER 2B CUAD TARGET: {target}", flush=True)

        # 5) Validar que la columna está realmente vacía antes de escribir.
        existing_nonblank=[]
        for st in summary.get("students") or []:
            note=(st.get("notas") or {}).get(str(header_id)) or (st.get("notas") or {}).get(header_id)
            if not isinstance(note,dict):
                continue
            vals=sieweb._grade_field_values(note)
            observed=[str(v).strip().upper() for v in vals.values() if str(v or "").strip()]
            if observed:
                existing_nonblank.append({
                    "alucod":st.get("alucod"),
                    "name":st.get("nomcomp"),
                    "observed":observed,
                })
        if existing_nonblank:
            print(f"TRANSFER 2B CUAD STOP: la columna no está vacía; no se sobrescribe. nonblank={existing_nonblank}", flush=True)
            return

        # 6) Preflight de notas oficiales Classroom.
        roster=classroom.list_students(course_id)
        uid_to_code={}
        uid_to_name={}
        for st in roster:
            uid=str(st.get("userId") or st.get("id") or "")
            email=str(st.get("email") or "")
            code=email.split("@",1)[0].strip() if "@" in email else ""
            if uid:
                uid_to_name[uid]=st.get("name")
            if uid and code:
                uid_to_code[uid]=code
        subs=classroom.list_submissions(course_id,work_id)
        grade_map={}
        skipped=[]
        details=[]
        for sub in subs:
            uid=str(sub.get("userId") or "")
            raw=sub.get("assignedGrade")
            code=uid_to_code.get(uid,"")
            if raw is None:
                skipped.append({"name":uid_to_name.get(uid),"userId":uid,"reason":"no_official_grade"})
                continue
            if not code:
                skipped.append({"name":uid_to_name.get(uid),"userId":uid,"reason":"student_code_not_resolved"})
                continue
            qualitative=_classroom_grade_to_sieweb_level(raw, {"A":15,"B":11})
            grade_map[code]=qualitative
            details.append({"name":uid_to_name.get(uid),"code":code,"numeric":raw,"qualitative":qualitative})

        print(f"TRANSFER 2B CUAD CLASSROOM GRADES: count={len(grade_map)} skipped={skipped} details={details}", flush=True)
        if skipped:
            print("TRANSFER 2B CUAD STOP: hay estudiantes sin nota oficial o sin código; no se envía lote parcial.", flush=True)
            return
        if len(grade_map) != len(subs):
            print(f"TRANSFER 2B CUAD STOP: notas={len(grade_map)} entregas={len(subs)}; no se envía.", flush=True)
            return

        # 7) Match exacto de matrícula SIEweb antes de escribir.
        roster_problems=[]
        for code in grade_map:
            matches=sieweb._students_matching_code(summary,code)
            if len(matches)!=1:
                roster_problems.append({"code":code,"matches":len(matches)})
        if roster_problems:
            print(f"TRANSFER 2B CUAD STOP: problemas de matrícula={roster_problems}", flush=True)
            return

        # 8) Guardado verificado SOLO en el desempeño CUADRILÁTEROS nivel 3.
        result=sieweb.save_grades_verified(
            year=str((summary.get("class") or {}).get("ano") or "2026"),
            course_code=str((summary.get("class") or {}).get("cursocod") or "05"),
            class_period_id=ctx["idClasePeriodo"],
            root_content_id=ctx["idContenido"],
            period=2,
            section_ng=(summary.get("class") or {}).get("arrNivelGrado") or [],
            header_id=header_id,
            grades_by_student_code=grade_map,
            class_name=None,
            extra_params={"idPeriodoAnt":ctx["idPeriodoAnt"]},
            notify=False,
            protect_achievement_level=True,
            performance_level=3,
        )
        print(f"TRANSFER 2B CUAD RESULT: {result}", flush=True)
    except Exception as exc:
        print(f"TRANSFER 2B CUAD ERROR: {type(exc).__name__}: {exc}", flush=True)

if str(os.getenv("SIEROOM_TRANSFER_2B_CUADRILATEROS_TOKEN") or "").strip():
    Thread(target=_transfer_2b_cuadrilateros_worker, name="sieroom-transfer-2b-cuad", daemon=True).start()

install_attendance(mcp, sieweb, settings, classroom)
setattr(mcp, "_sieroom_attendance_installed", True)
print("SieRoom Asistencia: rutas /asesoria restauradas.", flush=True)

if __name__ == "__main__":
    mcp.run(transport="streamable-http")
