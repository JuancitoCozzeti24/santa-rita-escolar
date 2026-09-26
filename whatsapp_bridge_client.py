from __future__ import annotations

import json
import os
import time
import urllib.error
import urllib.request
from typing import Any


BASE_URL = os.getenv("WHATSAPP_ASSISTANT_URL", "").strip().rstrip("/")
INTERNAL_SECRET = os.getenv("WHATSAPP_INTERNAL_SECRET", "").strip()


def _configured() -> bool:
    return bool(BASE_URL and INTERNAL_SECRET)


def _request_json(method: str, path: str, payload: dict[str, Any] | None = None) -> dict[str, Any]:
    if not _configured():
        raise RuntimeError("WhatsApp Assistant no está configurado en este servicio.")
    body = None
    headers = {
        "Accept": "application/json",
        "X-WhatsApp-Internal-Secret": INTERNAL_SECRET,
    }
    if payload is not None:
        body = json.dumps(payload).encode("utf-8")
        headers["Content-Type"] = "application/json"

    req = urllib.request.Request(
        BASE_URL + path,
        data=body,
        headers=headers,
        method=method.upper(),
    )
    try:
        with urllib.request.urlopen(req, timeout=12) as response:
            raw = response.read().decode("utf-8")
    except urllib.error.HTTPError as exc:
        try:
            detail = exc.read().decode("utf-8")
        except Exception:
            detail = ""
        raise RuntimeError(f"WhatsApp Assistant HTTP {exc.code}: {detail or exc.reason}") from exc
    except Exception as exc:
        raise RuntimeError(f"No se pudo contactar WhatsApp Assistant: {exc}") from exc

    try:
        data = json.loads(raw or "{}")
    except Exception as exc:
        raise RuntimeError("WhatsApp Assistant devolvió una respuesta no JSON.") from exc
    if not isinstance(data, dict):
        raise RuntimeError("WhatsApp Assistant devolvió una respuesta inválida.")
    return data


def _enqueue_and_wait(
    operation: str,
    payload: dict[str, Any],
    timeout_seconds: float = 18.0,
) -> dict[str, Any]:
    created = _request_json(
        "POST",
        "/wa/v1/internal/enqueue",
        {"operation": operation, "payload": payload},
    )
    job = created.get("job") or {}
    job_id = str(job.get("id") or "")
    if not job_id:
        raise RuntimeError(f"No se recibió job_id del WhatsApp Assistant: {created}")

    deadline = time.monotonic() + max(1.0, min(float(timeout_seconds), 30.0))
    last: dict[str, Any] = created
    while time.monotonic() < deadline:
        current = _request_json("GET", f"/wa/v1/internal/jobs/{job_id}")
        last = current
        job = current.get("job") or {}
        status = str(job.get("status") or "")
        if status == "completed":
            return {
                "ok": True,
                "job_id": job_id,
                "result": job.get("result") or {},
            }
        if status == "failed":
            return {
                "ok": False,
                "job_id": job_id,
                "error": job.get("error"),
                "result": job.get("result") or {},
            }
        time.sleep(0.35)

    job = (last.get("job") or {}) if isinstance(last, dict) else {}
    return {
        "ok": False,
        "pending": True,
        "job_id": job_id,
        "status": job.get("status"),
        "message": "El trabajo quedó pendiente. Mantén WhatsApp Web y la pestaña del bridge abiertos.",
    }


def install(mcp) -> None:
    @mcp.tool()
    def whatsapp_bridge_status() -> dict[str, Any]:
        """Comprueba si el proxy de WhatsApp está configurado. No lee conversaciones."""
        return {
            "configured": _configured(),
            "assistant_url": BASE_URL if BASE_URL else None,
        }

    @mcp.tool()
    def whatsapp_read_current_chat(limit: int = 40) -> dict[str, Any]:
        """Lee los mensajes actualmente cargados del chat abierto en WhatsApp Web. No cambia de chat ni envía nada."""
        limit = max(1, min(int(limit), 200))
        return _enqueue_and_wait("read_current_chat", {"limit": limit})

    @mcp.tool()
    def whatsapp_list_visible_chats(limit: int = 50) -> dict[str, Any]:
        """Lista chats actualmente visibles/cargados en la barra lateral de WhatsApp Web. No recorre todo el historial."""
        limit = max(1, min(int(limit), 100))
        return _enqueue_and_wait("list_visible_chats", {"limit": limit})

    @mcp.tool()
    def whatsapp_send_message(
        chat_title: str,
        message: str,
        confirmed: bool = False,
    ) -> dict[str, Any]:
        """Envía un mensaje al chat YA ABIERTO solo si su título coincide exactamente. Requiere confirmed=true tras autorización explícita."""
        title = str(chat_title or "").strip()
        text = str(message or "").strip()
        if not title:
            raise ValueError("Debes indicar chat_title.")
        if not text:
            raise ValueError("El mensaje no puede estar vacío.")
        if len(text) > 5000:
            raise ValueError("El mensaje supera 5000 caracteres.")

        preview = {
            "action": "send_message",
            "chat_title": title,
            "message": text,
            "safety": [
                "requiere_autorizacion_explicita",
                "verifica_titulo_del_chat_abierto",
                "bloquea_si_el_chat_no_coincide",
            ],
        }
        if not confirmed:
            return {"requires_confirmation": True, "preview": preview}

        return _enqueue_and_wait(
            "send_message",
            {"chat_title": title, "message": text},
        )

    @mcp.tool()
    def whatsapp_job_status(job_id: str) -> dict[str, Any]:
        """Consulta por ID un trabajo de WhatsApp que quedó pendiente."""
        ident = str(job_id or "").strip()
        if not ident:
            raise ValueError("Debes indicar job_id.")
        return _request_json("GET", f"/wa/v1/internal/jobs/{ident}")
