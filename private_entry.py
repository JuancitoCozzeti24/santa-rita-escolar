"""Render institutional entrypoint: private, no-login MCP endpoint.

This intentionally avoids Auth0 and interactive authorization. A secret URL prefix
acts as a bearer capability, derived from the existing Classroom bridge secret.
Do not publish the private endpoint URL outside the owner's ChatGPT connection.
"""
from __future__ import annotations

import hashlib
import os
from starlette.responses import PlainTextResponse
from server import mcp

BRIDGE_SECRET = os.environ.get("CLASSROOM_BRIDGE_SECRET", "").strip()
if len(BRIDGE_SECRET) < 24:
    raise RuntimeError(
        "CLASSROOM_BRIDGE_SECRET missing or too short; refusing to expose school tools."
    )

# Domain-separated derivation: never show or reuse the raw bridge secret.
PRIVATE_PREFIX = "/sieroom-" + hashlib.sha256(
    ("sieroom-private-mcp-v1:" + BRIDGE_SECRET).encode("utf-8")
).hexdigest()
_original_app_factory = mcp.streamable_http_app


class PrivatePathGate:
    """Allow only /<private-prefix>/... and strip the prefix before routing."""

    def __init__(self, app):
        self.app = app

    async def __call__(self, scope, receive, send):
        if scope["type"] == "lifespan":
            await self.app(scope, receive, send)
            return
        if scope["type"] not in ("http", "websocket"):
            return

        path = scope.get("path", "")
        if not (path == PRIVATE_PREFIX or path.startswith(PRIVATE_PREFIX + "/")):
            if scope["type"] == "http":
                response = PlainTextResponse("Not found", status_code=404)
                await response(scope, receive, send)
            else:
                await send({"type": "websocket.close", "code": 1008})
            return

        inner_scope = dict(scope)
        inner_scope["path"] = path[len(PRIVATE_PREFIX):] or "/"
        if "raw_path" in inner_scope:
            inner_scope["raw_path"] = inner_scope["path"].encode("utf-8")
        await self.app(inner_scope, receive, send)


def _private_app_factory():
    return PrivatePathGate(_original_app_factory())


mcp.streamable_http_app = _private_app_factory

if __name__ == "__main__":
    # This is a sensitive capability URL. Keep Render logs and ChatGPT connector
    # configuration private; anybody with the full URL can call school tools.
    print(f"SIEROOM_PRIVATE_MCP_PATH={PRIVATE_PREFIX}/mcp", flush=True)
    mcp.run(transport="streamable-http")
