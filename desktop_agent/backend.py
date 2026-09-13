from __future__ import annotations

from typing import Any
import json
import requests

from .observation import Observation
from .classroom_review import StudentReview
from .settings import DesktopSettings
from .vision import Decision


class BackendConnection:
    def __init__(self, settings: DesktopSettings) -> None:
        if not settings.backend_url or not settings.backend_secret:
            raise RuntimeError("Falta configurar la conexión con SieRoom.")
        self.base_url = settings.backend_url
        self.headers = {
            "x-sieroom-desktop-secret": settings.backend_secret,
            "content-type": "application/json",
        }

    def post(self, path: str, body: dict[str, Any]) -> dict[str, Any]:
        response = requests.post(self.base_url + path, headers=self.headers, json=body, timeout=240)
        if not response.ok:
            raise RuntimeError(f"SieRoom HTTP {response.status_code}: {response.text[:900]}")
        data = response.json()
        if not data.get("ok", False):
            raise RuntimeError(str(data.get("error") or "SieRoom devolvió un error."))
        return data

    def status(self) -> dict[str, Any]:
        return self.post("/desktop/v1/status", {})


class BackendClassroomClient:
    def __init__(self, connection: BackendConnection) -> None:
        self.connection = connection

    def _call(self, action: str, **payload: Any) -> Any:
        return self.connection.post("/desktop/v1/classroom", {"action": action, **payload})["result"]

    def list_courses(self, active_only: bool = True):
        return self._call("list_courses", active_only=active_only)

    def list_coursework(self, course_id: str, include_drafts: bool = False):
        return self._call("list_coursework", course_id=course_id, include_drafts=include_drafts)

    def list_students(self, course_id: str):
        return self._call("list_students", course_id=course_id)

    def list_submissions(self, course_id: str, course_work_id: str):
        return self._call("list_submissions", course_id=course_id, course_work_id=course_work_id)

    def get_submission(self, course_id: str, course_work_id: str, submission_id: str):
        return self._call(
            "get_submission", course_id=course_id, course_work_id=course_work_id, submission_id=submission_id
        )

    def grade_submission(self, course_id: str, course_work_id: str, submission_id: str, *, grade: float, return_to_student: bool = False):
        return self._call(
            "grade_submission", course_id=course_id, course_work_id=course_work_id,
            submission_id=submission_id, grade=grade, return_to_student=return_to_student,
        )

    def return_submission(self, course_id: str, course_work_id: str, submission_id: str, *, finalize_draft: bool = True):
        return self._call(
            "return_submission", course_id=course_id, course_work_id=course_work_id,
            submission_id=submission_id, finalize_draft=finalize_draft,
        )


class BackendReviewer:
    def __init__(self, connection: BackendConnection) -> None:
        self.connection = connection

    def review(self, **payload: Any) -> StudentReview:
        data = self.connection.post("/desktop/v1/review", payload)
        return StudentReview.from_public(data["review"])


class BackendVisionPlanner:
    def __init__(self, connection: BackendConnection) -> None:
        self.connection = connection

    def decide(self, goal: str, observation: Observation, history: list[dict[str, Any]]) -> Decision:
        data = self.connection.post("/desktop/v1/vision", {
            "goal": goal,
            "observation": {
                "url": observation.url, "title": observation.title,
                "screenshot_b64": observation.screenshot_b64, "viewport": observation.viewport,
            },
            "history": history,
        })["decision"]
        return Decision(**data)
