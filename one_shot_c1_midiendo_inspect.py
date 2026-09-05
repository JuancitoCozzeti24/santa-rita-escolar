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
    target = _norm(TARGET_ASSIGNMENT)
    course = None
    work = None
    for c in classroom.list_courses(active_only=True):
        hay = _norm(f"{c.get('name') or ''} {c.get('section') or ''}")
        if "MATE 5TO" not in hay or not ("5TO - B" in hay or "5TO B" in hay):
            continue
        works = classroom.list_coursework(str(c.get("id") or ""), include_drafts=True)
        matches = [w for w in works if _norm(w.get("title")) == target]
        if len(matches) == 1:
            course, work = c, matches[0]
            break
    if not course or not work:
        raise RuntimeError("C1_MIDIENDO_INSPECT: no se encontró de forma única MATE 5TO-B / C1: FICHA DE MIDIENDO NUESTRO AVANCE.")

    course_id = str(course.get("id") or "")
    work_id = str(work.get("id") or "")
    students = classroom.list_students(course_id)
    submissions = classroom.list_submissions(course_id, work_id)
    by_user = {str(s.get("userId") or ""): s for s in students}

    rows = []
    for sub in submissions:
        st = by_user.get(str(sub.get("userId") or "")) or {}
        attachments = ((sub.get("assignmentSubmission") or {}).get("attachments") or [])
        att_rows = []
        for att in attachments:
            if att.get("driveFile"):
                df = att.get("driveFile") or {}
                att_rows.append({
                    "type": "driveFile",
                    "id": df.get("id"),
                    "title": df.get("title"),
                    "alternateLink": df.get("alternateLink"),
                    "thumbnailUrl": df.get("thumbnailUrl"),
                })
            elif att.get("link"):
                lk = att.get("link") or {}
                att_rows.append({"type": "link", "url": lk.get("url"), "title": lk.get("title"), "thumbnailUrl": lk.get("thumbnailUrl")})
            elif att.get("youTubeVideo"):
                yt = att.get("youTubeVideo") or {}
                att_rows.append({"type": "youtube", "id": yt.get("id"), "title": yt.get("title"), "alternateLink": yt.get("alternateLink")})
            else:
                att_rows.append({"type": "other", "raw": att})
        rows.append({
            "student_name": st.get("name"),
            "student_email": st.get("email"),
            "user_id": sub.get("userId"),
            "submission_id": sub.get("id"),
            "submission_url": sub.get("alternateLink"),
            "state": sub.get("state"),
            "late": sub.get("late"),
            "draftGrade": sub.get("draftGrade"),
            "assignedGrade": sub.get("assignedGrade"),
            "updateTime": sub.get("updateTime"),
            "attachments": att_rows,
        })

    rows.sort(key=lambda r: _norm(r.get("student_name")))
    payload = {
        "course_id": course_id,
        "course_name": course.get("name"),
        "course_section": course.get("section"),
        "course_work_id": work_id,
        "course_work_title": work.get("title"),
        "count": len(rows),
        "rows": rows,
    }
    print("C1_MIDIENDO_INSPECT_JSON=" + json.dumps(payload, ensure_ascii=False), flush=True)
    return payload
