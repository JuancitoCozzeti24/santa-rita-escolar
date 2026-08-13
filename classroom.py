from __future__ import annotations

from datetime import date, time
from typing import Any

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
            raise ClassroomError("Falta configurar OAuth de Google: " + ", ".join(missing))

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
            raise ClassroomError(f"Google OAuth falló ({response.status_code}): {response.text[:500]}")
        data = response.json()
        token = data.get("access_token")
        if not token:
            raise ClassroomError("Google OAuth no devolvió access_token.")
        self._access_token = token
        return token

    def _request(self, method: str, path: str, *, params: dict[str, Any] | None = None,
                 json: dict[str, Any] | None = None) -> dict[str, Any]:
        token = self._access_token or self._refresh_access_token()
        headers = {"Authorization": f"Bearer {token}"}
        url = f"{self.API}/{path.lstrip('/')}"
        response = requests.request(method, url, headers=headers, params=params, json=json, timeout=30)
        if response.status_code == 401:
            headers["Authorization"] = f"Bearer {self._refresh_access_token()}"
            response = requests.request(method, url, headers=headers, params=params, json=json, timeout=30)
        if not response.ok:
            raise ClassroomError(
                f"Classroom API {method} {path} falló ({response.status_code}): {response.text[:1200]}"
            )
        return response.json() if response.content else {}

    def _paginate(self, path: str, key: str, *, params: dict[str, Any] | None = None) -> list[dict[str, Any]]:
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

    @staticmethod
    def _profile(person: dict[str, Any]) -> dict[str, Any]:
        p = person.get("profile") or {}
        return {
            "userId": person.get("userId"),
            "name": (p.get("name") or {}).get("fullName"),
            "email": p.get("emailAddress"),
            "photoUrl": p.get("photoUrl"),
        }

    def list_courses(self, active_only: bool = True) -> list[dict[str, Any]]:
        params: dict[str, Any] = {"teacherId": "me", "pageSize": 100}
        if active_only:
            params["courseStates"] = "ACTIVE"
        courses = self._paginate("courses", "courses", params=params)
        return [{k: c.get(k) for k in (
            "id","name","section","descriptionHeading","description","room","ownerId",
            "courseState","alternateLink","calendarId","teacherGroupEmail","courseGroupEmail"
        )} for c in courses]

    def get_course(self, course_id: str) -> dict[str, Any]:
        return self._request("GET", f"courses/{course_id}")

    def list_students(self, course_id: str) -> list[dict[str, Any]]:
        students = self._paginate(f"courses/{course_id}/students", "students", params={"pageSize": 100})
        return [self._profile(s) for s in students]

    def list_teachers(self, course_id: str) -> list[dict[str, Any]]:
        teachers = self._paginate(f"courses/{course_id}/teachers", "teachers", params={"pageSize": 100})
        return [self._profile(t) for t in teachers]

    def list_topics(self, course_id: str) -> list[dict[str, Any]]:
        topics = self._paginate(f"courses/{course_id}/topics", "topic", params={"pageSize": 100})
        return [{"topicId": t.get("topicId"), "name": t.get("name"), "updateTime": t.get("updateTime")} for t in topics]

    def create_topic(self, course_id: str, name: str) -> dict[str, Any]:
        return self._request("POST", f"courses/{course_id}/topics", json={"name": name})

    def list_announcements(self, course_id: str, include_drafts: bool = True) -> list[dict[str, Any]]:
        params: dict[str, Any] = {"pageSize": 100, "orderBy": "updateTime desc"}
        if include_drafts:
            params["announcementStates"] = ["PUBLISHED", "DRAFT"]
        items = self._paginate(f"courses/{course_id}/announcements", "announcements", params=params)
        return [{k: a.get(k) for k in (
            "id","text","state","alternateLink","creationTime","updateTime","scheduledTime",
            "assigneeMode","individualStudentsOptions","materials"
        )} for a in items]

    def create_announcement(self, course_id: str, *, text: str, publish: bool = False,
                            topic_id: str | None = None) -> dict[str, Any]:
        payload: dict[str, Any] = {"text": text, "state": "PUBLISHED" if publish else "DRAFT"}
        # Announcement no usa topicId en la API pública actual; se conserva parámetro por compatibilidad futura.
        return self._request("POST", f"courses/{course_id}/announcements", json=payload)

    def list_coursework(self, course_id: str, *, include_drafts: bool = True) -> list[dict[str, Any]]:
        params: dict[str, Any] = {"pageSize": 100, "orderBy": "updateTime desc"}
        if include_drafts:
            params["courseWorkStates"] = ["PUBLISHED", "DRAFT"]
        work = self._paginate(f"courses/{course_id}/courseWork", "courseWork", params=params)
        return [self._compact_coursework(w) for w in work]

    def get_coursework(self, course_id: str, course_work_id: str) -> dict[str, Any]:
        return self._request("GET", f"courses/{course_id}/courseWork/{course_work_id}")

    @staticmethod
    def _compact_coursework(w: dict[str, Any]) -> dict[str, Any]:
        return {k: w.get(k) for k in (
            "id","title","description","state","workType","maxPoints","dueDate","dueTime",
            "topicId","alternateLink","creationTime","updateTime","scheduledTime","assigneeMode",
            "individualStudentsOptions","materials","submissionModificationMode","gradingPeriodId"
        )}

    def list_coursework_materials(self, course_id: str, include_drafts: bool = True) -> list[dict[str, Any]]:
        params: dict[str, Any] = {"pageSize": 100, "orderBy": "updateTime desc"}
        if include_drafts:
            params["courseWorkMaterialStates"] = ["PUBLISHED", "DRAFT"]
        return self._paginate(f"courses/{course_id}/courseWorkMaterials", "courseWorkMaterial", params=params)

    def list_submissions(self, course_id: str, course_work_id: str) -> list[dict[str, Any]]:
        submissions = self._paginate(
            f"courses/{course_id}/courseWork/{course_work_id}/studentSubmissions",
            "studentSubmissions", params={"pageSize": 100},
        )
        return [self._compact_submission(s) for s in submissions]

    def get_submission(self, course_id: str, course_work_id: str, submission_id: str) -> dict[str, Any]:
        return self._request("GET", f"courses/{course_id}/courseWork/{course_work_id}/studentSubmissions/{submission_id}")

    @staticmethod
    def _compact_submission(s: dict[str, Any]) -> dict[str, Any]:
        return {k: s.get(k) for k in (
            "id","userId","courseWorkId","state","late","draftGrade","assignedGrade","updateTime",
            "creationTime","alternateLink","assignmentSubmission","shortAnswerSubmission","multipleChoiceSubmission",
            "submissionHistory","associatedWithDeveloper"
        )}

    def create_coursework(self, course_id: str, *, title: str, description: str = "",
                          max_points: float | None = None, due_date: date | None = None,
                          due_time: time | None = None, topic_id: str | None = None,
                          publish: bool = False) -> dict[str, Any]:
        payload: dict[str, Any] = {
            "title": title, "description": description, "workType": "ASSIGNMENT",
            "state": "PUBLISHED" if publish else "DRAFT",
        }
        if max_points is not None: payload["maxPoints"] = max_points
        if due_date is not None:
            payload["dueDate"] = {"year": due_date.year, "month": due_date.month, "day": due_date.day}
        if due_time is not None:
            payload["dueTime"] = {"hours": due_time.hour, "minutes": due_time.minute}
        if topic_id: payload["topicId"] = topic_id
        return self._request("POST", f"courses/{course_id}/courseWork", json=payload)

    def patch_coursework(self, course_id: str, course_work_id: str, updates: dict[str, Any]) -> dict[str, Any]:
        allowed = {"title","description","state","dueDate","dueTime","maxPoints","topicId","scheduledTime"}
        payload = {k: v for k, v in updates.items() if k in allowed}
        if not payload:
            raise ClassroomError("No hay campos válidos para actualizar.")
        mask = ",".join(payload.keys())
        return self._request("PATCH", f"courses/{course_id}/courseWork/{course_work_id}", params={"updateMask": mask}, json=payload)

    def delete_coursework(self, course_id: str, course_work_id: str) -> dict[str, Any]:
        return self._request("DELETE", f"courses/{course_id}/courseWork/{course_work_id}")

    def grade_submission(self, course_id: str, course_work_id: str, submission_id: str,
                         *, grade: float, return_to_student: bool = False) -> dict[str, Any]:
        updated = self._request(
            "PATCH", f"courses/{course_id}/courseWork/{course_work_id}/studentSubmissions/{submission_id}",
            params={"updateMask": "draftGrade,assignedGrade"},
            json={"draftGrade": grade, "assignedGrade": grade},
        )
        if return_to_student:
            self._request("POST", f"courses/{course_id}/courseWork/{course_work_id}/studentSubmissions/{submission_id}:return", json={})
        return updated

    def batch_grade(self, course_id: str, course_work_id: str, grades: list[dict[str, Any]],
                    return_to_student: bool = False) -> dict[str, Any]:
        subs = self.list_submissions(course_id, course_work_id)
        by_id = {str(s.get("id")): s for s in subs}
        by_user = {str(s.get("userId")): s for s in subs}
        results, errors = [], []
        for row in grades:
            sid = str(row.get("submission_id") or "")
            uid = str(row.get("user_id") or "")
            sub = by_id.get(sid) if sid else by_user.get(uid)
            if not sub:
                errors.append({"input": row, "error": "No se encontró la entrega."})
                continue
            try:
                updated = self.grade_submission(course_id, course_work_id, str(sub["id"]), grade=float(row["grade"]), return_to_student=return_to_student)
                results.append({"submission_id": sub["id"], "userId": sub.get("userId"), "grade": row["grade"], "result": updated})
            except Exception as exc:
                errors.append({"input": row, "error": str(exc)})
        return {"updated": results, "errors": errors, "count_updated": len(results), "count_errors": len(errors)}

    def missing_students(self, course_id: str, course_work_id: str) -> list[dict[str, Any]]:
        students = {s["userId"]: s for s in self.list_students(course_id)}
        submissions = self.list_submissions(course_id, course_work_id)
        completed_states = {"TURNED_IN", "RETURNED"}
        missing: list[dict[str, Any]] = []
        for sub in submissions:
            if sub.get("state") not in completed_states:
                student = students.get(sub.get("userId"), {})
                missing.append({**student, "submission": sub})
        return missing

    def course_progress(self, course_id: str, include_drafts: bool = False) -> dict[str, Any]:
        students = self.list_students(course_id)
        work = self.list_coursework(course_id, include_drafts=include_drafts)
        if not include_drafts:
            work = [w for w in work if w.get("state") == "PUBLISHED"]
        by_student: dict[str, dict[str, Any]] = {
            str(s["userId"]): {**s, "turned_in": 0, "returned": 0, "missing": 0, "late": 0, "graded": 0, "items": []}
            for s in students
        }
        for w in work:
            for sub in self.list_submissions(course_id, str(w["id"])):
                uid = str(sub.get("userId"))
                row = by_student.get(uid)
                if not row: continue
                state = sub.get("state")
                if state == "TURNED_IN": row["turned_in"] += 1
                elif state == "RETURNED": row["returned"] += 1
                else: row["missing"] += 1
                if sub.get("late"): row["late"] += 1
                if sub.get("assignedGrade") is not None: row["graded"] += 1
                row["items"].append({"courseWorkId": w.get("id"), "title": w.get("title"), "state": state, "late": sub.get("late"), "assignedGrade": sub.get("assignedGrade"), "maxPoints": w.get("maxPoints")})
        return {"course": self.get_course(course_id), "coursework_count": len(work), "students": list(by_student.values())}
