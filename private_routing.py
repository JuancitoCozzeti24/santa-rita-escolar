"""Two independent access paths: private MCP and secret-authenticated Bridge."""
from __future__ import annotations
import secrets
from starlette.middleware.cors import CORSMiddleware
from starlette.responses import JSONResponse, PlainTextResponse


class PrivatePathGate:
    def __init__(self, app, private_prefix: str, bridge_secret: str):
        self.app = app
        self.private_prefix = private_prefix
        self.bridge_secret = bridge_secret
        # Extension pages in Brave and Chrome both use chrome-extension://.
        # Preflight exposes no data; every actual request still needs the secret.
        self.bridge_app = CORSMiddleware(
            self._authenticated_bridge,
            allow_origin_regex=r"chrome-extension://[a-p]{32}",
            allow_methods=["GET", "POST"],
            allow_headers=["Content-Type", "X-SieRoom-Bridge-Secret",
                           "X-SieRoom-Bridge-Version", "X-SieRoom-Bridge-Build",
                           "X-SieRoom-Bridge-Capabilities", "X-SieRoom-Delete-Capability"],
            allow_credentials=False,
        )

    async def _authenticated_bridge(self, scope, receive, send):
        headers = dict(scope.get("headers", []))
        provided = headers.get(b"x-sieroom-bridge-secret", b"")
        expected = self.bridge_secret.encode("utf-8")
        if not expected or not secrets.compare_digest(expected, provided):
            await JSONResponse({"ok": False, "error": "bridge_unauthorized"}, 401)(scope, receive, send)
            return
        # Route handlers enforce version, build, capabilities, account and target.
        await self.app(scope, receive, send)

    async def __call__(self, scope, receive, send):
        if scope["type"] == "lifespan":
            await self.app(scope, receive, send)
            return
        if scope["type"] not in ("http", "websocket"):
            return
        path = scope.get("path", "")
        if scope["type"] == "http" and path.startswith("/bridge/v1/"):
            await self.bridge_app(scope, receive, send)
            return
        if not (path == self.private_prefix or path.startswith(self.private_prefix + "/")):
            if scope["type"] == "http":
                await PlainTextResponse("Not found", 404)(scope, receive, send)
            else:
                await send({"type": "websocket.close", "code": 1008})
            return
        inner_scope = dict(scope)
        inner_scope["path"] = path[len(self.private_prefix):] or "/"
        if "raw_path" in inner_scope:
            inner_scope["raw_path"] = inner_scope["path"].encode("utf-8")
        await self.app(inner_scope, receive, send)
