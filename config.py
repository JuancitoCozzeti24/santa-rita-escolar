from __future__ import annotations

import os
from dataclasses import dataclass
from dotenv import load_dotenv

load_dotenv()


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
