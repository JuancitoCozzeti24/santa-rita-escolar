from __future__ import annotations

import json
import unicodedata
from typing import Any

TARGET_ASSIGNMENT = "SUBIR AQUÍ FICHA INTRO MATRICES"


def _norm(value: Any) -> str:
    text = unicodedata.normalize("NFD", str(value or ""))
    text = "".join(ch for ch in text if unicodedata.category(ch) != "Mn")
    return " ".join(text.upper().split())


def inspect_zeroes(classroom: Any) -> dict[str, Any]:
    target_assignment_norm = _norm(TARGET_ASSIGNMENT)
    rows: list[dict[str, Any]] = []
    for course in classroom.list_courses(active_only=True):
        course_id = str(course.get("id") or "")
        course_hay = _norm(f"{course.get('name') or ''} {course.get('section') or ''}")
        if not course_id or "MATE 5TO" not in course_hay or ("5TO - B" not in course_hay and "5TO B" not in course_hay):
            continue
        works = classroom.list_coursework(course_id, include_drafts=True)
        work_matches = [w for w in works if _norm(w.get("title")) == target_assignment_norm]
        if len(work_matches) != 1:
            continue
        work = work_matches[0]
        work_id = str(work.get("id") or "")
        students = classroom.list_students(course_id)
        by_user = {str(s.get("userId") or ""): s for s in students}
        submissions = classroom.list_submissions(course_id, work_id)
        for sub in submissions:
            draft = sub.get("draftGrade")
            assigned = sub.get("assignedGrade")
            # Solo los que actualmente muestran 0 como calificación (borrador o final).
            zero = (draft is not None and float(draft) == 0.0) or (assigned is not None and float(assigned) == 0.0)
            if not zero:
                continue
            uid = str(sub.get("userId") or "")
            student = by_user.get(uid) or {}
            attachments = []
            for idx, att in enumerate(((sub.get("assignmentSubmission") or {}).get("attachments") or [])):
                drive = att.get("driveFile") or {}
                row = {
                    "index": idx,
                    "title": drive.get("title") or (att.get("form") or {}).get("title") or (att.get("link") or {}).get("title"),
                    "id": drive.get("id"),
                    "alternateLink": drive.get("alternateLink") or (att.get("link") or {}).get("url"),
                    "thumbnailUrl": drive.get("thumbnailUrl"),
                }
                if drive.get("id"):
                    try:
                        row["metadata"] = classroom.get_drive_file_metadata(str(drive["id"]))
                    except Exception as exc:
                        row["metadata_error"] = str(exc)
                attachments.append(row)
            rows.append({
                "course_id": course_id,
                "course_name": course.get("name"),
                "course_section": course.get("section"),
                "course_work_id": work_id,
                "course_work_title": work.get("title"),
                "student_name": student.get("name"),
                "student_email": student.get("email"),
                "user_id": uid,
                "submission_id": sub.get("id"),
                "submission_url": sub.get("alternateLink"),
                "state": sub.get("state"),
                "late": sub.get("late"),
                "draftGrade": draft,
                "assignedGrade": assigned,
                "updateTime": sub.get("updateTime"),
                "attachments": attachments,
            })
    rows.sort(key=lambda r: _norm(r.get("student_name")))
    payload = {"count": len(rows), "rows": rows}
    print("ZERO_GRADE_INSPECT_JSON=" + json.dumps(payload, ensure_ascii=False, default=str), flush=True)
    return payload
