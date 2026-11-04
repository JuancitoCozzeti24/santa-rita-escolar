"""Relay autorizado de API SIEweb mediante la sesión verificada del navegador.

No recibe ni almacena códigos OTP, contraseñas, cookies ni tokens de SIEweb.
Los trabajos se generan exclusivamente desde el cliente SIEweb del servidor;
el navegador conectado ejecuta peticiones de la API de la misma institución.
Las rutas HTTP quedan protegidas por PrivatePathGate y el secreto Bridge.
"""
from __future__ import annotations

import json
import re
import threading
import time
import uuid
from dataclasses import dataclass, field
from typing import Any

from starlette.requests import Request
from starlette.responses import JSONResponse


class SieWebRelayError(RuntimeError):
    pass


@dataclass
class RelayJob:
    id: str
    method: str
    path: str
    params: dict[str, Any] | None
    payload: dict[str, Any] | list[Any] | None
    created: float = field(default_factory=time.monotonic)
    claimed_at: float = 0.0
    attempts: int = 0
    result: dict[str, Any] | None = None
    error: str = ""
    done: threading.Event = field(default_factory=threading.Event)

    def public(self) -> dict[str, Any]:
        # El servidor envia solo la solicitud necesaria; jamás credenciales.
        return {
            "id": self.id,
            "method": self.method,
            "path": self.path,
            "params": self.params,
            "payload": self.payload,
        }


class VerifiedBrowserRelay:
    PULSE_MAX_AGE_SECONDS = 12.0
    JOB_TIMEOUT_SECONDS = 38.0
    MAX_RETRIES = 1

    def __init__(self) -> None:
        self._lock = threading.RLock()
        self._jobs: dict[str, RelayJob] = {}
        self._last_verified_pulse = 0.0
        self._browser_error = ""

    def pulse(self, *, verified: bool, reason: str = "") -> dict[str, Any]:
        with self._lock:
            if verified:
                self._last_verified_pulse = time.monotonic()
                self._browser_error = ""
            else:
                self._last_verified_pulse = 0.0
                self._browser_error = re.sub(r"[^a-z0-9_ -]", "", str(reason).lower())[:80]
            return self.status()

    def status(self) -> dict[str, Any]:
        with self._lock:
            active = (time.monotonic() - self._last_verified_pulse) < self.PULSE_MAX_AGE_SECONDS
            return {
                "verified_browser_session": bool(active),
                "transport": "user_browser_mfa_verified",
                "pending_requests": sum(not j.done.is_set() for j in self._jobs.values()),
                "last_error_hint": self._browser_error,
            }

    def is_ready(self) -> bool:
        return bool(self.status()["verified_browser_session"])

    @staticmethod
    def _validate_request(method: str, path: str) -> tuple[str, str]:
        method = str(method).upper()
        path = str(path)
        if method not in {"GET", "POST", "PUT"}:
            raise SieWebRelayError("Método no admitido por el puente de SieWeb.")
        if (not path.startswith("/lms/api/") or path.startswith("/lms/api/login/")
                or "?" in path or "#" in path
                or "\\" in path or "//" in path or ".." in path):
            raise SieWebRelayError("Ruta de API de SieWeb no permitida.")
        return method, path

    def request(
        self,
        method: str,
        path: str,
        *,
        params: dict[str, Any] | None = None,
        payload: dict[str, Any] | list[Any] | None = None,
    ) -> dict[str, Any]:
        method, path = self._validate_request(method, path)
        if not self.is_ready():
            raise SieWebRelayError(
                "Abre SieWeb con tu cuenta y valida el código en el navegador "
                "con la extensión SieRoom actualizada y su pestaña Bridge abierta."
            )
        job = RelayJob(
            id=str(uuid.uuid4()), method=method, path=path, params=params, payload=payload
        )
        with self._lock:
            self._jobs[job.id] = job
        try:
            if not job.done.wait(self.JOB_TIMEOUT_SECONDS):
                raise SieWebRelayError(
                    "La pestaña de SieWeb no respondió al trabajo de lectura/escritura. "
                    "Comprueba que la sesión continúe activa; no se reintentó la petición."
                )
            if job.error:
                raise SieWebRelayError(job.error)
            if not isinstance(job.result, dict):
                raise SieWebRelayError("La API de SieWeb no devolvió un objeto JSON verificable.")
            return job.result
        finally:
            with self._lock:
                self._jobs.pop(job.id, None)

    def next_job(self) -> dict[str, Any] | None:
        with self._lock:
            for j in self._jobs.values():
                if j.done.is_set():
                    continue
                if j.claimed_at:
                    # Nunca repetir una escritura cuyo resultado pueda ser ambiguo.
                    continue
                j.claimed_at = time.monotonic()
                j.attempts += 1
                return j.public()
        return None

    def complete(
        self, job_id: str, *, status_code: int, data: Any = None, error: str = ""
    ) -> bool:
        with self._lock:
            j = self._jobs.get(str(job_id))
            if not j or not j.claimed_at or j.done.is_set():
                return False
            if not 200 <= int(status_code) < 300:
                # No incluir respuesta cruda; puede llevar datos sensibles.
                j.error = (
                    f"SieWeb respondió HTTP {int(status_code)} al ejecutar una petición. "
                    "La operación no se considera confirmada."
                )
            elif error:
                j.error = "No se pudo validar la respuesta de SieWeb en el navegador."
            elif not isinstance(data, dict):
                j.error = "SieWeb devolvió datos no JSON o estructura inesperada."
            else:
                j.result = data
            j.done.set()
            return True


relay = VerifiedBrowserRelay()


def install(mcp: Any) -> None:
    if getattr(mcp, "_sieweb_verified_browser_relay_installed", False):
        return

    @mcp.custom_route("/bridge/v1/sieweb/pulse", methods=["POST"])
    async def pulse(request: Request) -> JSONResponse:
        if int(request.headers.get("content-length") or "0") > 4096:
            return JSONResponse({"ok": False, "error": "payload_too_large"}, status_code=413)
        obj = await request.json()
        # Este servicio nunca acepta ni espera códigos de verificación.
        result = relay.pulse(
            verified=obj.get("session_verified") is True,
            reason=str(obj.get("reason") or ""),
        )
        return JSONResponse({"ok": True, **result})

    @mcp.custom_route("/bridge/v1/sieweb/next", methods=["GET"])
    async def next_job(_request: Request) -> JSONResponse:
        return JSONResponse({"ok": True, "job": relay.next_job()})

    @mcp.custom_route("/bridge/v1/sieweb/result", methods=["POST"])
    async def complete(request: Request) -> JSONResponse:
        raw = await request.body()
        if len(raw) > 4_000_000:
            return JSONResponse({"ok": False, "error": "payload_too_large"}, status_code=413)
        try:
            obj = json.loads(raw)
            success = relay.complete(
                obj.get("job_id", ""),
                status_code=int(obj.get("status_code", 0)),
                data=obj.get("data"),
                error=str(obj.get("error") or "")[:100],
            )
        except (ValueError, TypeError, AttributeError):
            success = False
        return JSONResponse({"ok": bool(success)}, status_code=200 if success else 409)

    @mcp.custom_route("/bridge/v1/sieweb/status", methods=["GET"])
    async def relay_status(_request: Request) -> JSONResponse:
        return JSONResponse({"ok": True, **relay.status()})

    setattr(mcp, "_sieweb_verified_browser_relay_installed", True)
