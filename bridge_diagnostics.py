"""Read-only Bridge negotiation and HTTP diagnostics; never claims queued work."""
from __future__ import annotations
import os
import asyncio
import requests
from starlette.responses import JSONResponse
from bridge import ClassroomBridgeQueue

RELEASE = "0.8.7-R6.8-SRC-1"
VERSION = "0.8.7"
BUILD = "0.8.7-HF4-GRADE-TARGET-DEDUP-SINGLE-PASS-R6.2"
CAPABILITIES = {
    "post_private_comment", "read_private_comments", "verified_private_comment_read_v4",
    "student_scoped_private_comment_read", "browser_grade_return", "teacher_account_guard",
    "target_submission_guard", "grade_target_guard_v1",
}
ACCEPTED_BUILDS = {BUILD, "0.8.7-HF4-R6.8-CLAIM-CAPABILITY-RESTORE",
                   "0.8.7-HF4-R6.9-DETAILED-FEEDBACK-CORE"}
BASE_URL = "https://sieroom-src.onrender.com"


def compatibility(headers):
    capabilities = {s.strip().lower() for s in headers.get("x-sieroom-bridge-capabilities", "").split(",")}
    missing = sorted(CAPABILITIES - capabilities)
    compatible = (headers.get("x-sieroom-bridge-version") == VERSION
                  and headers.get("x-sieroom-bridge-build") in ACCEPTED_BUILDS and not missing)
    return {
        "ok": compatible, "compatible": compatible, "version": VERSION, "release": RELEASE,
        "bridge": "SieRoom Classroom Bridge", "missing_capabilities": missing,
        "teacher_account_guard": True, "target_submission_guard": True,
        "triple_contract": bool(getattr(ClassroomBridgeQueue, "_sieroom_triple_contract_r62", False)),
        "operations": ["read_private_comments", "post_private_comment", "browser_grade_return"],
        "read_only": True,
    }


def run_diagnostics():
    # Fixed destination: no caller-controlled URL or credential forwarding.
    secret = os.environ.get("CLASSROOM_BRIDGE_SECRET", "").strip()
    headers = {"X-SieRoom-Bridge-Secret": secret, "X-SieRoom-Bridge-Version": VERSION,
               "X-SieRoom-Bridge-Build": BUILD,
               "X-SieRoom-Bridge-Capabilities": ",".join(sorted(CAPABILITIES))}
    checks = {}
    for label, path, request_headers, expected in [
        ("unauthorized", "/bridge/v1/status", {}, 401),
        ("wrong_secret", "/bridge/v1/status", {"X-SieRoom-Bridge-Secret": "invalid-diagnostic-secret"}, 401),
        ("status", "/bridge/v1/status", headers, 200),
        ("compatibility", "/bridge/v1/compatibility", headers, 200),
        ("incompatible_version", "/bridge/v1/compatibility", {**headers, "X-SieRoom-Bridge-Version": "0.0.0"}, 409),
        ("incompatible_build", "/bridge/v1/compatibility", {**headers, "X-SieRoom-Bridge-Build": "unknown"}, 409),
        ("public_mcp_blocked", "/mcp", headers, 404),
    ]:
        try:
            response = requests.get(BASE_URL + path, headers=request_headers, timeout=45, allow_redirects=False)
            try: data = response.json()
            except ValueError: data = {}
            valid = response.status_code == expected
            if expected == 401: valid = valid and data.get("error") == "bridge_unauthorized"
            if label == "status":
                valid = valid and data.get("ok") is True and data.get("bridge") == "SieRoom Classroom Bridge" and isinstance(data.get("queue"), dict)
            if label == "compatibility": valid = valid and data.get("compatible") is True and data.get("triple_contract") is True
            if expected == 409: valid = valid and data.get("compatible") is False
            checks[label] = {"passed": valid, "http_status": response.status_code}
            if label == "status": checks[label]["queue"] = data.get("queue", {})
            if label == "compatibility": checks[label]["contract"] = data
        except requests.RequestException:
            checks[label] = {"passed": False, "error": "connection_failed_or_timeout"}
    return {"ok": all(x["passed"] for x in checks.values()), "release": RELEASE,
            "read_only": True, "checks": checks}


def install(mcp):
    @mcp.custom_route("/bridge/v1/compatibility", methods=["GET"])
    async def bridge_compatibility(request):
        from server_core import _bridge_auth_ok, _bridge_unauthorized
        if not _bridge_auth_ok(request): return _bridge_unauthorized()
        result = compatibility(request.headers)
        return JSONResponse(result, status_code=200 if result["compatible"] else 409)

    @mcp.tool()
    async def bridge_connection_diagnostics() -> dict:
        """Comprueba conexión HTTP, autorización y contrato Bridge sin reclamar trabajos ni modificar Classroom."""
        return await asyncio.to_thread(run_diagnostics)
