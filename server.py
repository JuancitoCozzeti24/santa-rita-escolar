from __future__ import annotations

from dataclasses import asdict, dataclass, field
from datetime import datetime, timezone
from threading import RLock
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

# ---------------------------------------------------------------------------
# PRUEBA PUNTUAL DEDUP — autorizada por el docente.
# Esta ruta está bloqueada a un único alumno/tarea y exige un token temporal
# de entorno. No acepta IDs ni nombres enviados por el cliente.
# ---------------------------------------------------------------------------

_DEDUP_TEST_COURSE_ID = "794101973737"
_DEDUP_TEST_COURSE_WORK_ID = "874845898173"
_DEDUP_TEST_STUDENT_NAME = "Luis Gonzalo Vargas Guerrero"
_dedup_test_state: dict[str, object] = {}


def _dedup_test_auth_ok(request: Request) -> bool:
    expected = str(os.getenv("SIEROOM_DEDUP_TEST_TOKEN") or "")
    provided = str(request.query_params.get("token") or "")
    return bool(expected) and bool(provided) and _secrets.compare_digest(expected, provided)


def _dedup_norm(value: object) -> str:
    return " ".join(str(value or "").split()).strip().casefold()


def _dedup_is_clear_duplicate(left: dict[str, object], right: dict[str, object]) -> bool:
    a = _dedup_norm(left.get("text"))
    b = _dedup_norm(right.get("text"))
    if not a or not b:
        return False
    if a == b:
        return True
    shorter, longer = (a, b) if len(a) <= len(b) else (b, a)
    ratio = len(shorter) / max(1, len(longer))
    return len(shorter) >= 80 and ratio >= 0.70 and shorter in longer


def _dedup_structured_comments(result: dict[str, object]) -> list[dict[str, object]]:
    raw = result.get("comments")
    if not isinstance(raw, list):
        return []
    out: list[dict[str, object]] = []
    for item in raw:
        if not isinstance(item, dict):
            continue
        markers = item.get("markers")
        if item.get("structuredFeedback") is not True:
            continue
        if not isinstance(markers, list) or len(markers) < 2:
            continue
        text = str(item.get("text") or "").strip()
        dom_order = item.get("domOrder")
        if not text or not isinstance(dom_order, int) or isinstance(dom_order, bool):
            continue
        out.append({
            "text": text,
            "domOrder": dom_order,
            "characterCount": len(text),
        })
    return out


def _dedup_pick_one(comments: list[dict[str, object]]) -> tuple[dict[str, object], dict[str, object]] | None:
    # Solo una eliminación por esta prueba. Conserva el comentario más largo.
    for i, left in enumerate(comments):
        for right in comments[i + 1:]:
            if not _dedup_is_clear_duplicate(left, right):
                continue
            left_len = int(left["characterCount"])
            right_len = int(right["characterCount"])
            if left_len == right_len:
                # La orden pedida es borrar el de MENOR cantidad de caracteres;
                # ante empate no se borra nada automáticamente.
                continue
            keeper, target = (left, right) if left_len > right_len else (right, left)
            return keeper, target
    return None


@mcp.custom_route("/bridge/v1/dedup-test/start", methods=["GET"])
async def classroom_dedup_test_start(request: Request):
    if not _dedup_test_auth_ok(request):
        return JSONResponse({"ok": False, "error": "dedup_test_unauthorized"}, status_code=401)

    if _dedup_test_state.get("read_job_id"):
        return JSONResponse({
            "ok": True,
            "reused": True,
            "student": _DEDUP_TEST_STUDENT_NAME,
            "state": dict(_dedup_test_state),
        })

    students = classroom.list_students(_DEDUP_TEST_COURSE_ID)
    matches = [
        row for row in students
        if _dedup_norm(row.get("name")) == _dedup_norm(_DEDUP_TEST_STUDENT_NAME)
    ]
    if len(matches) != 1:
        return JSONResponse({
            "ok": False,
            "error": "student_resolution_failed",
            "expected": _DEDUP_TEST_STUDENT_NAME,
            "match_count": len(matches),
        }, status_code=409)

    user_id = str(matches[0].get("userId") or "")
    submissions = classroom.list_submissions(
        _DEDUP_TEST_COURSE_ID, _DEDUP_TEST_COURSE_WORK_ID
    )
    matched_submissions = [row for row in submissions if str(row.get("userId") or "") == user_id]
    if len(matched_submissions) != 1:
        return JSONResponse({
            "ok": False,
            "error": "submission_resolution_failed",
            "student": _DEDUP_TEST_STUDENT_NAME,
            "match_count": len(matched_submissions),
        }, status_code=409)

    sub = matched_submissions[0]
    submission_id = str(sub.get("id") or "")
    submission_url = str(sub.get("alternateLink") or "")
    if not submission_id or not submission_url:
        return JSONResponse({"ok": False, "error": "submission_missing_id_or_url"}, status_code=409)

    job = bridge_queue.enqueue(
        course_id=_DEDUP_TEST_COURSE_ID,
        course_work_id=_DEDUP_TEST_COURSE_WORK_ID,
        submission_id=submission_id,
        submission_url=submission_url,
        operation="read_private_comments",
    )
    _dedup_test_state.update({
        "student": _DEDUP_TEST_STUDENT_NAME,
        "submission_id": submission_id,
        "submission_url": submission_url,
        "read_job_id": job.id,
        "stage": "reading_before_delete",
        "delete_job_id": None,
        "verify_read_job_id": None,
        "keeper_characters": None,
        "deleted_characters": None,
        "outcome": None,
    })
    return JSONResponse({
        "ok": True,
        "student": _DEDUP_TEST_STUDENT_NAME,
        "submission_id": submission_id,
        "read_job_id": job.id,
        "stage": "reading_before_delete",
    })


@mcp.custom_route("/bridge/v1/dedup-test/status", methods=["GET"])
async def classroom_dedup_test_status(request: Request):
    if not _dedup_test_auth_ok(request):
        return JSONResponse({"ok": False, "error": "dedup_test_unauthorized"}, status_code=401)
    if not _dedup_test_state.get("read_job_id"):
        return JSONResponse({"ok": True, "stage": "not_started"})

    read_job = bridge_queue.get(str(_dedup_test_state["read_job_id"]))
    if read_job is None:
        return JSONResponse({"ok": False, "error": "read_job_missing"}, status_code=409)

    # Fase 1: esperar lectura y, si hay un duplicado claro, encolar UN borrado.
    if not _dedup_test_state.get("delete_job_id") and not _dedup_test_state.get("outcome"):
        if read_job.status == "failed":
            _dedup_test_state.update({"stage": "read_failed", "outcome": "read_failed"})
        elif read_job.status == "completed":
            result = read_job.bridge_result or {}
            comments = _dedup_structured_comments(result)
            pair = _dedup_pick_one(comments)
            if pair is None:
                _dedup_test_state.update({
                    "stage": "no_clear_duplicate",
                    "outcome": "no_clear_duplicate",
                    "structured_comment_count": len(comments),
                })
            else:
                keeper, target = pair
                delete_job, reused = _private_comment_delete_queue.enqueue(
                    course_id=_DEDUP_TEST_COURSE_ID,
                    course_work_id=_DEDUP_TEST_COURSE_WORK_ID,
                    submission_id=str(_dedup_test_state["submission_id"]),
                    submission_url=str(_dedup_test_state["submission_url"]),
                    comment_text=str(target["text"]),
                    dom_order=int(target["domOrder"]),
                )
                _dedup_test_state.update({
                    "stage": "delete_queued",
                    "delete_job_id": delete_job.id,
                    "delete_reused": reused,
                    "keeper_characters": int(keeper["characterCount"]),
                    "deleted_characters": int(target["characterCount"]),
                    "keeper_dom_order": int(keeper["domOrder"]),
                    "deleted_dom_order": int(target["domOrder"]),
                })

    # Fase 2: esperar borrado y encolar una lectura de verificación.
    delete_job_id = _dedup_test_state.get("delete_job_id")
    if delete_job_id and not _dedup_test_state.get("verify_read_job_id"):
        delete_job = _private_comment_delete_queue.get(str(delete_job_id))
        if delete_job:
            if delete_job.status == "failed":
                _dedup_test_state.update({
                    "stage": "delete_failed",
                    "outcome": "delete_failed",
                    "delete_error": delete_job.error,
                })
            elif delete_job.status == "completed":
                verify = bridge_queue.enqueue(
                    course_id=_DEDUP_TEST_COURSE_ID,
                    course_work_id=_DEDUP_TEST_COURSE_WORK_ID,
                    submission_id=str(_dedup_test_state["submission_id"]),
                    submission_url=str(_dedup_test_state["submission_url"]),
                    operation="read_private_comments",
                )
                _dedup_test_state.update({
                    "stage": "verifying_after_delete",
                    "verify_read_job_id": verify.id,
                    "delete_confirmation": {
                        "before_matching_count": (delete_job.result or {}).get("before_matching_count"),
                        "after_matching_count": (delete_job.result or {}).get("after_matching_count"),
                    },
                })

    # Fase 3: comprobar que el duplicado ya no persiste.
    verify_id = _dedup_test_state.get("verify_read_job_id")
    if verify_id and not _dedup_test_state.get("outcome"):
        verify_job = bridge_queue.get(str(verify_id))
        if verify_job:
            if verify_job.status == "failed":
                _dedup_test_state.update({
                    "stage": "verification_failed",
                    "outcome": "verification_failed",
                })
            elif verify_job.status == "completed":
                comments = _dedup_structured_comments(verify_job.bridge_result or {})
                still_duplicate = _dedup_pick_one(comments) is not None
                _dedup_test_state.update({
                    "stage": "finished",
                    "outcome": "still_duplicate" if still_duplicate else "verified_clean",
                    "structured_comment_count_after": len(comments),
                })

    # No devolvemos el texto privado completo; solo datos necesarios para auditar la prueba.
    public_state = {
        key: value for key, value in _dedup_test_state.items()
        if key not in {"submission_url"}
    }
    read_public = {
        "status": read_job.status,
        "error": read_job.error,
    }
    delete_public = None
    if _dedup_test_state.get("delete_job_id"):
        dj = _private_comment_delete_queue.get(str(_dedup_test_state["delete_job_id"]))
        if dj:
            delete_public = {"status": dj.status, "error": dj.error}
    return JSONResponse({
        "ok": True,
        "student": _DEDUP_TEST_STUDENT_NAME,
        "state": public_state,
        "read": read_public,
        "delete": delete_public,
    })



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


install_attendance(mcp, sieweb, settings, classroom)
setattr(mcp, "_sieroom_attendance_installed", True)
print("SieRoom Asistencia: rutas /asesoria restauradas.", flush=True)


if __name__ == "__main__":
    mcp.run(transport="streamable-http")
