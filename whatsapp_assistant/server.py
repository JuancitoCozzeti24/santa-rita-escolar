from __future__ import annotations

import os
import secrets
import time
from dataclasses import asdict, dataclass, field
from datetime import datetime, timedelta, timezone
from threading import RLock
from typing import Any
from uuid import uuid4

from mcp.server.fastmcp import FastMCP
from starlette.requests import Request
from starlette.responses import JSONResponse


VERSION = "0.1.0"
BRIDGE_CAPABILITY = "johnny_whatsapp_bridge_v1"
BRIDGE_SECRET = os.getenv("WHATSAPP_BRIDGE_SECRET", "").strip()
HOST = os.getenv("MCP_HOST", "0.0.0.0")
PORT = int(os.getenv("PORT", os.getenv("MCP_PORT", "8000")))

mcp = FastMCP(
    "Johnny WhatsApp Assistant",
    host=HOST,
    port=PORT,
    streamable_http_path="/mcp",
    instructions=(
        "Asistente privado para el WhatsApp Web del usuario. Las lecturas se realizan "
        "únicamente desde la sesión oficial abierta en su navegador. Para escribir, nunca "
        "envíes un mensaje sin una orden explícita del usuario. Usa whatsapp_send_message "
        "con confirmed=true solo después de que el usuario haya autorizado ese mensaje. "
        "Antes de enviar, el bridge verifica el título del chat y bloquea cualquier discrepancia."
    ),
)


def _now() -> datetime:
    return datetime.now(timezone.utc)


def _norm(value: object) -> str:
    return " ".join(str(value or "").split()).casefold()


def _clean_message(value: object) -> str:
    text = str(value or "").strip()
    if not text:
        raise ValueError("El mensaje no puede estar vacío.")
    if len(text) > 5000:
        raise ValueError("El mensaje supera el límite de 5000 caracteres de esta versión.")
    return text


@dataclass
class WhatsAppJob:
    id: str
    operation: str
    payload: dict[str, Any]
    status: str = "queued"
    created_at: datetime = field(default_factory=_now)
    updated_at: datetime = field(default_factory=_now)
    claimed_until: datetime | None = None
    result: dict[str, Any] | None = None
    error: str | None = None

    def public(self) -> dict[str, Any]:
        raw = asdict(self)
        for key in ("created_at", "updated_at", "claimed_until"):
            value = raw.get(key)
            raw[key] = value.isoformat() if value else None
        return raw


class WhatsAppQueue:
    def __init__(self) -> None:
        self._lock = RLock()
        self._jobs: dict[str, WhatsAppJob] = {}

    def enqueue(self, operation: str, payload: dict[str, Any]) -> WhatsAppJob:
        operation = str(operation or "").strip()
        if operation not in {"read_current_chat", "list_visible_chats", "send_message"}:
            raise ValueError(f"Operación no soportada: {operation}")
        job = WhatsAppJob(id=str(uuid4()), operation=operation, payload=dict(payload or {}))
        with self._lock:
            self._jobs[job.id] = job
        return job

    def get(self, job_id: str) -> WhatsAppJob | None:
        with self._lock:
            return self._jobs.get(str(job_id))

    def next(self, lease_seconds: int = 45) -> WhatsAppJob | None:
        now = _now()
        with self._lock:
            for job in self._jobs.values():
                if job.status == "claimed" and job.claimed_until and job.claimed_until < now:
                    job.status = "queued"
                    job.claimed_until = None
                    job.updated_at = now
            queued = [j for j in self._jobs.values() if j.status == "queued"]
            if not queued:
                return None
            job = min(queued, key=lambda j: j.created_at)
            job.status = "claimed"
            job.claimed_until = now + timedelta(seconds=lease_seconds)
            job.updated_at = now
            return job

    def complete(self, job_id: str, result: dict[str, Any]) -> WhatsAppJob:
        with self._lock:
            job = self._jobs[str(job_id)]
            job.status = "completed"
            job.result = dict(result or {})
            job.error = None
            job.claimed_until = None
            job.updated_at = _now()
            return job

    def fail(self, job_id: str, error: str, result: dict[str, Any] | None = None) -> WhatsAppJob:
        with self._lock:
            job = self._jobs[str(job_id)]
            job.status = "failed"
            job.error = str(error or "bridge_failed")
            job.result = dict(result or {})
            job.claimed_until = None
            job.updated_at = _now()
            return job

    def stats(self) -> dict[str, int]:
        with self._lock:
            counts: dict[str, int] = {}
            for job in self._jobs.values():
                counts[job.status] = counts.get(job.status, 0) + 1
            counts["work_remaining"] = counts.get("queued", 0) + counts.get("claimed", 0)
            return counts


queue = WhatsAppQueue()


def _auth_ok(request: Request) -> bool:
    provided = str(request.headers.get("x-whatsapp-bridge-secret") or "")
    capability = str(request.headers.get("x-whatsapp-bridge-capability") or "")
    return (
        bool(BRIDGE_SECRET)
        and bool(provided)
        and secrets.compare_digest(BRIDGE_SECRET, provided)
        and capability == BRIDGE_CAPABILITY
    )


def _unauthorized() -> JSONResponse:
    return JSONResponse({"ok": False, "error": "whatsapp_bridge_unauthorized"}, status_code=401)


@mcp.custom_route("/wa/v1/status", methods=["GET"])
async def wa_status(request: Request):
    if not _auth_ok(request):
        return _unauthorized()
    return JSONResponse({
        "ok": True,
        "version": VERSION,
        "capability": BRIDGE_CAPABILITY,
        "queue": queue.stats(),
    })


@mcp.custom_route("/wa/v1/next", methods=["GET"])
async def wa_next(request: Request):
    if not _auth_ok(request):
        return _unauthorized()
    job = queue.next()
    return JSONResponse({"ok": True, "job": job.public() if job else None})


@mcp.custom_route("/wa/v1/jobs/{job_id}/complete", methods=["POST"])
async def wa_complete(request: Request):
    if not _auth_ok(request):
        return _unauthorized()
    job_id = str(request.path_params.get("job_id") or "")
    job = queue.get(job_id)
    if not job:
        return JSONResponse({"ok": False, "error": "job_not_found"}, status_code=404)
    try:
        body = await request.json()
    except Exception:
        body = {}
    body = body if isinstance(body, dict) else {}

    errors: list[str] = []
    if body.get("ok") is not True:
        errors.append("bridge_did_not_confirm_ok")
    if body.get("operation") != job.operation:
        errors.append("operation_mismatch")

    if job.operation == "send_message":
        expected_title = job.payload.get("chat_title")
        expected_message = job.payload.get("message")
        if body.get("sent") is not True:
            errors.append("send_not_confirmed")
        if _norm(body.get("chat_title")) != _norm(expected_title):
            errors.append("chat_title_mismatch")
        if str(body.get("message") or "") != str(expected_message or ""):
            errors.append("message_mismatch")

    if errors:
        failed = queue.fail(job_id, ",".join(errors), body)
        return JSONResponse({"ok": False, "job": failed.public()}, status_code=409)

    done = queue.complete(job_id, body)
    return JSONResponse({"ok": True, "job": done.public()})


@mcp.custom_route("/wa/v1/jobs/{job_id}/fail", methods=["POST"])
async def wa_fail(request: Request):
    if not _auth_ok(request):
        return _unauthorized()
    job_id = str(request.path_params.get("job_id") or "")
    if not queue.get(job_id):
        return JSONResponse({"ok": False, "error": "job_not_found"}, status_code=404)
    try:
        body = await request.json()
    except Exception:
        body = {}
    body = body if isinstance(body, dict) else {}
    failed = queue.fail(job_id, str(body.get("error") or "bridge_failed"), body)
    return JSONResponse({"ok": True, "job": failed.public()})


def _run_and_wait(operation: str, payload: dict[str, Any], timeout_seconds: float = 18.0) -> dict[str, Any]:
    job = queue.enqueue(operation, payload)
    deadline = time.monotonic() + max(1.0, min(float(timeout_seconds), 30.0))
    while time.monotonic() < deadline:
        current = queue.get(job.id)
        if current is None:
            break
        if current.status == "completed":
            return {
                "ok": True,
                "job_id": current.id,
                "result": current.result or {},
            }
        if current.status == "failed":
            return {
                "ok": False,
                "job_id": current.id,
                "error": current.error,
                "result": current.result or {},
            }
        time.sleep(0.25)
    current = queue.get(job.id)
    return {
        "ok": False,
        "pending": True,
        "job_id": job.id,
        "status": current.status if current else "unknown",
        "message": "El trabajo quedó en cola. Verifica que WhatsApp Web y la pestaña del bridge estén abiertos.",
    }


@mcp.tool()
def whatsapp_bridge_status() -> dict[str, Any]:
    """Devuelve el estado interno de la cola del bridge. No lee conversaciones."""
    return {
        "version": VERSION,
        "configured": bool(BRIDGE_SECRET),
        "queue": queue.stats(),
    }


@mcp.tool()
def whatsapp_read_current_chat(limit: int = 40) -> dict[str, Any]:
    """Lee los mensajes visibles/cargados del chat actualmente abierto en WhatsApp Web. No cambia de chat ni envía nada."""
    limit = max(1, min(int(limit), 200))
    return _run_and_wait("read_current_chat", {"limit": limit})


@mcp.tool()
def whatsapp_list_visible_chats(limit: int = 50) -> dict[str, Any]:
    """Lista chats que estén visibles/cargados en la barra lateral de WhatsApp Web. No recorre ni scrapea todo el historial."""
    limit = max(1, min(int(limit), 100))
    return _run_and_wait("list_visible_chats", {"limit": limit})


@mcp.tool()
def whatsapp_send_message(
    chat_title: str,
    message: str,
    confirmed: bool = False,
) -> dict[str, Any]:
    """Envía un mensaje al chat YA ABIERTO solo si su título coincide exactamente con chat_title. Requiere confirmed=true tras autorización explícita del usuario."""
    title = str(chat_title or "").strip()
    text = _clean_message(message)
    if not title:
        raise ValueError("Debes indicar chat_title.")

    preview = {
        "action": "send_message",
        "chat_title": title,
        "message": text,
        "safety": [
            "requiere_autorizacion_explicita",
            "verifica_titulo_del_chat_abierto",
            "bloquea_si_el_chat_no_coincide",
            "verifica_que_el_campo_de_escritura_quede_vacio_despues_del_envio",
        ],
    }
    if not confirmed:
        return {"requires_confirmation": True, "preview": preview}

    return _run_and_wait("send_message", {"chat_title": title, "message": text})


@mcp.tool()
def whatsapp_job_status(job_id: str) -> dict[str, Any]:
    """Consulta un trabajo pendiente o completado del bridge por su identificador."""
    job = queue.get(str(job_id or ""))
    if not job:
        return {"ok": False, "error": "job_not_found"}
    return {"ok": True, "job": job.public()}


if __name__ == "__main__":
    mcp.run(transport="streamable-http")
