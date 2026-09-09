from __future__ import annotations

import functools
import json
import os
from dataclasses import dataclass
from dotenv import load_dotenv

load_dotenv()


BITACORA_ACADEMICS_COMPAT_NOTE = (
    "COMPATIBILIDAD BITÁCORA: si la herramienta bitacora_docente no aparece en este chat, "
    "usa sieweb_academics con action=bitacora_policy, bitacora_status, "
    "bitacora_resolve_student, bitacora_student_history, bitacora_append_observation o "
    "bitacora_append_academic. Las dos acciones append son escrituras y conservan la misma "
    "regla de autorización: una orden explícita del docente para registrar/anotar en la bitácora "
    "permite confirmed=true. Nunca inventes estudiante, hora, causa o identificadores."
)


def _install_bridge_download_bootstrap() -> None:
    """Registra la ruta ZIP en FastMCP antes de que server_core cree `mcp`."""
    try:
        from mcp.server.fastmcp import FastMCP
    except Exception:
        return

    original_init = FastMCP.__init__
    if getattr(original_init, "_sieroom_bridge_download_bootstrap", False):
        return

    @functools.wraps(original_init)
    def init_with_bridge_download(self, *args, **kwargs):
        original_init(self, *args, **kwargs)
        try:
            from bridge_download import install as install_bridge_download

            install_bridge_download(self)
            print("SieRoom Bridge: descarga ZIP R6.2 habilitada.", flush=True)
        except Exception as exc:
            print(f"SieRoom Bridge: error habilitando descarga ZIP: {exc}", flush=True)

    setattr(init_with_bridge_download, "_sieroom_bridge_download_bootstrap", True)
    FastMCP.__init__ = init_with_bridge_download


_install_bridge_download_bootstrap()


def _install_bitacora_bootstrap() -> None:
    """Instala la política/herramienta de bitácora al crearse FastMCP."""
    try:
        from mcp.server.fastmcp import FastMCP
    except Exception:
        return

    original_init = FastMCP.__init__
    if getattr(original_init, "_sieroom_bitacora_bootstrap", False):
        return

    @functools.wraps(original_init)
    def init_with_bitacora(self, *args, **kwargs):
        original_init(self, *args, **kwargs)
        try:
            from bitacora import install as install_bitacora
            from bitacora_link_policy import install as install_bitacora_link_policy

            install_bitacora(self)
            install_bitacora_link_policy(self)
            try:
                server = getattr(self, "_mcp_server", None)
                current = str(getattr(server, "instructions", "") or "")
                if BITACORA_ACADEMICS_COMPAT_NOTE not in current and server is not None:
                    server.instructions = (current + "\n\n" + BITACORA_ACADEMICS_COMPAT_NOTE).strip()
            except Exception as exc:
                print(f"SieRoom Bitácora: no se pudo anexar fallback a instructions: {exc}", flush=True)
        except Exception as exc:
            print(f"SieRoom Bitácora: error habilitando módulo: {exc}", flush=True)

    setattr(init_with_bitacora, "_sieroom_bitacora_bootstrap", True)
    FastMCP.__init__ = init_with_bitacora


_install_bitacora_bootstrap()


def _install_bitacora_academics_compat() -> None:
    """Añade un fallback de bitácora dentro del tool ya existente sieweb_academics.

    Esto evita depender de que ChatGPT refresque inmediatamente el catálogo para descubrir
    el tool nuevo bitacora_docente: los chats con un esquema antiguo de SIEROOM pueden usar
    la firma estable sieweb_academics(action, payload_json, confirmed).
    """
    try:
        from mcp.server.fastmcp import FastMCP
    except Exception:
        return

    original_tool = FastMCP.tool
    if getattr(original_tool, "_sieroom_bitacora_academics_compat", False):
        return

    @functools.wraps(original_tool)
    def tool_with_bitacora_compat(self, *args, **kwargs):
        decorator = original_tool(self, *args, **kwargs)
        if not callable(decorator):
            return decorator

        def decorate(fn):
            if getattr(fn, "__name__", "") != "sieweb_academics":
                return decorator(fn)

            original_fn = fn

            @functools.wraps(original_fn)
            def sieweb_academics_with_bitacora(
                action: str, payload_json: str = "{}", confirmed: bool = False
            ) -> str:
                act = str(action or "").strip().lower()
                bitacora_actions = {
                    "bitacora_policy",
                    "bitacora_status",
                    "bitacora_resolve_student",
                    "bitacora_student_history",
                    "bitacora_append_observation",
                    "bitacora_append_academic",
                }
                if act not in bitacora_actions:
                    return original_fn(action, payload_json, confirmed)

                from bitacora import (
                    BITACORA_POLICY,
                    _history,
                    _parse_payload,
                    _preview_academic,
                    _preview_observation,
                    _resolve_student,
                    _sheets_append,
                    _spreadsheet_id,
                    _spreadsheet_url,
                    _verify_saved,
                )

                data = _parse_payload(payload_json)
                if act == "bitacora_policy":
                    result = {
                        "policy": BITACORA_POLICY,
                        "spreadsheet_id": _spreadsheet_id(),
                        "spreadsheet_url": _spreadsheet_url(),
                        "compatibility_route": "sieweb_academics",
                    }
                elif act == "bitacora_status":
                    result = {
                        "ok": True,
                        "available": True,
                        "compatibility_route": "sieweb_academics",
                        "reads": [
                            "bitacora_policy",
                            "bitacora_status",
                            "bitacora_resolve_student",
                            "bitacora_student_history",
                        ],
                        "writes": [
                            "bitacora_append_observation",
                            "bitacora_append_academic",
                        ],
                        "spreadsheet_id": _spreadsheet_id(),
                        "spreadsheet_url": _spreadsheet_url(),
                    }
                elif act == "bitacora_resolve_student":
                    result = _resolve_student(data)
                elif act == "bitacora_student_history":
                    result = _history(data)
                elif act == "bitacora_append_observation":
                    record, row = _preview_observation(data)
                    if not confirmed:
                        result = {
                            "requires_confirmation": True,
                            "preview": record,
                            "note": (
                                "Una orden explícita del docente para registrar/anotar en la "
                                "BITÁCORA permite repetir con confirmed=true."
                            ),
                            "spreadsheet_url": _spreadsheet_url(),
                        }
                    else:
                        updated_range = _sheets_append("BITÁCORA!A:R", row)
                        result = {
                            "ok": True,
                            "saved": True,
                            "kind": "BITÁCORA",
                            "record": record,
                            "verification": _verify_saved(updated_range, record["Registro_ID"]),
                            "spreadsheet_url": _spreadsheet_url(),
                        }
                else:
                    record, row = _preview_academic(data)
                    if not confirmed:
                        result = {
                            "requires_confirmation": True,
                            "preview": record,
                            "note": (
                                "Una orden explícita del docente para registrar/anotar en la "
                                "BITÁCORA permite repetir con confirmed=true."
                            ),
                            "spreadsheet_url": _spreadsheet_url(),
                        }
                    else:
                        updated_range = _sheets_append("ACADÉMICO!A:M", row)
                        result = {
                            "ok": True,
                            "saved": True,
                            "kind": "ACADÉMICO",
                            "record": record,
                            "verification": _verify_saved(updated_range, record["Registro_ID"]),
                            "spreadsheet_url": _spreadsheet_url(),
                        }
                return json.dumps(result, ensure_ascii=False, default=str)

            sieweb_academics_with_bitacora.__doc__ = (
                (original_fn.__doc__ or "")
                + "\n\nCompatibilidad BITÁCORA: action="
                + "bitacora_policy|bitacora_status|bitacora_resolve_student|"
                + "bitacora_student_history|bitacora_append_observation|bitacora_append_academic. "
                + "Las acciones append requieren confirmed=true; una orden explícita del docente "
                + "para registrar/anotar en la bitácora constituye autorización."
            )
            return decorator(sieweb_academics_with_bitacora)

        return decorate

    setattr(tool_with_bitacora_compat, "_sieroom_bitacora_academics_compat", True)
    FastMCP.tool = tool_with_bitacora_compat


_install_bitacora_academics_compat()


def _int(name: str, default: int) -> int:
    raw = os.getenv(name)
    return int(raw) if raw else default


def _first(*names: str, default: str = "") -> str:
    for name in names:
        value = os.getenv(name)
        if value:
            return value
    return default


@dataclass(frozen=True)
class Settings:
    # Render injecta PORT y RENDER_EXTERNAL_URL automáticamente.
    mcp_host: str = os.getenv("MCP_HOST", "0.0.0.0")
    mcp_port: int = _int("PORT", _int("MCP_PORT", 8000))
    public_base_url: str = _first(
        "MCP_PUBLIC_BASE_URL",
        "RENDER_EXTERNAL_URL",
        default="http://localhost:8000",
    ).rstrip("/")

    # OAuth que protege el MCP (Auth0).
    auth0_issuer: str = os.getenv("AUTH0_ISSUER", "").rstrip("/")
    auth0_audience: str = os.getenv("AUTH0_AUDIENCE", "")
    auth0_required_scope: str = os.getenv("AUTH0_REQUIRED_SCOPE", "santa:use")

    # Google Classroom.
    google_client_id: str = os.getenv("GOOGLE_CLIENT_ID", "")
    google_client_secret: str = os.getenv("GOOGLE_CLIENT_SECRET", "")
    google_refresh_token: str = os.getenv("GOOGLE_REFRESH_TOKEN", "")

    # Puente local del navegador para comentarios privados nativos de Classroom.
    classroom_bridge_secret: str = os.getenv("CLASSROOM_BRIDGE_SECRET", "")

    # SieWeb.
    sieweb_base_url: str = os.getenv(
        "SIEWEB_BASE_URL", "https://santaritadecasia.sieweb.com.pe"
    ).rstrip("/")
    sieweb_user: str = os.getenv("SIEWEB_USER", "")
    sieweb_password: str = os.getenv("SIEWEB_PASSWORD", "")

    # Compatibilidad con la v0.1; no usar en Render salvo emergencia.
    sieweb_cookie: str = os.getenv("SIEWEB_COOKIE", "")
    sieweb_authorization: str = os.getenv("SIEWEB_AUTHORIZATION", "")

    sieweb_timeout_seconds: int = _int("SIEWEB_TIMEOUT_SECONDS", 30)
    sieweb_id_ambito_registro_notas: int = _int(
        "SIEWEB_ID_AMBITO_REGISTRO_NOTAS", 518
    )

    @property
    def mcp_resource_url(self) -> str:
        return f"{self.public_base_url}/mcp"


settings = Settings()
