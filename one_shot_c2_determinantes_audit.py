from __future__ import annotations

import json
import unicodedata
from typing import Any

TARGET_TITLE = "C2: Desarrollar tarea de determinantes"


def _norm(value: Any) -> str:
    text = unicodedata.normalize("NFD", str(value or ""))
    text = "".join(ch for ch in text if unicodedata.category(ch) != "Mn")
    return " ".join(text.upper().split())


def inspect(classroom: Any) -> dict[str, Any]:
    course = work = None
    wanted = _norm(TARGET_TITLE)
    for c in classroom.list_courses(active_only=True):
        hay = _norm(f"{c.get('name') or ''} {c.get('section') or ''}")
        if "MATE 5TO" not in hay or ("5TO - B" not in hay and "5TO B" not in hay):
            continue
        works = classroom.list_coursework(str(c.get("id") or ""), include_drafts=True)
        exact = [w for w in works if _norm(w.get("title")) == wanted]
        if len(exact) == 1:
            course, work = c, exact[0]
            break
    if not course or not work:
        raise RuntimeError("C2_DET_AUDIT: no se encontró de forma única la actividad exacta en 5B.")

    course_id = str(course.get("id") or "")
    work_id = str(work.get("id") or "")
    roster = classroom.list_students(course_id)
    by_user = {str(s.get("userId") or ""): s for s in roster}

    pending = []
    all_rows = []
    for sub in classroom.list_submissions(course_id, work_id):
        st = by_user.get(str(sub.get("userId") or "")) or {}
        grade = sub.get("assignedGrade") if sub.get("assignedGrade") is not None else sub.get("draftGrade")
        attachments = sub.get("attachments") or []
        row = {
            "name": st.get("name"),
            "email": st.get("email"),
            "userId": sub.get("userId"),
            "submissionId": sub.get("id"),
            "state": sub.get("state"),
            "draftGrade": sub.get("draftGrade"),
            "assignedGrade": sub.get("assignedGrade"),
            "effectiveGrade": grade,
            "late": sub.get("late"),
            "alternateLink": sub.get("alternateLink"),
            "attachments": attachments,
        }
        all_rows.append(row)
        try:
            is_zero = grade is not None and float(grade) == 0.0
        except Exception:
            is_zero = False
        if is_zero:
            pending.append(row)

    all_rows.sort(key=lambda x: _norm(x.get("name")))
    pending.sort(key=lambda x: _norm(x.get("name")))
    print("C2_DET_WORK=" + json.dumps({
        "course": course.get("name"),
        "section": course.get("section"),
        "courseId": course_id,
        "title": work.get("title"),
        "courseWorkId": work_id,
        "maxPoints": work.get("maxPoints"),
    }, ensure_ascii=False, default=str), flush=True)
    print("C2_DET_ZERO_PENDING=" + json.dumps(pending, ensure_ascii=False, default=str), flush=True)
    print("C2_DET_ZERO_COUNT=" + str(len(pending)), flush=True)
    print("C2_DET_ALL=" + json.dumps(all_rows, ensure_ascii=False, default=str), flush=True)
    return {
        "queued": False,
        "count": 0,
        "course_name": course.get("name"),
        "work": work.get("title"),
        "pending_count": len(pending),
        "pending": pending,
    }
