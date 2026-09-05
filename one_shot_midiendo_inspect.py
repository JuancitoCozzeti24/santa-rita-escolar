from __future__ import annotations

import json
import unicodedata
from typing import Any

TARGET_ASSIGNMENT = "C1: FICHA DE MIDIENDO NUESTRO AVANCE"


def _norm(value: Any) -> str:
    text = unicodedata.normalize("NFD", str(value or ""))
    text = "".join(ch for ch in text if unicodedata.category(ch) != "Mn")
    return " ".join(text.upper().split())


def inspect(classroom: Any) -> dict[str, Any]:
    target_norm = _norm(TARGET_ASSIGNMENT)
    payload: dict[str, Any] = {"course": None, "coursework": None, "rows": []}

    for course in classroom.list_courses(active_only=True):
        course_id = str(course.get("id") or "")
        hay = _norm(f"{course.get('name') or ''} {course.get('section') or ''}")
        if not course_id or "MATE 5TO" not in hay or ("5TO - B" not in hay and "5TO B" not in hay):
            continue

        works = classroom.list_coursework(course_id, include_drafts=True)
        matches = [w for w in works if _norm(w.get("title")) == target_norm]
        if len(matches) != 1:
            print(
                "MIDIENDO_INSPECT_MATCH_ERROR=" + json.dumps({
                    "course_id": course_id,
                    "course_name": course.get("name"),
                    "matches": [{"id": w.get("id"), "title": w.get("title")} for w in matches],
                }, ensure_ascii=False),
                flush=True,
            )
            continue

        work = matches[0]
        work_id = str(work.get("id") or "")
        payload["course"] = {
            "id": course_id,
            "name": course.get("name"),
            "section": course.get("section"),
            "alternateLink": course.get("alternateLink"),
        }
        payload["coursework"] = {
            "id": work_id,
            "title": work.get("title"),
            "description": work.get("description"),
            "maxPoints": work.get("maxPoints"),
            "state": work.get("state"),
            "alternateLink": work.get("alternateLink"),
            "materials": work.get("materials"),
            "dueDate": work.get("dueDate"),
            "dueTime": work.get("dueTime"),
        }

        students = classroom.list_students(course_id)
        by_user = {str(s.get("userId") or ""): s for s in students}
        submissions = classroom.list_submissions(course_id, work_id)
        for sub in submissions:
            uid = str(sub.get("userId") or "")
            student = by_user.get(uid) or {}
            attachments = []
            raw_attachments = ((sub.get("assignmentSubmission") or {}).get("attachments") or [])
            for idx, att in enumerate(raw_attachments):
                drive = att.get("driveFile") or {}
                item = {
                    "index": idx,
                    "title": drive.get("title") or (att.get("form") or {}).get("title") or (att.get("link") or {}).get("title"),
                    "id": drive.get("id"),
                    "alternateLink": drive.get("alternateLink") or (att.get("link") or {}).get("url"),
                    "thumbnailUrl": drive.get("thumbnailUrl"),
                }
                if drive.get("id"):
                    try:
                        item["metadata"] = classroom.get_drive_file_metadata(str(drive["id"]))
                    except Exception as exc:
                        item["metadata_error"] = str(exc)
                attachments.append(item)

            payload["rows"].append({
                "student_name": student.get("name"),
                "student_email": student.get("email"),
                "user_id": uid,
                "submission_id": sub.get("id"),
                "submission_url": sub.get("alternateLink"),
                "state": sub.get("state"),
                "late": sub.get("late"),
                "draftGrade": sub.get("draftGrade"),
                "assignedGrade": sub.get("assignedGrade"),
                "updateTime": sub.get("updateTime"),
                "attachments": attachments,
            })

        payload["rows"].sort(key=lambda r: _norm(r.get("student_name")))
        break

    print("MIDIENDO_WORK=" + json.dumps({
        "course": payload.get("course"),
        "coursework": payload.get("coursework"),
        "count": len(payload.get("rows") or []),
    }, ensure_ascii=False, default=str), flush=True)

    for row in payload.get("rows") or []:
        compact = {
            "student_name": row.get("student_name"),
            "student_email": row.get("student_email"),
            "user_id": row.get("user_id"),
            "submission_id": row.get("submission_id"),
            "submission_url": row.get("submission_url"),
            "state": row.get("state"),
            "late": row.get("late"),
            "draftGrade": row.get("draftGrade"),
            "assignedGrade": row.get("assignedGrade"),
            "updateTime": row.get("updateTime"),
            "attachments": [
                {
                    "index": att.get("index"),
                    "title": att.get("title"),
                    "id": att.get("id"),
                    "mimeType": (att.get("metadata") or {}).get("mimeType"),
                    "alternateLink": att.get("alternateLink"),
                }
                for att in (row.get("attachments") or [])
            ],
        }
        print("MIDIENDO_ROW=" + json.dumps(compact, ensure_ascii=False, default=str), flush=True)

    print(
        "MIDIENDO_INSPECT_READY: "
        f"{len(payload.get('rows') or [])} entrega(s) encontradas.",
        flush=True,
    )
    return payload
