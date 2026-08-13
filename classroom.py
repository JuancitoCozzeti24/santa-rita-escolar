from __future__ import annotations

from datetime import date, time
from typing import Any, Iterable

import requests

from config import settings


class ClassroomError(RuntimeError):
    pass


class ClassroomClient:
    API = "https://classroom.googleapis.com/v1"
    TOKEN_URL = "https://oauth2.googleapis.com/token"

    def __init__(self) -> None:
        self._access_token: str | None = None

    def _ensure_configured(self) -> None:
        missing = [
            name
            for name, value in [
                ("GOOGLE_CLIENT_ID", settings.google_client_id),
                ("GOOGLE_CLIENT_SECRET", settings.google_client_secret),
                ("GOOGLE_REFRESH_TOKEN", settings.google_refresh_token),
            ]
            if not value
        ]
        if missing:
            raise ClassroomError(
                "Falta configurar OAuth de Google: " + ", ".join(missing)
            )

    def _refresh_access_token(self) -> str:
        self._ensure_configured()
        response = requests.post(
            self.TOKEN_URL,
            data={
                "client_id": settings.google_client_id,
                "client_secret": settings.google_client_secret,
                "refresh_token": settings.google_refresh_token,
                "grant_type": "refresh_token",
            },
            timeout=30,
        )
        if not response.ok:
            raise ClassroomError(
                f"Google OAuth falló ({response.status_code}): {response.text[:500]}"
            )
        data = response.json()
        token = data.get("access_token")
        if not token:
            raise ClassroomError("Google OAuth no devolvió access_token.")
        self._access_token = token
        return token

    def _request(
        self,
        method: str,
        path: str,
        *,
        params: dict[str, Any] | None = None,
        json: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        token = self._access_token or self._refresh_access_token()
        headers = {"Authorization": f"Bearer {token}"}
        url = f"{self.API}/{path.lstrip('/')}"
        response = requests.request(
            method, url, headers=headers, params=params, json=json, timeout=30
        )
        if response.status_code == 401:
            headers["Authorization"] = f"Bearer {self._refresh_access_token()}"
            response = requests.request(
                method, url, headers=headers, params=params, json=json, timeout=30
            )
        if not response.ok:
            raise ClassroomError(
                f"Classroom API {method} {path} falló ({response.status_code}): "
                f"{response.text[:1000]}"
            )
        return response.json() if response.content else {}

    def _paginate(
        self, path: str, key: str, *, params: dict[str, Any] | None = None
    ) -> list[dict[str, Any]]:
        out: list[dict[str, Any]] = []
        page_token: str | None = None
        base = dict(params or {})
        while True:
            query = dict(base)
            if page_token:
                query["pageToken"] = page_token
            data = self._request("GET", path, params=query)
            out.extend(data.get(key, []))
            page_token = data.get("nextPageToken")
            if not page_token:
                return out

    def list_courses(self, active_only: bool = True) -> list[dict[str, Any]]:
        params: dict[str, Any] = {"teacherId": "me", "pageSize": 100}
        if active_only:
            params["courseStates"] = "ACTIVE"
        courses = self._paginate("courses", "courses", params=params)
        return [
            {
                "id": c.get("id"),
                "name": c.get("name"),
                "section": c.get("section"),
                "room": c.get("room"),
                "courseState": c.get("courseState"),
                "alternateLink": c.get("alternateLink"),
            }
            for c in courses
        ]

    def list_students(self, course_id: str) -> list[dict[str, Any]]:
        students = self._paginate(
            f"courses/{course_id}/students", "students", params={"pageSize": 100}
        )
        return [
            {
                "userId": s.get("userId"),
                "name": (s.get("profile") or {}).get("name", {}).get("fullName"),
                "email": (s.get("profile") or {}).get("emailAddress"),
            }
            for s in students
        ]

    def list_coursework(
        self, course_id: str, *, include_drafts: bool = True
    ) -> list[dict[str, Any]]:
        params: dict[str, Any] = {"pageSize": 100, "orderBy": "updateTime desc"}
        if include_drafts:
            params["courseWorkStates"] = ["PUBLISHED", "DRAFT"]
        work = self._paginate(
            f"courses/{course_id}/courseWork", "courseWork", params=params
        )
        return [
            {
                "id": w.get("id"),
                "title": w.get("title"),
                "description": w.get("description"),
                "state": w.get("state"),
                "workType": w.get("workType"),
                "maxPoints": w.get("maxPoints"),
                "dueDate": w.get("dueDate"),
                "dueTime": w.get("dueTime"),
                "topicId": w.get("topicId"),
                "alternateLink": w.get("alternateLink"),
                "creationTime": w.get("creationTime"),
                "updateTime": w.get("updateTime"),
            }
            for w in work
        ]

    def list_submissions(
        self, course_id: str, course_work_id: str
    ) -> list[dict[str, Any]]:
        submissions = self._paginate(
            f"courses/{course_id}/courseWork/{course_work_id}/studentSubmissions",
            "studentSubmissions",
            params={"pageSize": 100},
        )
        return [
            {
                "id": s.get("id"),
                "userId": s.get("userId"),
                "state": s.get("state"),
                "late": s.get("late", False),
                "draftGrade": s.get("draftGrade"),
                "assignedGrade": s.get("assignedGrade"),
                "updateTime": s.get("updateTime"),
                "alternateLink": s.get("alternateLink"),
            }
            for s in submissions
        ]

    def create_coursework(
        self,
        course_id: str,
        *,
        title: str,
        description: str = "",
        max_points: float | None = None,
        due_date: date | None = None,
        due_time: time | None = None,
        topic_id: str | None = None,
        publish: bool = False,
    ) -> dict[str, Any]:
        payload: dict[str, Any] = {
            "title": title,
            "description": description,
            "workType": "ASSIGNMENT",
            "state": "PUBLISHED" if publish else "DRAFT",
        }
        if max_points is not None:
            payload["maxPoints"] = max_points
        if due_date is not None:
            payload["dueDate"] = {
                "year": due_date.year,
                "month": due_date.month,
                "day": due_date.day,
            }
        if due_time is not None:
            payload["dueTime"] = {
                "hours": due_time.hour,
                "minutes": due_time.minute,
            }
        if topic_id:
            payload["topicId"] = topic_id
        return self._request("POST", f"courses/{course_id}/courseWork", json=payload)

    def grade_submission(
        self,
        course_id: str,
        course_work_id: str,
        submission_id: str,
        *,
        grade: float,
        return_to_student: bool = False,
    ) -> dict[str, Any]:
        updated = self._request(
            "PATCH",
            f"courses/{course_id}/courseWork/{course_work_id}/studentSubmissions/{submission_id}",
            params={"updateMask": "draftGrade,assignedGrade"},
            json={"draftGrade": grade, "assignedGrade": grade},
        )
        if return_to_student:
            self._request(
                "POST",
                f"courses/{course_id}/courseWork/{course_work_id}/studentSubmissions/{submission_id}:return",
                json={},
            )
        return updated

    def missing_students(
        self, course_id: str, course_work_id: str
    ) -> list[dict[str, Any]]:
        students = {s["userId"]: s for s in self.list_students(course_id)}
        submissions = self.list_submissions(course_id, course_work_id)
        completed_states = {"TURNED_IN", "RETURNED"}
        missing: list[dict[str, Any]] = []
        for sub in submissions:
            if sub.get("state") not in completed_states:
                student = students.get(sub.get("userId"), {})
                missing.append({**student, "submission": sub})
        return missing
