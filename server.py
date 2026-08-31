from __future__ import annotations

from dataclasses import asdict, dataclass, field
from datetime import datetime, timezone
from threading import RLock, Thread
from urllib.parse import urlsplit
from uuid import uuid4
import secrets as _secrets
import os
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
















# Temporal: publicar retroalimentación ya revisada visualmente para 2.º B,
# TAREA DE LIBRO págs. 106–107. No modifica nota ni devuelve entregas.
def _feedback_2b_106107_worker():
    if not str(os.getenv("SIEROOM_FEEDBACK_2B_106107_TOKEN") or "").strip():
        return

    course_id="794101844709"
    work_id="856164577487"
    base="https://classroom.google.com/c/Nzk0MTAxODQ0NzA5/a/ODU2MTY0NTc3NDg3/submissions/by-status/and-sort-last-name/student/"

    reviewed = [
        {
            "name":"Romina",
            "submission":"Cg4Izbi75owTEM_hirv1GA",
            "url":base+"NjU2MjcxMTM3ODY5",
            "good":"Ej. 6: planteaste correctamente la proporción 3:7 y obtuviste 336 m³. Ej. 7: hallaste 1320 hombres como cantidad que puede permanecer y completaste la resta 1500−1320=180. Ej. 8: llegaste correctamente a 24 ovejas. Ej. 10: calculaste las áreas 400 m² y 144 m² y obtuviste S/108.",
            "improve":"En el ejercicio 8, aunque el resultado es correcto, define con claridad qué representa x: debe representar el número de ovejas, no una cantidad de kilogramos. También conviene indicar explícitamente si la relación que estás usando es directa o inversa antes de armar la proporción.",
            "suggest":"Antes de operar, escribe siempre las dos magnitudes, sus unidades y qué representa la incógnita. Eso hará que tu procedimiento sea más claro y evitará confundir ovejas con kilogramos."
        },
        {
            "name":"Victor",
            "submission":"Cg4Iyubt3psTEM_hirv1GA",
            "url":base+"NjYwMjgxNzE3NTc4",
            "good":"Ej. 6: organizaste bien la relación 3/7=144/x y obtuviste 336 m³. Ej. 7: reconociste la relación inversa entre hombres y duración de los víveres y llegaste a 1320 hombres que pueden permanecer. Ej. 8: planteaste correctamente la relación entre ovejas y cantidad de pasto y obtuviste 24 ovejas. Ej. 10: calculaste 400 m² y 144 m² y llegaste correctamente a S/108.",
            "improve":"En el ejercicio 7, después de obtener 1320, deja muy visible el último paso que responde exactamente lo preguntado: 1500−1320=180 hombres que deben retirarse. En varios pasos la escritura queda bastante tenue y puede dificultar verificar el cierre del procedimiento.",
            "suggest":"Diferencia siempre el resultado intermedio de la respuesta final y encierra o subraya la respuesta con su unidad."
        },
        {
            "name":"Antonella",
            "submission":"Cg4I-4DQ4JsTEM_hirv1GA",
            "url":base+"NjYwMjg1NDIzNzM5",
            "good":"Ej. 6: la proporción está bien planteada y llegas a 336 m³. Ej. 7: avanzas correctamente hasta obtener 1320 hombres como la cantidad que puede permanecer.",
            "improve":"Ej. 7: el problema pregunta cuántos deben retirarse; después de 1320 faltaba terminar con 1500−1320=180 hombres y escribir esa respuesta. Ej. 8: la orientación de la proporción no es correcta. Si x es el número inicial de ovejas, debe cumplirse x/40=(x−12)/20; al multiplicar en cruz: 20x=40(x−12), luego 20x=40x−480, por lo que 480=20x y x=24. No debe partirse de 40x=20(x−12). Ej. 10: no aparece en las imágenes entregadas, por lo que no pude verificar su procedimiento.",
            "suggest":"Cuando una pregunta tiene una segunda acción, como “retirar”, verifica que tu respuesta final conteste esa acción y no se quede en un valor intermedio. Además, revisa que todos los ejercicios solicitados aparezcan en las fotos."
        },
        {
            "name":"Gonzalo",
            "submission":"Cg4IvsCW-ZsTEM_hirv1GA",
            "url":base+"NjYwMzM2OTEwMzk4",
            "good":"Los cuatro ejercicios solicitados están correctamente desarrollados. En el 6 obtienes 336 m³; en el 7 hallas 1320 hombres que permanecen y luego 180 que se retiran; en el 8 llegas correctamente a 24 ovejas; y en el 10 calculas las áreas 400 m² y 144 m² para obtener S/108.",
            "improve":"El procedimiento es correcto, pero puedes hacerlo más pedagógico indicando antes de cada proporción si las magnitudes son directa o inversamente proporcionales y manteniendo visibles las unidades durante las operaciones.",
            "suggest":"Conserva este orden: magnitudes → tipo de relación → proporción → operación → respuesta con unidad."
        },
        {
            "name":"Dania",
            "submission":"Cg4IusG8rMMTEM_hirv1GA",
            "url":base+"NjcwOTEzNDcwNjUw",
            "good":"Desarrollaste correctamente todos los ejercicios solicitados. Ej. 6: 336 m³. Ej. 7: 1320 hombres pueden permanecer y 1500−1320=180 deben retirarse. Ej. 8: tu ecuación conduce correctamente a 24 ovejas. Ej. 10: relacionas 400 m² con S/300 y 144 m² con x, obteniendo S/108.",
            "improve":"No hay errores de resultado en los ejercicios pedidos. Lo que puedes mejorar es hacer explícito el tipo de proporcionalidad en cada caso y mantener las unidades junto a los valores para que el razonamiento se entienda sin tener que inferirlo.",
            "suggest":"Sigue trabajando con esa secuencia ordenada y añade una frase final que responda literalmente lo que pregunta cada problema."
        },
        {
            "name":"Ana Paula",
            "submission":"Cg4IjJuO_8MTEM_hirv1GA",
            "url":base+"NjcxMDg2Nzc1Njky",
            "good":"Ej. 6: el cálculo conduce correctamente a 336. Ej. 7: obtienes 1320 hombres que pueden permanecer y luego 180 que deben retirarse. Ej. 8: planteas la relación con x y x−12 y llegas a 24 ovejas. Ej. 10: calculas 400 m² y 144 m² y obtienes S/108.",
            "improve":"En el ejercicio 6 cuida especialmente la unidad: el resultado corresponde a volumen, por lo que debe escribirse 336 m³. En los demás ejercicios, aunque los cálculos son correctos, conviene indicar de manera explícita si la relación es directa o inversa.",
            "suggest":"Revisa siempre que la unidad final corresponda a la magnitud preguntada: m³ para volumen, ovejas/hombres para cantidades de personas o animales y soles para costo."
        },
        {
            "name":"Mathias",
            "submission":"Cg4Iz9KxtcUTEM_hirv1GA",
            "url":base+"NjcxNDY5MDM3OTAz",
            "good":"Ej. 6: planteas 3:7 con 144 m³ y obtienes correctamente 336 m³. Ej. 7: hallas 1320 hombres que permanecen y haces 1500−1320=180. Ej. 10: calculas las áreas 400 y 144 y obtienes S/108.",
            "improve":"Ej. 8: el resultado 24 es correcto, pero el procedimiento escrito no lo justifica. El 12 representa ovejas, no kilogramos; por eso no corresponde escribir 40−12 ni relacionar 20−x. Debes definir x como el número inicial de ovejas: x ovejas ↔ 40 kg y x−12 ovejas ↔ 20 kg. La proporción correcta es x/40=(x−12)/20; entonces 20x=40(x−12), 20x=40x−480, 480=20x y x=24.",
            "suggest":"Nunca restes cantidades que pertenecen a magnitudes distintas. Primero identifica qué dato es “ovejas” y cuál es “kg de pasto”; después construye la proporción."
        },
        {
            "name":"Santiago",
            "submission":"Cg4IpOnl0scTEM_hirv1GA",
            "url":base+"NjcyMDY3NTgxMDky",
            "good":"Los ejercicios 6, 7, 8 y 10 están correctamente resueltos. Obtienes 336 m³ en el 6; 1320 hombres que permanecen y 180 que se retiran en el 7; 24 ovejas en el 8; y S/108 en el 10 después de calcular las áreas 400 m² y 144 m².",
            "improve":"La matemática está bien. Para mejorar la presentación, señala de forma explícita cuándo utilizas proporcionalidad inversa —como en el ejercicio 7— y cuándo proporcionalidad directa —como en los ejercicios 6, 8 y 10—, además de mantener las unidades en cada resultado.",
            "suggest":"Tu procedimiento es sólido; hazlo aún más claro nombrando las magnitudes y el tipo de relación antes de operar."
        },
        {
            "name":"Lucia",
            "submission":"Cg4IpJ7u08cTEM_hirv1GA",
            "url":base+"NjcyMDY5ODE2MTAw",
            "good":"Los cuatro ejercicios solicitados están correctamente desarrollados. Ej. 6: 336 m³. Ej. 7: organizas 88+12=100 días, hallas 1320 hombres y finalmente 180 que se retiran. Ej. 8: planteas x y x−12 con 40 kg y 20 kg y obtienes 24 ovejas. Ej. 10: calculas 400 m² y 144 m² y obtienes S/108.",
            "improve":"No encuentro un error de procedimiento en los ejercicios solicitados. Puedes mejorar la explicación escribiendo al lado de cada tabla si la relación es directa o inversa y conservando las unidades durante toda la operación.",
            "suggest":"Mantén este nivel de orden y añade una respuesta verbal corta al final de cada ejercicio para cerrar el razonamiento."
        },
        {
            "name":"Luis",
            "submission":"Cg4I5uiQ18cTEM_hirv1GA",
            "url":base+"NjcyMDc2Njc0MTUw",
            "good":"Ej. 6: llegas correctamente a 336 m³. Ej. 7: obtienes 1320 hombres que permanecen y luego 180 que deben retirarse. Ej. 8: el planteamiento con x y x−12 conduce correctamente a 24 ovejas. Ej. 10: relacionas las áreas con el costo y obtienes S/108.",
            "improve":"En el ejercicio 10, recuerda que 20×20 y 12×12 representan áreas, por lo que deben escribirse 400 m² y 144 m², no solo como metros. También procura que las operaciones del ejercicio 7 queden más separadas para distinguir el valor intermedio 1320 de la respuesta final 180.",
            "suggest":"Cuida especialmente las unidades y presenta cada paso en una línea distinta; eso facilita revisar tu razonamiento."
        },
        {
            "name":"Fabrizio",
            "submission":"Cg4I-LrDp8gTEM_hirv1GA",
            "url":base+"NjcyMjQ1Mjc2MDI0",
            "good":"Ej. 6: la regla de tres conduce correctamente a 336 m³. Ej. 7: obtienes 1320 hombres y haces la resta para llegar a 180 retirados. Ej. 8: llegas correctamente a 24 ovejas. Ej. 10: calculas 400 m² y 144 m², planteas la proporción de costo y obtienes S/108.",
            "improve":"Los resultados solicitados son correctos. Lo principal a mejorar es la legibilidad y el orden de algunas operaciones: en especial, evita superponer cálculos y conserva las unidades junto a los datos de área y volumen.",
            "suggest":"Usa una línea por operación y deja la respuesta final separada o encerrada; así tu trabajo será mucho más fácil de verificar."
        },
        {
            "name":"Nicolas",
            "submission":"Cg4ImP7mrsgTEM_hirv1GA",
            "url":base+"NjcyMjYwNTM4MTM2",
            "good":"Ej. 6: planteas correctamente la razón 3:7 y obtienes 336 m³. Ej. 7: llegas a 1320 hombres que pueden permanecer y luego a 180 que deben retirarse. Ej. 8: usas x y x−12 con 40 kg y 20 kg y obtienes 24 ovejas. Ej. 10: calculas las áreas 400 m² y 144 m² y llegas a S/108.",
            "improve":"No observo errores de resultado en los cuatro ejercicios. Puedes mejorar la claridad escribiendo explícitamente qué representa x en cada problema y señalando el tipo de proporcionalidad antes de multiplicar en cruz.",
            "suggest":"Sigue mostrando el procedimiento completo; agrega siempre una frase final con la unidad para que la respuesta quede inequívoca."
        },
        {
            "name":"Abigail",
            "submission":"Cg4IpqqN-cgTEM_hirv1GA",
            "url":base+"NjcyNDE2MzU1NjIy",
            "good":"Ej. 6: organizas habilidad y obra y obtienes correctamente 336 m³. Ej. 7: reconoces la relación inversa, hallas 1320 hombres y luego 180 retirados. Ej. 8: planteas x ovejas con 40 kg y x−12 con 20 kg y obtienes 24 ovejas. Ej. 10: la tabla área-costo conduce correctamente a S/108.",
            "improve":"En el ejercicio 10, para que el procedimiento quede completo, muestra explícitamente de dónde salen las áreas: 20²=400 m² y 12²=144 m² antes de colocar 400 y 144 en la tabla.",
            "suggest":"Mantén la buena organización por magnitudes y procura justificar cada dato calculado antes de usarlo en la regla de tres."
        },
        {
            "name":"Juan Pablo",
            "submission":"Cg4IgJq--sgTEM_hirv1GA",
            "url":base+"NjcyNDE5MjUzNTA0",
            "good":"Ej. 6: planteas la proporción 3/7=144/x y obtienes 336 m³. Ej. 7: llegas a 1320 hombres que permanecen y finalmente a 180 que deben retirarse. Ej. 8: el planteamiento con x y x−12 conduce a 24 ovejas. Ej. 10: calculas 400 m² y 144 m² y obtienes correctamente S/108.",
            "improve":"En el ejercicio 7 el resultado es correcto, pero la secuencia escrita queda difícil de seguir. Define desde el inicio qué representa x —por ejemplo, “hombres que permanecen”—, calcula x=1320 y recién después escribe 1500−1320=180. Así no se mezclan el valor intermedio y la respuesta final.",
            "suggest":"Ordena cada ejercicio en datos, incógnita, proporción y respuesta; tu cálculo es correcto y con esa presentación será mucho más claro."
        },
        {
            "name":"Gianfranco",
            "submission":"Cg4It9XG-sgTEM_hirv1GA",
            "url":base+"NjcyNDE5MzkyMTgz",
            "good":"Ej. 6: obtienes correctamente 336 m³. Ej. 7: hallas 1320 hombres que permanecen y luego 180 que deben retirarse. Ej. 10: calculas 400 m² y 144 m² y obtienes S/108.",
            "improve":"Ej. 8: aunque escribiste finalmente 24, hay un error importante en el planteamiento y en la distribución. Si x es el número inicial de ovejas, debe cumplirse x/40=(x−12)/20, por lo que 20x=40(x−12). Al desarrollar: 20x=40x−480, luego 480=20x y x=24. En tu trabajo aparece 40x=20(x−12) y además 20×12 se transforma en 480, cuando 20×12=240. El 24 final coincide con la respuesta, pero el procedimiento escrito no es válido.",
            "suggest":"No valides un procedimiento solo porque llegue al número esperado. Revisa la proporcionalidad y distribuye cuidadosamente cada multiplicación antes de despejar."
        },
        {
            "name":"Mateo",
            "submission":"Cg4Ile_q-sgTEM_hirv1GA",
            "url":base+"NjcyNDE5OTg1MzAx",
            "good":"Ej. 6: la proporción lleva correctamente a 336 m³. Ej. 7: tu planteamiento permite hallar directamente los 180 hombres que deben retirarse. Ej. 8: defines n y n−12 y resuelves correctamente hasta n=24 ovejas. Ej. 10: calculas 400 m² y 144 m² y obtienes S/108.",
            "improve":"No observo errores de procedimiento en los cuatro ejercicios. Para mejorar aún más, indica junto a cada ejercicio si la relación es directa o inversa y conserva las unidades en cada línea.",
            "suggest":"Tu organización es buena; mantén la definición de la incógnita y una respuesta final escrita con su unidad."
        },
        {
            "name":"Mateo",
            "submission":"Cg4Ixv7w-sgTEM_hirv1GA",
            "url":base+"NjcyNDIwMDg1NTc0",
            "good":"Ej. 6: usas correctamente un procedimiento por unidad, 144÷3=48 y luego 48×7=336 m³. Ej. 8: el planteamiento con x y x−12 conduce correctamente a 24 ovejas. Ej. 10: calculas 400 m² y 144 m² y obtienes S/108.",
            "improve":"El ejercicio 7 no aparece en las fotografías entregadas, por lo que no puedo verificar su procedimiento ni afirmar si está correcto. En una evidencia de tarea deben verse todos los ejercicios solicitados, especialmente cuando se pide revisar el desarrollo completo.",
            "suggest":"Antes de enviar, comprueba que las fotos incluyan los ejercicios 6, 7, 8 y 10 completos y legibles. Si una pregunta queda fuera de la imagen, no puede ser evaluada con seguridad."
        },
        {
            "name":"Tamiko",
            "submission":"Cg4IqsylxIUWEM_hirv1GA",
            "url":base+"NzU3Mzk5NjQzNjkw",
            "good":"Ej. 6: resuelves correctamente la relación 3:7 y obtienes 336 m³. Ej. 7: llegas a 1320 hombres que pueden permanecer y luego a 180 que se retiran. Ej. 10: calculas las áreas 400 m² y 144 m² y obtienes correctamente S/108.",
            "improve":"Ej. 8: escribiste que no lo entendiste y no desarrollaste el procedimiento. Aquí las magnitudes son número de ovejas y kg de pasto, y la relación es directa. Si x es el número inicial de ovejas: x ovejas ↔ 40 kg y x−12 ovejas ↔ 20 kg. Entonces x/40=(x−12)/20; 20x=40(x−12); 20x=40x−480; 480=20x; por tanto x=24 ovejas.",
            "suggest":"Cuando un problema no se entienda, empieza escribiendo qué magnitudes aparecen y pregunta: “si una aumenta, ¿la otra aumenta o disminuye?”. Ese paso suele mostrar si la proporcionalidad es directa o inversa y facilita construir la regla de tres."
        }
    ]

    def build_comment(row):
        return (
            f"{row['name']},\n"
            "He revisado tu trabajo de manera detallada, y he podido observar lo siguiente:\n\n"
            "LO QUE HICISTE BIEN:\n" + row["good"] + "\n\n"
            "LO QUE DEBES CORREGIR / MEJORAR:\n" + row["improve"] + "\n\n"
            "SUGERENCIAS:\n" + row["suggest"]
        )

    jobs=[]
    print(f"FEEDBACK 2B 106107: encolando {len(reviewed)} retroalimentaciones revisadas.", flush=True)
    for row in reviewed:
        active=bridge_queue.matching(
            course_id=course_id,
            course_work_id=work_id,
            submission_id=row["submission"],
            operation="post_private_comment",
            statuses={"queued","claimed","waiting_comment_guard"},
        )
        if active:
            jobs.append((row["name"],row["submission"],active[0]))
            print(f"FEEDBACK 2B 106107 REUSE {row['name']}: job={active[0].id}", flush=True)
            continue
        job=bridge_queue.enqueue(
            course_id=course_id,
            course_work_id=work_id,
            submission_id=row["submission"],
            submission_url=row["url"],
            comment=build_comment(row),
            grade=None,
            return_after_comment=False,
        )
        jobs.append((row["name"],row["submission"],job))
        print(f"FEEDBACK 2B 106107 QUEUED {row['name']}: job={job.id}", flush=True)

    terminal={"completed","comment_posted","failed","cancelled","blocked_existing_comment","comment_posted_followup_failed"}
    seen=set()
    started=_time.time()
    while _time.time()-started < 900:
        done=0
        for name,submission,job in jobs:
            cur=bridge_queue.get(job.id)
            if not cur:
                continue
            if cur.status in terminal:
                done += 1
                if cur.id not in seen:
                    seen.add(cur.id)
                    result=cur.bridge_result if isinstance(cur.bridge_result,dict) else {}
                    print(
                        f"FEEDBACK 2B 106107 RESULT {name}: submission={submission} "
                        f"status={cur.status} error={cur.error} bridge_result={result}",
                        flush=True,
                    )
        if done==len(jobs):
            print(f"FEEDBACK 2B 106107 FIN: terminales={done}/{len(jobs)} segundos={_time.time()-started:.1f}", flush=True)
            return
        _time.sleep(0.5)
    print(f"FEEDBACK 2B 106107 TIMEOUT: no se encolarán trabajos nuevos.", flush=True)

if str(os.getenv("SIEROOM_FEEDBACK_2B_106107_TOKEN") or "").strip():
    Thread(target=_feedback_2b_106107_worker, name="sieroom-feedback-2b-106107", daemon=True).start()

install_attendance(mcp, sieweb, settings, classroom)
setattr(mcp, "_sieroom_attendance_installed", True)
print("SieRoom Asistencia: rutas /asesoria restauradas.", flush=True)

if __name__ == "__main__":
    mcp.run(transport="streamable-http")
