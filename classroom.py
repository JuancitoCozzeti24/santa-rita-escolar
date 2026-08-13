from __future__ import annotations

from datetime import date, time
from typing import Any
import re

import requests

from config import settings


class ClassroomError(RuntimeError):
    pass


class ClassroomClient:
    API = "https://classroom.googleapis.com/v1"
    TOKEN_URL = "https://oauth2.googleapis.com/token"
    TOKENINFO_URL = "https://oauth2.googleapis.com/tokeninfo"

    # Conjunto suficiente para el control docente estable implementado en v0.5.0.
    FULL_WRITE_SCOPES = [
        "https://www.googleapis.com/auth/classroom.courses",
        "https://www.googleapis.com/auth/classroom.rosters",
        "https://www.googleapis.com/auth/classroom.profile.emails",
        "https://www.googleapis.com/auth/classroom.profile.photos",
        "https://www.googleapis.com/auth/classroom.topics",
        "https://www.googleapis.com/auth/classroom.announcements",
        "https://www.googleapis.com/auth/classroom.coursework.students",
        "https://www.googleapis.com/auth/classroom.courseworkmaterials",
        "https://www.googleapis.com/auth/classroom.guardianlinks.students",
    ]

    COURSEWORK_PATCHABLE = {
        "title", "description", "state", "dueDate", "dueTime", "maxPoints",
        "scheduledTime", "submissionModificationMode", "topicId", "gradingPeriodId",
    }
    COURSEWORK_CLEARABLE = {
        "description", "dueDate", "dueTime", "maxPoints", "scheduledTime", "topicId", "gradingPeriodId"
    }

    def __init__(self) -> None:
        self._access_token: str | None = None

    # ---------- OAuth / HTTP ----------
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

    def oauth_scope_status(self) -> dict[str, Any]:
        token = self._access_token or self._refresh_access_token()
        response = requests.get(self.TOKENINFO_URL, params={"access_token": token}, timeout=30)
        if not response.ok:
            raise ClassroomError(f"Google tokeninfo falló ({response.status_code}): {response.text[:500]}")
        data = response.json()
        granted = set(str(data.get("scope") or "").split())
        required = list(self.FULL_WRITE_SCOPES)
        return {
            "email": data.get("email"),
            "audience": data.get("aud") or data.get("issued_to"),
            "expires_in": data.get("expires_in"),
            "granted_scopes": sorted(granted),
            "required_full_write_scopes": required,
            "missing_full_write_scopes": [scope for scope in required if scope not in granted],
            "full_write_ready": all(scope in granted for scope in required),
            "note": (
                "Crear una rúbrica desde una Google Sheet requiere además spreadsheets.readonly o spreadsheets; "
                "v0.5.0 crea rúbricas desde criterios JSON y no exige ese scope adicional."
            ),
        }

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
        response = requests.request(method, url, headers=headers, params=params, json=json, timeout=30)
        if response.status_code == 401:
            headers["Authorization"] = f"Bearer {self._refresh_access_token()}"
            response = requests.request(method, url, headers=headers, params=params, json=json, timeout=30)
        if not response.ok:
            raise ClassroomError(
                f"Classroom API {method} {path} falló ({response.status_code}): {response.text[:1600]}"
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
    def _preview_params(preview_version: str | None) -> dict[str, Any] | None:
        return {"previewVersion": preview_version} if preview_version else None

    # ---------- Helpers ----------
    @staticmethod
    def _extract_drive_id(value: str) -> str:
        value = str(value or "").strip()
        if not value:
            raise ClassroomError("Falta el ID o URL del archivo de Drive.")
        for pattern in (r"/d/([A-Za-z0-9_-]+)", r"[?&]id=([A-Za-z0-9_-]+)"):
            m = re.search(pattern, value)
            if m:
                return m.group(1)
        if re.fullmatch(r"[A-Za-z0-9_-]{10,}", value):
            return value
        raise ClassroomError(f"No pude extraer un ID válido de Drive desde: {value[:120]}")

    @classmethod
    def normalize_materials(
        cls, materials: list[dict[str, Any]] | None, *, assignment: bool = False
    ) -> list[dict[str, Any]]:
        """Convierte especificaciones simples en objetos Material de Classroom."""
        out: list[dict[str, Any]] = []
        for raw in materials or []:
            if not isinstance(raw, dict):
                raise ClassroomError("Cada material debe ser un objeto JSON.")
            kind = str(raw.get("type") or raw.get("kind") or "").strip().lower()
            if kind == "drive":
                drive_id = cls._extract_drive_id(
                    str(raw.get("id") or raw.get("url") or raw.get("drive_file_id") or "")
                )
                share_mode = str(raw.get("share_mode") or "VIEW").upper()
                allowed = {"VIEW"} if not assignment else {"VIEW", "EDIT", "STUDENT_COPY"}
                if share_mode not in allowed:
                    raise ClassroomError(
                        f"share_mode={share_mode} no es válido aquí. Permitidos: {sorted(allowed)}"
                    )
                out.append({"driveFile": {"driveFile": {"id": drive_id}, "shareMode": share_mode}})
            elif kind in {"link", "url", "youtube", "form"}:
                url = str(raw.get("url") or raw.get("link") or "").strip()
                if not (url.startswith("https://") or url.startswith("http://")):
                    raise ClassroomError("El material tipo link necesita una URL http(s) válida.")
                out.append({"link": {"url": url}})
            else:
                raise ClassroomError(f"Tipo de material no admitido: {kind!r}. Usa drive o link.")
        if len(out) > 20:
            raise ClassroomError("Classroom permite como máximo 20 materiales adjuntos por publicación.")
        return out

    @staticmethod
    def _apply_assignees(payload: dict[str, Any], student_ids: list[str] | None) -> None:
        ids = [str(x).strip() for x in (student_ids or []) if str(x).strip()]
        if ids:
            payload["assigneeMode"] = "INDIVIDUAL_STUDENTS"
            payload["individualStudentsOptions"] = {"studentIds": ids}
        else:
            payload["assigneeMode"] = "ALL_STUDENTS"

    @staticmethod
    def _profile(person: dict[str, Any]) -> dict[str, Any]:
        p = person.get("profile") or {}
        return {
            "courseId": person.get("courseId"),
            "userId": person.get("userId"),
            "name": (p.get("name") or {}).get("fullName"),
            "email": p.get("emailAddress"),
            "photoUrl": p.get("photoUrl"),
            "verifiedTeacher": p.get("verifiedTeacher"),
        }

    @staticmethod
    def _date_obj(value: date | None) -> dict[str, int] | None:
        if value is None:
            return None
        return {"year": value.year, "month": value.month, "day": value.day}

    @staticmethod
    def _time_obj(value: time | None) -> dict[str, int] | None:
        if value is None:
            return None
        return {"hours": value.hour, "minutes": value.minute, "seconds": value.second}

    # ---------- Courses ----------
    def list_courses(self, active_only: bool = True) -> list[dict[str, Any]]:
        params: dict[str, Any] = {"teacherId": "me", "pageSize": 100}
        if active_only:
            params["courseStates"] = "ACTIVE"
        courses = self._paginate("courses", "courses", params=params)
        return [
            {k: c.get(k) for k in (
                "id", "name", "section", "descriptionHeading", "description", "room", "ownerId",
                "courseState", "alternateLink", "calendarId", "teacherGroupEmail", "courseGroupEmail",
                "enrollmentCode", "guardiansEnabled", "gradebookSettings", "subject", "levels"
            )}
            for c in courses
        ]

    def get_course(self, course_id: str) -> dict[str, Any]:
        return self._request("GET", f"courses/{course_id}")

    def create_course(
        self,
        *,
        name: str,
        owner_id: str = "me",
        section: str = "",
        description_heading: str = "",
        description: str = "",
        room: str = "",
        subject: str = "",
        course_state: str | None = None,
    ) -> dict[str, Any]:
        payload: dict[str, Any] = {"name": name, "ownerId": owner_id}
        if section:
            payload["section"] = section
        if description_heading:
            payload["descriptionHeading"] = description_heading
        if description:
            payload["description"] = description
        if room:
            payload["room"] = room
        if subject:
            payload["subject"] = subject
        if course_state:
            payload["courseState"] = course_state
        return self._request("POST", "courses", json=payload)

    def update_course(self, course_id: str, updates: dict[str, Any], clear_fields: list[str] | None = None) -> dict[str, Any]:
        allowed = {"courseState", "description", "descriptionHeading", "name", "room", "section", "subject", "levels"}
        clearable = {"description", "descriptionHeading", "room", "section", "subject", "levels"}
        payload = {k: v for k, v in updates.items() if k in allowed}
        clear = [f for f in (clear_fields or []) if f in clearable]
        mask = list(dict.fromkeys([*payload.keys(), *clear]))
        if not mask:
            raise ClassroomError("No hay campos válidos para actualizar el curso.")
        return self._request("PATCH", f"courses/{course_id}", params={"updateMask": ",".join(mask)}, json=payload)

    def delete_course(self, course_id: str) -> dict[str, Any]:
        return self._request("DELETE", f"courses/{course_id}")

    def list_aliases(self, course_id: str) -> list[dict[str, Any]]:
        return self._paginate(f"courses/{course_id}/aliases", "aliases", params={"pageSize": 100})

    def create_alias(self, course_id: str, alias: str) -> dict[str, Any]:
        return self._request("POST", f"courses/{course_id}/aliases", json={"alias": alias})

    def delete_alias(self, course_id: str, alias: str) -> dict[str, Any]:
        return self._request("DELETE", f"courses/{course_id}/aliases/{alias}")

    def get_grading_period_settings(self, course_id: str) -> dict[str, Any]:
        return self._request("GET", f"courses/{course_id}/gradingPeriodSettings")

    def update_grading_period_settings(
        self, course_id: str, settings_payload: dict[str, Any], update_mask: str = "gradingPeriods,applyToExistingCoursework"
    ) -> dict[str, Any]:
        allowed_mask = {"gradingPeriods", "applyToExistingCoursework"}
        fields = [x.strip() for x in update_mask.split(",") if x.strip()]
        if not fields or any(x not in allowed_mask for x in fields):
            raise ClassroomError("update_mask de períodos inválido.")
        return self._request(
            "PATCH", f"courses/{course_id}/gradingPeriodSettings",
            params={"updateMask": ",".join(fields)}, json=settings_payload,
        )

    # ---------- Roster / invitations ----------
    def list_students(self, course_id: str) -> list[dict[str, Any]]:
        students = self._paginate(f"courses/{course_id}/students", "students", params={"pageSize": 100})
        return [self._profile(s) for s in students]

    def get_student(self, course_id: str, user_id: str) -> dict[str, Any]:
        return self._request("GET", f"courses/{course_id}/students/{user_id}")

    def list_teachers(self, course_id: str) -> list[dict[str, Any]]:
        teachers = self._paginate(f"courses/{course_id}/teachers", "teachers", params={"pageSize": 100})
        return [self._profile(t) for t in teachers]

    def get_teacher(self, course_id: str, user_id: str) -> dict[str, Any]:
        return self._request("GET", f"courses/{course_id}/teachers/{user_id}")

    def add_student(self, course_id: str, user_id: str, enrollment_code: str | None = None) -> dict[str, Any]:
        params = {"enrollmentCode": enrollment_code} if enrollment_code else None
        return self._request("POST", f"courses/{course_id}/students", params=params, json={"userId": user_id})

    def remove_student(self, course_id: str, user_id: str) -> dict[str, Any]:
        return self._request("DELETE", f"courses/{course_id}/students/{user_id}")

    def add_teacher(self, course_id: str, user_id: str) -> dict[str, Any]:
        return self._request("POST", f"courses/{course_id}/teachers", json={"userId": user_id})

    def remove_teacher(self, course_id: str, user_id: str) -> dict[str, Any]:
        return self._request("DELETE", f"courses/{course_id}/teachers/{user_id}")

    def get_invitation(self, invitation_id: str) -> dict[str, Any]:
        return self._request("GET", f"invitations/{invitation_id}")

    def list_invitations(self, *, course_id: str | None = None, user_id: str | None = None) -> list[dict[str, Any]]:
        if not course_id and not user_id:
            raise ClassroomError("Invitations.list exige course_id o user_id.")
        params: dict[str, Any] = {"pageSize": 100}
        if course_id:
            params["courseId"] = course_id
        if user_id:
            params["userId"] = user_id
        return self._paginate("invitations", "invitations", params=params)

    def create_invitation(self, course_id: str, user_id: str, role: str) -> dict[str, Any]:
        role = role.upper()
        if role not in {"STUDENT", "TEACHER", "OWNER"}:
            raise ClassroomError("role debe ser STUDENT, TEACHER u OWNER.")
        return self._request("POST", "invitations", json={"courseId": course_id, "userId": user_id, "role": role})

    def delete_invitation(self, invitation_id: str) -> dict[str, Any]:
        return self._request("DELETE", f"invitations/{invitation_id}")

    def accept_invitation(self, invitation_id: str) -> dict[str, Any]:
        return self._request("POST", f"invitations/{invitation_id}:accept", json={})


    # ---------- User profiles / guardians ----------
    def get_user_profile(self, user_id: str = "me") -> dict[str, Any]:
        return self._request("GET", f"userProfiles/{user_id}")

    def check_user_capability(
        self, capability: str, *, user_id: str = "me", preview_version: str = "V1_20240930_PREVIEW"
    ) -> dict[str, Any]:
        params: dict[str, Any] = {"capability": capability}
        if preview_version:
            params["previewVersion"] = preview_version
        return self._request("GET", f"userProfiles/{user_id}:checkUserCapability", params=params)

    def list_guardians(
        self, student_id: str, *, invited_email_address: str | None = None
    ) -> list[dict[str, Any]]:
        params: dict[str, Any] = {"pageSize": 100}
        if invited_email_address:
            params["invitedEmailAddress"] = invited_email_address
        return self._paginate(f"userProfiles/{student_id}/guardians", "guardians", params=params)

    def get_guardian(self, student_id: str, guardian_id: str) -> dict[str, Any]:
        return self._request("GET", f"userProfiles/{student_id}/guardians/{guardian_id}")

    def delete_guardian(self, student_id: str, guardian_id: str) -> dict[str, Any]:
        return self._request("DELETE", f"userProfiles/{student_id}/guardians/{guardian_id}")

    def list_guardian_invitations(
        self, student_id: str, *, invited_email_address: str | None = None, states: list[str] | None = None
    ) -> list[dict[str, Any]]:
        params: dict[str, Any] = {"pageSize": 100}
        if invited_email_address:
            params["invitedEmailAddress"] = invited_email_address
        if states:
            params["states"] = [str(x).upper() for x in states]
        return self._paginate(f"userProfiles/{student_id}/guardianInvitations", "guardianInvitations", params=params)

    def get_guardian_invitation(self, student_id: str, invitation_id: str) -> dict[str, Any]:
        return self._request("GET", f"userProfiles/{student_id}/guardianInvitations/{invitation_id}")

    def create_guardian_invitation(self, student_id: str, invited_email_address: str) -> dict[str, Any]:
        return self._request(
            "POST", f"userProfiles/{student_id}/guardianInvitations",
            json={"studentId": student_id, "invitedEmailAddress": invited_email_address},
        )

    def cancel_guardian_invitation(self, student_id: str, invitation_id: str) -> dict[str, Any]:
        return self._request(
            "PATCH", f"userProfiles/{student_id}/guardianInvitations/{invitation_id}",
            params={"updateMask": "state"}, json={"state": "COMPLETE"},
        )

    # ---------- Topics ----------
    def get_topic(self, course_id: str, topic_id: str) -> dict[str, Any]:
        return self._request("GET", f"courses/{course_id}/topics/{topic_id}")

    def list_topics(self, course_id: str) -> list[dict[str, Any]]:
        topics = self._paginate(f"courses/{course_id}/topics", "topic", params={"pageSize": 100})
        return [{"topicId": t.get("topicId"), "name": t.get("name"), "updateTime": t.get("updateTime")} for t in topics]

    def create_topic(self, course_id: str, name: str) -> dict[str, Any]:
        return self._request("POST", f"courses/{course_id}/topics", json={"name": name})

    def update_topic(self, course_id: str, topic_id: str, name: str) -> dict[str, Any]:
        return self._request("PATCH", f"courses/{course_id}/topics/{topic_id}", params={"updateMask": "name"}, json={"name": name})

    def delete_topic(self, course_id: str, topic_id: str) -> dict[str, Any]:
        return self._request("DELETE", f"courses/{course_id}/topics/{topic_id}")

    # ---------- Announcements ----------
    def list_announcements(self, course_id: str, include_drafts: bool = True) -> list[dict[str, Any]]:
        params: dict[str, Any] = {"pageSize": 100, "orderBy": "updateTime desc"}
        if include_drafts:
            params["announcementStates"] = ["PUBLISHED", "DRAFT"]
        items = self._paginate(f"courses/{course_id}/announcements", "announcements", params=params)
        return [{k: a.get(k) for k in (
            "id", "text", "state", "alternateLink", "creationTime", "updateTime", "scheduledTime",
            "assigneeMode", "individualStudentsOptions", "materials", "creatorUserId"
        )} for a in items]

    def get_announcement(self, course_id: str, announcement_id: str) -> dict[str, Any]:
        return self._request("GET", f"courses/{course_id}/announcements/{announcement_id}")

    def create_announcement(
        self, course_id: str, *, text: str, publish: bool = False,
        materials: list[dict[str, Any]] | None = None,
        scheduled_time: str | None = None, student_ids: list[str] | None = None,
    ) -> dict[str, Any]:
        state = "DRAFT" if scheduled_time else ("PUBLISHED" if publish else "DRAFT")
        payload: dict[str, Any] = {"text": text, "state": state}
        norm = self.normalize_materials(materials, assignment=False)
        if norm:
            payload["materials"] = norm
        if scheduled_time:
            payload["scheduledTime"] = scheduled_time
        self._apply_assignees(payload, student_ids)
        return self._request("POST", f"courses/{course_id}/announcements", json=payload)

    def patch_announcement(
        self, course_id: str, announcement_id: str, updates: dict[str, Any], clear_fields: list[str] | None = None
    ) -> dict[str, Any]:
        allowed = {"text", "state", "scheduledTime"}
        clearable = {"scheduledTime"}
        payload = {k: v for k, v in updates.items() if k in allowed}
        clear = [f for f in (clear_fields or []) if f in clearable]
        mask = list(dict.fromkeys([*payload.keys(), *clear]))
        if not mask:
            raise ClassroomError("No hay campos válidos para actualizar el anuncio.")
        return self._request(
            "PATCH", f"courses/{course_id}/announcements/{announcement_id}",
            params={"updateMask": ",".join(mask)}, json=payload,
        )

    def modify_announcement_assignees(
        self, course_id: str, announcement_id: str, *, assignee_mode: str,
        add_student_ids: list[str] | None = None, remove_student_ids: list[str] | None = None,
    ) -> dict[str, Any]:
        mode = assignee_mode.upper()
        if mode not in {"ALL_STUDENTS", "INDIVIDUAL_STUDENTS"}:
            raise ClassroomError("assignee_mode inválido.")
        body: dict[str, Any] = {"assigneeMode": mode}
        if mode == "INDIVIDUAL_STUDENTS":
            body["modifyIndividualStudentsOptions"] = {
                "addStudentIds": [str(x) for x in (add_student_ids or []) if str(x)],
                "removeStudentIds": [str(x) for x in (remove_student_ids or []) if str(x)],
            }
        return self._request("POST", f"courses/{course_id}/announcements/{announcement_id}:modifyAssignees", json=body)

    def delete_announcement(self, course_id: str, announcement_id: str) -> dict[str, Any]:
        return self._request("DELETE", f"courses/{course_id}/announcements/{announcement_id}")

    # ---------- CourseWork / assignments / questions ----------
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
            "id", "title", "description", "state", "workType", "maxPoints", "dueDate", "dueTime",
            "topicId", "alternateLink", "creationTime", "updateTime", "scheduledTime", "assigneeMode",
            "individualStudentsOptions", "materials", "submissionModificationMode", "gradingPeriodId",
            "gradeCategory", "associatedWithDeveloper", "creatorUserId", "multipleChoiceQuestion", "assignment"
        )}

    def create_coursework_item(
        self,
        course_id: str,
        *,
        title: str,
        description: str = "",
        work_type: str = "ASSIGNMENT",
        max_points: float | None = None,
        due_date: date | None = None,
        due_time: time | None = None,
        topic_id: str | None = None,
        publish: bool = False,
        materials: list[dict[str, Any]] | None = None,
        scheduled_time: str | None = None,
        student_ids: list[str] | None = None,
        multiple_choice_choices: list[str] | None = None,
        submission_modification_mode: str | None = None,
        grading_period_id: str | None = None,
    ) -> dict[str, Any]:
        work_type = work_type.upper()
        if work_type not in {"ASSIGNMENT", "SHORT_ANSWER_QUESTION", "MULTIPLE_CHOICE_QUESTION"}:
            raise ClassroomError("work_type debe ser ASSIGNMENT, SHORT_ANSWER_QUESTION o MULTIPLE_CHOICE_QUESTION.")
        if max_points is not None and (max_points < 0 or float(max_points).is_integer() is False):
            raise ClassroomError("max_points debe ser un entero no negativo según Classroom.")
        if due_time is not None and due_date is None:
            raise ClassroomError("due_time requiere due_date.")
        state = "DRAFT" if scheduled_time else ("PUBLISHED" if publish else "DRAFT")
        payload: dict[str, Any] = {
            "title": title,
            "description": description,
            "workType": work_type,
            "state": state,
        }
        if max_points is not None:
            payload["maxPoints"] = int(max_points)
        if due_date is not None:
            payload["dueDate"] = self._date_obj(due_date)
        if due_time is not None:
            payload["dueTime"] = self._time_obj(due_time)
        if topic_id:
            payload["topicId"] = topic_id
        norm = self.normalize_materials(materials, assignment=(work_type == "ASSIGNMENT"))
        if norm:
            payload["materials"] = norm
        if scheduled_time:
            payload["scheduledTime"] = scheduled_time
        if submission_modification_mode:
            mode = submission_modification_mode.upper()
            if mode not in {"MODIFIABLE_UNTIL_TURNED_IN", "MODIFIABLE"}:
                raise ClassroomError("submission_modification_mode inválido.")
            payload["submissionModificationMode"] = mode
        if grading_period_id is not None:
            payload["gradingPeriodId"] = grading_period_id
        if work_type == "MULTIPLE_CHOICE_QUESTION":
            choices = [str(x).strip() for x in (multiple_choice_choices or []) if str(x).strip()]
            if len(choices) < 2:
                raise ClassroomError("Una pregunta de opción múltiple necesita al menos dos opciones.")
            payload["multipleChoiceQuestion"] = {"choices": choices}
        self._apply_assignees(payload, student_ids)
        return self._request("POST", f"courses/{course_id}/courseWork", json=payload)

    def create_coursework(self, course_id: str, **kwargs: Any) -> dict[str, Any]:
        kwargs["work_type"] = "ASSIGNMENT"
        return self.create_coursework_item(course_id, **kwargs)

    def patch_coursework(
        self, course_id: str, course_work_id: str, updates: dict[str, Any], clear_fields: list[str] | None = None
    ) -> dict[str, Any]:
        payload = {k: v for k, v in updates.items() if k in self.COURSEWORK_PATCHABLE}
        clear = [f for f in (clear_fields or []) if f in self.COURSEWORK_CLEARABLE]
        mask = list(dict.fromkeys([*payload.keys(), *clear]))
        if not mask:
            raise ClassroomError("No hay campos válidos para actualizar el trabajo.")
        return self._request(
            "PATCH", f"courses/{course_id}/courseWork/{course_work_id}",
            params={"updateMask": ",".join(mask)}, json=payload,
        )

    def modify_coursework_assignees(
        self, course_id: str, course_work_id: str, *, assignee_mode: str,
        add_student_ids: list[str] | None = None, remove_student_ids: list[str] | None = None,
    ) -> dict[str, Any]:
        mode = assignee_mode.upper()
        if mode not in {"ALL_STUDENTS", "INDIVIDUAL_STUDENTS"}:
            raise ClassroomError("assignee_mode inválido.")
        body: dict[str, Any] = {"assigneeMode": mode}
        if mode == "INDIVIDUAL_STUDENTS":
            body["modifyIndividualStudentsOptions"] = {
                "addStudentIds": [str(x) for x in (add_student_ids or []) if str(x)],
                "removeStudentIds": [str(x) for x in (remove_student_ids or []) if str(x)],
            }
        return self._request("POST", f"courses/{course_id}/courseWork/{course_work_id}:modifyAssignees", json=body)

    def delete_coursework(self, course_id: str, course_work_id: str) -> dict[str, Any]:
        return self._request("DELETE", f"courses/{course_id}/courseWork/{course_work_id}")

    # ---------- CourseWorkMaterial ----------
    def list_coursework_materials(self, course_id: str, include_drafts: bool = True) -> list[dict[str, Any]]:
        params: dict[str, Any] = {"pageSize": 100, "orderBy": "updateTime desc"}
        if include_drafts:
            params["courseWorkMaterialStates"] = ["PUBLISHED", "DRAFT"]
        return self._paginate(f"courses/{course_id}/courseWorkMaterials", "courseWorkMaterial", params=params)

    def get_coursework_material(self, course_id: str, material_id: str) -> dict[str, Any]:
        return self._request("GET", f"courses/{course_id}/courseWorkMaterials/{material_id}")

    def create_coursework_material(
        self, course_id: str, *, title: str, description: str = "",
        materials: list[dict[str, Any]] | None = None, topic_id: str | None = None,
        publish: bool = False, scheduled_time: str | None = None,
        student_ids: list[str] | None = None,
    ) -> dict[str, Any]:
        state = "DRAFT" if scheduled_time else ("PUBLISHED" if publish else "DRAFT")
        payload: dict[str, Any] = {"title": title, "description": description, "state": state}
        norm = self.normalize_materials(materials, assignment=False)
        if norm:
            payload["materials"] = norm
        if topic_id:
            payload["topicId"] = topic_id
        if scheduled_time:
            payload["scheduledTime"] = scheduled_time
        self._apply_assignees(payload, student_ids)
        return self._request("POST", f"courses/{course_id}/courseWorkMaterials", json=payload)

    def patch_coursework_material(
        self, course_id: str, material_id: str, updates: dict[str, Any], clear_fields: list[str] | None = None
    ) -> dict[str, Any]:
        allowed = {"title", "description", "state", "scheduledTime", "topicId"}
        clearable = {"description", "scheduledTime", "topicId"}
        payload = {k: v for k, v in updates.items() if k in allowed}
        clear = [f for f in (clear_fields or []) if f in clearable]
        mask = list(dict.fromkeys([*payload.keys(), *clear]))
        if not mask:
            raise ClassroomError("No hay campos válidos para actualizar el material.")
        return self._request(
            "PATCH", f"courses/{course_id}/courseWorkMaterials/{material_id}",
            params={"updateMask": ",".join(mask)}, json=payload,
        )

    def delete_coursework_material(self, course_id: str, material_id: str) -> dict[str, Any]:
        return self._request("DELETE", f"courses/{course_id}/courseWorkMaterials/{material_id}")

    # ---------- Student submissions / grading ----------
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
            "id", "userId", "courseWorkId", "state", "late", "draftGrade", "assignedGrade",
            "draftRubricGrades", "assignedRubricGrades", "updateTime", "creationTime", "alternateLink",
            "assignmentSubmission", "shortAnswerSubmission", "multipleChoiceSubmission", "submissionHistory",
            "associatedWithDeveloper"
        )}

    def patch_submission_grades(
        self, course_id: str, course_work_id: str, submission_id: str,
        *, draft_grade: float | None = None, assigned_grade: float | None = None,
    ) -> dict[str, Any]:
        if draft_grade is None and assigned_grade is None:
            raise ClassroomError("Debes proporcionar draft_grade o assigned_grade.")
        payload: dict[str, Any] = {}
        mask: list[str] = []
        if assigned_grade is not None and draft_grade is None:
            # Emula la interfaz de Classroom y evita assignedGrade sin draftGrade.
            draft_grade = assigned_grade
        if draft_grade is not None:
            if draft_grade < 0:
                raise ClassroomError("draft_grade no puede ser negativo.")
            payload["draftGrade"] = float(draft_grade)
            mask.append("draftGrade")
        if assigned_grade is not None:
            if assigned_grade < 0:
                raise ClassroomError("assigned_grade no puede ser negativo.")
            payload["assignedGrade"] = float(assigned_grade)
            mask.append("assignedGrade")
        return self._request(
            "PATCH", f"courses/{course_id}/courseWork/{course_work_id}/studentSubmissions/{submission_id}",
            params={"updateMask": ",".join(mask)}, json=payload,
        )

    def grade_submission(
        self, course_id: str, course_work_id: str, submission_id: str,
        *, grade: float, return_to_student: bool = False,
    ) -> dict[str, Any]:
        updated = self.patch_submission_grades(
            course_id, course_work_id, submission_id, draft_grade=grade, assigned_grade=grade
        )
        returned = None
        if return_to_student:
            returned = self.return_submission(course_id, course_work_id, submission_id, finalize_draft=False)
        return {"submission": updated, "returned": returned}

    def clear_submission_grade(
        self, course_id: str, course_work_id: str, submission_id: str, *, which: str = "all"
    ) -> dict[str, Any]:
        """Intenta limpiar draftGrade/assignedGrade mediante FieldMask y cuerpo sin esos campos.

        Classroom documenta esos campos como actualizables, pero no documenta explícitamente un ejemplo de borrado.
        Si el backend no admite el vaciado, devuelve un resultado estructurado sin ocultar el error.
        """
        mode = which.lower().strip()
        if mode not in {"draft", "assigned", "all"}:
            raise ClassroomError("which debe ser draft, assigned o all.")
        fields = ["draftGrade", "assignedGrade"] if mode == "all" else (["draftGrade"] if mode == "draft" else ["assignedGrade"])
        try:
            result = self._request(
                "PATCH", f"courses/{course_id}/courseWork/{course_work_id}/studentSubmissions/{submission_id}",
                params={"updateMask": ",".join(fields)}, json={},
            )
            return {"cleared": True, "fields": fields, "submission": result}
        except ClassroomError as exc:
            return {
                "cleared": False,
                "fields": fields,
                "error": str(exc),
                "note": "Google no documenta un ejemplo oficial para borrar una nota ya establecida; no se hizo una sustitución destructiva alternativa.",
            }

    def return_submission(
        self, course_id: str, course_work_id: str, submission_id: str, *, finalize_draft: bool = True
    ) -> dict[str, Any]:
        before = self.get_submission(course_id, course_work_id, submission_id)
        finalized = None
        if finalize_draft and before.get("draftGrade") is not None:
            grade = float(before["draftGrade"])
            finalized = self.patch_submission_grades(
                course_id, course_work_id, submission_id, draft_grade=grade, assigned_grade=grade
            )
        returned = self._request(
            "POST", f"courses/{course_id}/courseWork/{course_work_id}/studentSubmissions/{submission_id}:return", json={}
        )
        after = self.get_submission(course_id, course_work_id, submission_id)
        return {"before": before, "finalized": finalized, "return_response": returned, "after": after}

    def batch_grade(
        self, course_id: str, course_work_id: str, grades: list[dict[str, Any]],
        *, mode: str = "final", return_to_student: bool = False,
    ) -> dict[str, Any]:
        mode = mode.lower().strip()
        if mode not in {"draft", "final"}:
            raise ClassroomError("mode debe ser draft o final.")
        subs = self.list_submissions(course_id, course_work_id)
        by_id = {str(s.get("id")): s for s in subs}
        by_user = {str(s.get("userId")): s for s in subs}
        results: list[dict[str, Any]] = []
        errors: list[dict[str, Any]] = []
        for row in grades:
            sid = str(row.get("submission_id") or "")
            uid = str(row.get("user_id") or "")
            sub = by_id.get(sid) if sid else by_user.get(uid)
            if not sub:
                errors.append({"input": row, "error": "No se encontró la entrega."})
                continue
            try:
                grade = float(row["grade"])
                if mode == "draft":
                    updated = self.patch_submission_grades(
                        course_id, course_work_id, str(sub["id"]), draft_grade=grade
                    )
                    returned = None
                else:
                    updated = self.patch_submission_grades(
                        course_id, course_work_id, str(sub["id"]), draft_grade=grade, assigned_grade=grade
                    )
                    returned = self.return_submission(
                        course_id, course_work_id, str(sub["id"]), finalize_draft=False
                    ) if return_to_student else None
                results.append({
                    "submission_id": sub["id"], "userId": sub.get("userId"), "grade": grade,
                    "mode": mode, "updated": updated, "returned": returned,
                })
            except Exception as exc:
                errors.append({"input": row, "error": str(exc)})
        return {"updated": results, "errors": errors, "count_updated": len(results), "count_errors": len(errors)}

    def batch_return(self, course_id: str, course_work_id: str, submission_ids: list[str], *, finalize_draft: bool = True) -> dict[str, Any]:
        results, errors = [], []
        for sid in submission_ids:
            try:
                results.append({"submission_id": sid, "result": self.return_submission(
                    course_id, course_work_id, sid, finalize_draft=finalize_draft
                )})
            except Exception as exc:
                errors.append({"submission_id": sid, "error": str(exc)})
        return {"returned": results, "errors": errors, "count_returned": len(results), "count_errors": len(errors)}

    def diagnose_coursework_control(self, course_id: str, course_work_id: str) -> dict[str, Any]:
        work = self.get_coursework(course_id, course_work_id)
        submissions = self.list_submissions(course_id, course_work_id)
        associated = bool(work.get("associatedWithDeveloper"))
        sample_assoc = sorted({str(s.get("associatedWithDeveloper")) for s in submissions[:10]})
        return {
            "courseWork": self._compact_coursework(work),
            "associatedWithDeveloper": associated,
            "submission_association_samples": sample_assoc,
            "likely_permissions": {
                "read": True,
                "edit_coursework": associated,
                "grade_student_submissions": associated,
                "return_student_submissions": associated,
            },
            "reason": (
                "Google exige que las modificaciones del CourseWork y de sus StudentSubmissions se hagan con el proyecto OAuth asociado a ese CourseWork."
                if not associated else
                "El CourseWork está asociado a este proyecto OAuth; aún pueden aplicar permisos del usuario/curso y otras precondiciones de Google."
            ),
            "submission_count": len(submissions),
        }

    # ---------- Rubrics ----------
    def list_rubrics(self, course_id: str, course_work_id: str, preview_version: str | None = None) -> list[dict[str, Any]]:
        params = {"pageSize": 100}
        if preview_version:
            params["previewVersion"] = preview_version
        return self._paginate(
            f"courses/{course_id}/courseWork/{course_work_id}/rubrics", "rubrics", params=params
        )

    def get_rubric(self, course_id: str, course_work_id: str, rubric_id: str, preview_version: str | None = None) -> dict[str, Any]:
        return self._request(
            "GET", f"courses/{course_id}/courseWork/{course_work_id}/rubrics/{rubric_id}",
            params=self._preview_params(preview_version),
        )

    def create_rubric(
        self, course_id: str, course_work_id: str, *, criteria: list[dict[str, Any]], preview_version: str | None = None
    ) -> dict[str, Any]:
        if not criteria:
            raise ClassroomError("La rúbrica necesita al menos un criterio.")
        return self._request(
            "POST", f"courses/{course_id}/courseWork/{course_work_id}/rubrics",
            params=self._preview_params(preview_version), json={"criteria": criteria},
        )

    def update_rubric(
        self, course_id: str, course_work_id: str, rubric_id: str, *, criteria: list[dict[str, Any]],
        preview_version: str | None = None,
    ) -> dict[str, Any]:
        params: dict[str, Any] = {"updateMask": "criteria"}
        if preview_version:
            params["previewVersion"] = preview_version
        return self._request(
            "PATCH", f"courses/{course_id}/courseWork/{course_work_id}/rubrics/{rubric_id}",
            params=params, json={"criteria": criteria},
        )

    def delete_rubric(self, course_id: str, course_work_id: str, rubric_id: str, preview_version: str | None = None) -> dict[str, Any]:
        return self._request(
            "DELETE", f"courses/{course_id}/courseWork/{course_work_id}/rubrics/{rubric_id}",
            params=self._preview_params(preview_version),
        )

    # ---------- Student groups ----------
    def list_student_groups(self, course_id: str, preview_version: str | None = None) -> list[dict[str, Any]]:
        params: dict[str, Any] = {"pageSize": 75}
        if preview_version:
            params["previewVersion"] = preview_version
        return self._paginate(f"courses/{course_id}/studentGroups", "studentGroups", params=params)

    def create_student_group(self, course_id: str, title: str, preview_version: str | None = None) -> dict[str, Any]:
        return self._request(
            "POST", f"courses/{course_id}/studentGroups", params=self._preview_params(preview_version), json={"title": title}
        )

    def update_student_group(self, course_id: str, group_id: str, title: str, preview_version: str | None = None) -> dict[str, Any]:
        params: dict[str, Any] = {"updateMask": "title"}
        if preview_version:
            params["previewVersion"] = preview_version
        return self._request(
            "PATCH", f"courses/{course_id}/studentGroups/{group_id}", params=params, json={"title": title}
        )

    def delete_student_group(self, course_id: str, group_id: str, preview_version: str | None = None) -> dict[str, Any]:
        return self._request(
            "DELETE", f"courses/{course_id}/studentGroups/{group_id}", params=self._preview_params(preview_version)
        )

    def list_student_group_members(self, course_id: str, group_id: str, preview_version: str | None = None) -> list[dict[str, Any]]:
        params: dict[str, Any] = {"pageSize": 100}
        if preview_version:
            params["previewVersion"] = preview_version
        return self._paginate(
            f"courses/{course_id}/studentGroups/{group_id}/studentGroupMembers", "studentGroupMembers", params=params
        )

    def add_student_group_member(self, course_id: str, group_id: str, user_id: str, preview_version: str | None = None) -> dict[str, Any]:
        return self._request(
            "POST", f"courses/{course_id}/studentGroups/{group_id}/studentGroupMembers",
            params=self._preview_params(preview_version), json={"userId": user_id},
        )

    def remove_student_group_member(self, course_id: str, group_id: str, user_id: str, preview_version: str | None = None) -> dict[str, Any]:
        return self._request(
            "DELETE", f"courses/{course_id}/studentGroups/{group_id}/studentGroupMembers/{user_id}",
            params=self._preview_params(preview_version),
        )

    # ---------- Progress / helpers ----------
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
            str(s["userId"]): {
                **s, "turned_in": 0, "returned": 0, "missing": 0, "late": 0, "graded": 0,
                "draft_graded": 0, "items": []
            }
            for s in students
        }
        for w in work:
            for sub in self.list_submissions(course_id, str(w["id"])):
                uid = str(sub.get("userId"))
                row = by_student.get(uid)
                if not row:
                    continue
                state = sub.get("state")
                if state == "TURNED_IN":
                    row["turned_in"] += 1
                elif state == "RETURNED":
                    row["returned"] += 1
                else:
                    row["missing"] += 1
                if sub.get("late"):
                    row["late"] += 1
                if sub.get("assignedGrade") is not None:
                    row["graded"] += 1
                if sub.get("draftGrade") is not None:
                    row["draft_graded"] += 1
                row["items"].append({
                    "courseWorkId": w.get("id"), "title": w.get("title"), "state": state,
                    "late": sub.get("late"), "draftGrade": sub.get("draftGrade"),
                    "assignedGrade": sub.get("assignedGrade"), "maxPoints": w.get("maxPoints"),
                    "gradingPeriodId": w.get("gradingPeriodId"),
                })
        return {"course": self.get_course(course_id), "coursework_count": len(work), "students": list(by_student.values())}
