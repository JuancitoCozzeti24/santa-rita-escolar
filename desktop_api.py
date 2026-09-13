from __future__ import annotations

from dataclasses import asdict
from typing import Any
import secrets

from starlette.requests import Request
from starlette.responses import JSONResponse

from config import settings
from desktop_agent.observation import Observation
from desktop_agent.classroom_review import SubmissionReviewer
from desktop_agent.settings import DesktopSettings
from desktop_agent.vision import VisionPlanner


def install(mcp: Any, classroom: Any) -> None:
    def authorized(request: Request) -> bool:
        expected = str(settings.classroom_bridge_secret or "")
        provided = str(request.headers.get("x-sieroom-desktop-secret") or "")
        return bool(expected and provided and secrets.compare_digest(expected, provided))

    async def body(request: Request) -> dict[str, Any]:
        try:
            return dict(await request.json())
        except Exception:
            return {}

    def denied() -> JSONResponse:
        return JSONResponse({"ok": False, "error": "desktop_unauthorized"}, status_code=401)

    @mcp.custom_route("/desktop/v1/status", methods=["POST"])
    async def desktop_status(request: Request):
        if not authorized(request):
            return denied()
        desktop = DesktopSettings.from_env()
        return JSONResponse({
            "ok": True,
            "classroom_configured": bool(settings.google_client_id and settings.google_client_secret and settings.google_refresh_token),
            "openai_configured": bool(desktop.openai_api_key),
        })

    @mcp.custom_route("/desktop/v1/classroom", methods=["POST"])
    async def desktop_classroom(request: Request):
        if not authorized(request):
            return denied()
        data = await body(request)
        action = str(data.pop("action", ""))
        allowed = {
            "list_courses", "list_coursework", "list_students", "list_submissions",
            "get_submission", "grade_submission", "return_submission",
        }
        if action not in allowed:
            return JSONResponse({"ok": False, "error": "Acción no permitida."}, status_code=400)
        try:
            result = getattr(classroom, action)(**data)
            return JSONResponse({"ok": True, "result": result})
        except Exception as exc:
            return JSONResponse({"ok": False, "error": str(exc)}, status_code=400)

    @mcp.custom_route("/desktop/v1/review", methods=["POST"])
    async def desktop_review(request: Request):
        if not authorized(request):
            return denied()
        data = await body(request)
        try:
            reviewer = SubmissionReviewer(DesktopSettings.from_env(), classroom)
            review = reviewer.review(**data)
            return JSONResponse({"ok": True, "review": review.public()})
        except Exception as exc:
            return JSONResponse({"ok": False, "error": str(exc)}, status_code=400)

    @mcp.custom_route("/desktop/v1/vision", methods=["POST"])
    async def desktop_vision(request: Request):
        if not authorized(request):
            return denied()
        data = await body(request)
        try:
            observation = Observation(**data["observation"])
            decision = VisionPlanner(DesktopSettings.from_env()).decide(
                str(data["goal"]), observation, list(data.get("history") or [])
            )
            return JSONResponse({"ok": True, "decision": asdict(decision)})
        except Exception as exc:
            return JSONResponse({"ok": False, "error": str(exc)}, status_code=400)
