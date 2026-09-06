from __future__ import annotations

import json
import unicodedata
from typing import Any

TARGET_TOKENS = ("C3", "EVALUACION", "SEMANAL", "MATRICES")
TARGET_STUDENTS = [
    ("RENZO", "VEGA"),
    ("DIEGO", "LINARES"),
    ("RODRIGO", "RODRIGUEZ"),
    ("MATIAS", "ALIAGA"),
    ("FATIMA", "MUJICA"),
]


def _norm(value: Any) -> str:
    text = unicodedata.normalize("NFD", str(value or ""))
    text = "".join(ch for ch in text if unicodedata.category(ch) != "Mn")
    return " ".join(text.upper().split())


def inspect(classroom: Any) -> dict[str, Any]:
    course = work = None
    for c in classroom.list_courses(active_only=True):
        hay = _norm(f"{c.get('name') or ''} {c.get('section') or ''}")
        if "MATE 5TO" not in hay or not ("5TO - B" in hay or "5TO B" in hay):
            continue
        works = classroom.list_coursework(str(c.get("id") or ""), include_drafts=True)
        matches = []
        for w in works:
            title = _norm(w.get("title"))
            if all(tok in title for tok in TARGET_TOKENS):
                matches.append(w)
        if len(matches) == 1:
            course, work = c, matches[0]
            break
        if len(matches) > 1:
            raise RuntimeError("C3_INSPECT: hay más de una actividad que coincide con C3 Evaluación semanal de matrices.")
    if not course or not work:
        raise RuntimeError("C3_INSPECT: no se encontró la actividad C3 Evaluación semanal de matrices en 5.º B.")

    course_id = str(course.get("id") or "")
    work_id = str(work.get("id") or "")
    students = classroom.list_students(course_id)
    submissions = classroom.list_submissions(course_id, work_id)
    by_user = {str(s.get("userId") or ""): s for s in students}

    rows = []
    for tokens in TARGET_STUDENTS:
        found = []
        for sub in submissions:
            st = by_user.get(str(sub.get("userId") or "")) or {}
            hay = _norm(f"{st.get('name') or ''} {st.get('email') or ''}")
            if all(tok in hay for tok in tokens):
                found.append((st, sub))
        if len(found) != 1:
            raise RuntimeError(f"C3_INSPECT: {' '.join(tokens)} coincide con {len(found)} estudiantes.")
        st, sub = found[0]
        attachments = []
        for idx, att in enumerate(((sub.get("assignmentSubmission") or {}).get("attachments") or [])):
            drive = att.get("driveFile") or {}
            link = att.get("link") or {}
            yt = att.get("youTubeVideo") or {}
            attachments.append({
                "index": idx,
                "title": drive.get("title") or link.get("title") or yt.get("title"),
                "id": drive.get("id"),
                "alternateLink": drive.get("alternateLink") or link.get("url"),
                "mimeType": drive.get("mimeType"),
            })
        row = {
            "student_name": st.get("name"),
            "student_email": st.get("email"),
            "user_id": st.get("userId"),
            "submission_id": sub.get("id"),
            "submission_url": sub.get("alternateLink"),
            "state": sub.get("state"),
            "late": sub.get("late"),
            "draftGrade": sub.get("draftGrade"),
            "assignedGrade": sub.get("assignedGrade"),
            "updateTime": sub.get("updateTime"),
            "attachments": attachments,
        }
        rows.append(row)
        print("C3_MATRIX_ROW=" + json.dumps(row, ensure_ascii=False), flush=True)

    result = {
        "course_id": course_id,
        "course_name": course.get("name"),
        "course_work_id": work_id,
        "course_work_title": work.get("title"),
        "maxPoints": work.get("maxPoints"),
        "count": len(rows),
        "rows": rows,
    }
    print("C3_MATRIX_WORK=" + json.dumps({k: result[k] for k in ("course_id","course_name","course_work_id","course_work_title","maxPoints","count")}, ensure_ascii=False), flush=True)
    print("C3_MATRIX_INSPECT_READY: 5 estudiantes objetivo inspeccionados; no se modificó Classroom.", flush=True)
    return result
