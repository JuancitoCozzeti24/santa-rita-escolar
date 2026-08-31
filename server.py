from __future__ import annotations

from dataclasses import asdict, dataclass, field
from datetime import datetime, timezone
from threading import RLock, Thread
from urllib.parse import urlsplit
from uuid import uuid4
import secrets as _secrets
import os
import re as _re
import unicodedata as _unicodedata
import time as _time

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









# Temporal: 2.º A — tarea de libro págs. 106–107, solo estudiantes SIN evidencia.
# Escribe comentario privado, 0 puntos y devuelve la entrega mediante Bridge R6.2.
_NO_EVIDENCE_2A_COURSE_ID = "794101973737"
_NO_EVIDENCE_2A_EXPECTED_TITLE = "TAREA DE LIBRO: Págs. 106–107 – Regla de tres simple."

def _no_evidence_norm(value):
    text = _unicodedata.normalize("NFD", str(value or ""))
    text = "".join(ch for ch in text if _unicodedata.category(ch) != "Mn").lower()
    text = text.replace("–", "-").replace("—", "-")
    text = _re.sub(r"[^a-z0-9]+", " ", text)
    return " ".join(text.split())

def _submission_has_evidence(sub):
    assignment = sub.get("assignmentSubmission") or {}
    attachments = assignment.get("attachments") or []
    if isinstance(attachments, list) and len(attachments) > 0:
        return True
    short_answer = sub.get("shortAnswerSubmission") or {}
    if str(short_answer.get("answer") or "").strip():
        return True
    multiple = sub.get("multipleChoiceSubmission") or {}
    if str(multiple.get("answer") or "").strip():
        return True
    return False

def _first_name(display_name):
    parts = [p for p in str(display_name or "").strip().split() if p]
    return parts[0] if parts else "Estudiante"

def _no_evidence_comment(first_name):
    return (
        f"{first_name},\n\n"
        "He revisado la tarea «TAREA DE LIBRO: Págs. 106–107 – Regla de tres simple» y, "
        "hasta este momento, no he encontrado evidencia de que hayas cumplido con la actividad solicitada, "
        "pese al plazo que se brindó para su entrega.\n\n"
        "Por este motivo, tu calificación actual será C con 0 puntos. Sin embargo, quiero darte una última "
        "oportunidad para que puedas regularizarla: podrás entregar la tarea mañana, 31 de agosto, hasta las "
        "11:00 p. m. Te animo a aprovechar este plazo con responsabilidad y organización; cumplir a tiempo "
        "también forma parte de tu proceso de aprendizaje y te ayudará a fortalecer hábitos importantes para "
        "tu formación.\n\n"
        "Después de ese horario ya no habrá una nueva prórroga y se mantendrán la C y los 0 puntos. "
        "Confío en que podrás aprovechar esta última oportunidad y demostrar tu compromiso con tu aprendizaje."
    )

def _no_evidence_2a_worker():
    if not str(os.getenv("SIEROOM_NO_EVIDENCE_2A_TOKEN") or "").strip():
        return
    print("NO EVIDENCE 2A: inicio protegido.", flush=True)
    try:
        works = classroom.list_coursework(_NO_EVIDENCE_2A_COURSE_ID)
        expected = _no_evidence_norm(_NO_EVIDENCE_2A_EXPECTED_TITLE)
        exact = [w for w in works if _no_evidence_norm(w.get("title")) == expected]
        if len(exact) != 1:
            candidates = [
                {"id": w.get("id"), "title": w.get("title")}
                for w in works
                if "106" in str(w.get("title") or "") or "regla de tres" in _no_evidence_norm(w.get("title"))
            ]
            print(
                f"NO EVIDENCE 2A STOP: coincidencias exactas={len(exact)}. candidatos={candidates}",
                flush=True,
            )
            return

        work = exact[0]
        work_id = str(work.get("id") or "")
        print(
            f"NO EVIDENCE 2A TAREA: id={work_id} title={work.get('title')!r} maxPoints={work.get('maxPoints')}",
            flush=True,
        )

        students = classroom.list_students(_NO_EVIDENCE_2A_COURSE_ID)
        names = {str(s.get("userId") or ""): str(s.get("name") or "").strip() for s in students}
        subs = classroom.list_submissions(_NO_EVIDENCE_2A_COURSE_ID, work_id)

        targets = []
        evidence_count = 0
        for sub in subs:
            sid = str(sub.get("id") or "")
            uid = str(sub.get("userId") or "")
            url = str(sub.get("alternateLink") or "")
            name = names.get(uid) or uid or "Estudiante"
            if not sid or not uid or not url:
                print(f"NO EVIDENCE 2A STOP: entrega incompleta para {name}; no se encola nada.", flush=True)
                return
            if _submission_has_evidence(sub):
                evidence_count += 1
                continue
            targets.append({
                "name": name,
                "submission_id": sid,
                "url": url,
                "state": sub.get("state"),
                "assignedGrade": sub.get("assignedGrade"),
                "draftGrade": sub.get("draftGrade"),
            })

        targets.sort(key=lambda x: x["name"].casefold())
        print(
            f"NO EVIDENCE 2A DETECCION: total={len(subs)} con_evidencia={evidence_count} sin_evidencia={len(targets)}.",
            flush=True,
        )
        print(
            "NO EVIDENCE 2A OBJETIVOS: " + " | ".join(
                f"{row['name']}[{row['state']},assigned={row['assignedGrade']},draft={row['draftGrade']}]"
                for row in targets
            ),
            flush=True,
        )

        jobs = []
        for row in targets:
            active = bridge_queue.matching(
                course_id=_NO_EVIDENCE_2A_COURSE_ID,
                course_work_id=work_id,
                submission_id=row["submission_id"],
                operation="post_private_comment",
                statuses={"queued", "claimed"},
            )
            if active:
                jobs.append((row["name"], active[0]))
                print(f"NO EVIDENCE 2A REUSE: {row['name']} job={active[0].id}", flush=True)
                continue

            job = bridge_queue.enqueue(
                course_id=_NO_EVIDENCE_2A_COURSE_ID,
                course_work_id=work_id,
                submission_id=row["submission_id"],
                submission_url=row["url"],
                comment=_no_evidence_comment(_first_name(row["name"])),
                grade=0,
                return_after_comment=True,
            )
            jobs.append((row["name"], job))
            print(f"NO EVIDENCE 2A QUEUED: {row['name']} job={job.id}", flush=True)

        if not jobs:
            print("NO EVIDENCE 2A FIN: no había estudiantes sin evidencia.", flush=True)
            return

        terminal = {"completed", "failed", "blocked", "cancelled"}
        seen = set()
        started = _time.time()
        while _time.time() - started < 720:
            completed = 0
            failed = 0
            pending = 0
            for name, job in jobs:
                cur = bridge_queue.get(job.id)
                if not cur:
                    continue
                if cur.status == "completed":
                    completed += 1
                elif cur.status in {"failed", "blocked", "cancelled"}:
                    failed += 1
                else:
                    pending += 1

                if cur.status in terminal and job.id not in seen:
                    seen.add(job.id)
                    result = cur.bridge_result if isinstance(cur.bridge_result, dict) else {}
                    comment_info = result.get("comment") if isinstance(result.get("comment"), dict) else {}
                    print(
                        f"NO EVIDENCE 2A RESULT {name}: status={cur.status} "
                        f"comment_already={comment_info.get('alreadyPresent')} "
                        f"comment_blocked_existing={comment_info.get('blockedByExistingTeacherComment')} "
                        f"grade={result.get('browser_grade')} returned={result.get('browser_returned')} "
                        f"error={cur.error}",
                        flush=True,
                    )

            if completed + failed == len(jobs):
                print(
                    f"NO EVIDENCE 2A FIN: completed={completed} failed={failed} total={len(jobs)} "
                    f"segundos={_time.time()-started:.1f}.",
                    flush=True,
                )
                return
            _time.sleep(0.5)

        print("NO EVIDENCE 2A TIMEOUT: el monitor terminó a los 12 min; no se crean nuevos jobs.", flush=True)
    except Exception as exc:
        print(f"NO EVIDENCE 2A ERROR FATAL: {type(exc).__name__}: {exc}", flush=True)

if str(os.getenv("SIEROOM_NO_EVIDENCE_2A_TOKEN") or "").strip():
    Thread(target=_no_evidence_2a_worker, name="sieroom-no-evidence-2a", daemon=True).start()

install_attendance(mcp, sieweb, settings, classroom)
setattr(mcp, "_sieroom_attendance_installed", True)
print("SieRoom Asistencia: rutas /asesoria restauradas.", flush=True)

if __name__ == "__main__":
    mcp.run(transport="streamable-http")
