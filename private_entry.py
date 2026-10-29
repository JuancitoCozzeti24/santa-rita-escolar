"""Render institutional entrypoint: private, no-login MCP endpoint.

This intentionally avoids Auth0 and interactive authorization. A secret URL prefix
acts as a bearer capability, derived from the existing Classroom bridge secret.
Do not publish the private endpoint URL outside the owner's ChatGPT connection.
"""
from __future__ import annotations

import hashlib
import os
from private_routing import PrivatePathGate
from bridge_policy_hotfix import install as install_bridge_guards
install_bridge_guards()
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


def _private_app_factory():
    return PrivatePathGate(_original_app_factory(), PRIVATE_PREFIX, BRIDGE_SECRET)


mcp.streamable_http_app = _private_app_factory

from bridge_diagnostics import install as install_bridge_diagnostics
install_bridge_diagnostics(mcp)

if __name__ == "__main__":
    # This is a sensitive capability URL. Keep Render logs and ChatGPT connector
    # configuration private; anybody with the full URL can call school tools.
    print(f"SIEROOM_PRIVATE_MCP_PATH={PRIVATE_PREFIX}/mcp", flush=True)
    mcp.run(transport="streamable-http")
