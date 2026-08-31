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













# Lectura temporal: identificar qué tareas Classroom originaron dos desempeños de 2.º A.
def _match_2a_perf_worker():
    if not str(os.getenv("SIEROOM_MATCH_2A_PERF_TOKEN") or "").strip():
        return
    print("MATCH 2A PERF: inicio SOLO LECTURA.", flush=True)
    try:
        course_id="794101973737"
        ctx=sieweb.resolve_class_context(section="2A", period=2, course_code="05")
        extra={"idPeriodoAnt":ctx.get("idPeriodoAnt",0)}
        summary=sieweb.get_gradebook_summary(
            class_period_id=ctx["idClasePeriodo"],
            root_content_id=ctx["idContenido"],
            extra_params=extra,
        )

        targets=[]
        for item in summary.get("criteria") or []:
            text=sieweb._canon_text(" | ".join(str(item.get(k) or "") for k in ("desc","abreviatura","descripcion")))
            if (
                "clasifica y representa cuadrados rectangulos rombos romboides y trapecios" in text
                or "aplica formulas y procedimientos para calcular areas y perimetros de figuras planas" in text
                or sieweb._canon_text(item.get("abreviatura"))=="areas perim"
                or sieweb._canon_text(item.get("abreviatura"))=="calc area perim"
            ):
                targets.append(item)
        print(f"MATCH 2A PERF TARGETS: {targets}", flush=True)

        students=classroom.list_students(course_id)
        uid_to_code={}
        code_to_name={}
        for st in students:
            uid=str(st.get("userId") or st.get("id") or "")
            email=str(st.get("email") or "")
            code=email.split("@",1)[0].strip() if "@" in email else ""
            if uid and code:
                uid_to_code[uid]=code
                code_to_name[code]=st.get("name")

        def grade_level(raw):
            try:
                n=float(raw)
            except Exception:
                return None
            if n>=15: return "A"
            if n>=11: return "B"
            if n>=0: return "C"
            return None

        target_vectors={}
        for target in targets:
            hid=int(target["id"])
            vec={}
            for sw in summary.get("students") or []:
                code=str(sw.get("alucod") or "").strip()
                note=(sw.get("notas") or {}).get(str(hid)) or (sw.get("notas") or {}).get(hid)
                if not isinstance(note,dict): continue
                vals=sieweb._grade_field_values(note)
                raw=None
                for v in vals.values():
                    if str(v or "").strip():
                        raw=str(v).strip().upper(); break
                if raw in {"A","B","C"}:
                    vec[code]=raw
            target_vectors[hid]=vec
            print(f"MATCH 2A PERF VECTOR id={hid} abrev={target.get('abreviatura')} count={len(vec)} vec={vec}", flush=True)

        works=classroom.list_coursework(course_id)
        comparisons=[]
        for work in works:
            wid=str(work.get("id") or "")
            title=str(work.get("title") or "")
            try:
                subs=classroom.list_submissions(course_id,wid)
            except Exception:
                continue
            vec={}
            for sub in subs:
                raw=sub.get("assignedGrade")
                if raw is None: continue
                code=uid_to_code.get(str(sub.get("userId") or ""),"")
                lvl=grade_level(raw)
                if code and lvl: vec[code]=lvl
            if not vec: continue

            for target in targets:
                hid=int(target["id"])
                tv=target_vectors.get(hid,{})
                common=set(tv)&set(vec)
                exact=sum(1 for code in common if tv.get(code)==vec.get(code))
                mismatch=sum(1 for code in common if tv.get(code)!=vec.get(code))
                missing_target=len(set(vec)-set(tv))
                missing_work=len(set(tv)-set(vec))
                comparisons.append({
                    "target_id":hid,
                    "target_abrev":target.get("abreviatura"),
                    "work_id":wid,
                    "title":title,
                    "common":len(common),
                    "exact":exact,
                    "mismatch":mismatch,
                    "missing_target":missing_target,
                    "missing_work":missing_work,
                    "work_grade_count":len(vec),
                    "target_grade_count":len(tv),
                })

        comparisons.sort(key=lambda x:(x["target_id"], x["mismatch"], -x["exact"], abs(x["missing_target"])+abs(x["missing_work"])))
        for target in targets:
            hid=int(target["id"])
            top=[x for x in comparisons if x["target_id"]==hid][:12]
            print(f"MATCH 2A PERF TOP id={hid} abrev={target.get('abreviatura')}: {top}", flush=True)
        print("MATCH 2A PERF FIN.", flush=True)
    except Exception as exc:
        print(f"MATCH 2A PERF ERROR: {type(exc).__name__}: {exc}", flush=True)

if str(os.getenv("SIEROOM_MATCH_2A_PERF_TOKEN") or "").strip():
    Thread(target=_match_2a_perf_worker, name="sieroom-match-2a-perf", daemon=True).start()

install_attendance(mcp, sieweb, settings, classroom)
setattr(mcp, "_sieroom_attendance_installed", True)
print("SieRoom Asistencia: rutas /asesoria restauradas.", flush=True)

if __name__ == "__main__":
    mcp.run(transport="streamable-http")
