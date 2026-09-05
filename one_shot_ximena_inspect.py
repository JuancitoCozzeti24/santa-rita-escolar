from __future__ import annotations

import json
import unicodedata
from typing import Any

TARGET_ASSIGNMENT = "SUBIR AQUÍ FICHA INTRO MATRICES"
TARGET_STUDENT_TOKENS = ("XIMENA", "SUAREZ")


def _norm(value: Any) -> str:
    text = unicodedata.normalize("NFD", str(value or ""))
    text = "".join(ch for ch in text if unicodedata.category(ch) != "Mn")
    return " ".join(text.upper().split())


def inspect_once(classroom: Any) -> dict[str, Any]:
    target_assignment_norm = _norm(TARGET_ASSIGNMENT)
    candidates: list[dict[str, Any]] = []

    for course in classroom.list_courses(active_only=True):
        course_id = str(course.get("id") or "")
        if not course_id:
            continue
        course_hay = _norm(f"{course.get('name') or ''} {course.get('section') or ''}")
        if "MATE 5TO" not in course_hay or ("5TO - B" not in course_hay and "5TO B" not in course_hay):
            continue
        works = classroom.list_coursework(course_id, include_drafts=True)
        matches = [w for w in works if _norm(w.get("title")) == target_assignment_norm]
        if len(matches) != 1:
            continue
        students = classroom.list_students(course_id)
        sm = []
        for student in students:
            hay = _norm(f"{student.get('name') or ''} {student.get('email') or ''}")
            if all(tok in hay for tok in TARGET_STUDENT_TOKENS):
                sm.append(student)
        if len(sm) != 1:
            continue
        student = sm[0]
        work = matches[0]
        submissions = classroom.list_submissions(course_id, str(work.get('id') or ''))
        subs = [s for s in submissions if str(s.get('userId') or '') == str(student.get('userId') or '')]
        if len(subs) != 1:
            continue
        sub = subs[0]
        full = classroom.get_submission(course_id, str(work.get('id')), str(sub.get('id')))
        attachments = ((full.get('assignmentSubmission') or {}).get('attachments') or [])
        files = []
        for idx, att in enumerate(attachments):
            drive = att.get('driveFile') or {}
            row = {
                'index': idx,
                'title': drive.get('title'),
                'id': drive.get('id'),
                'alternateLink': drive.get('alternateLink'),
                'thumbnailUrl': drive.get('thumbnailUrl'),
                'form': att.get('form'),
                'link': att.get('link'),
                'youtubeVideo': att.get('youTubeVideo'),
            }
            if drive.get('id'):
                try:
                    meta = classroom.get_drive_file_metadata(str(drive.get('id')))
                    row['metadata'] = {
                        'name': meta.get('name'),
                        'mimeType': meta.get('mimeType'),
                        'size': meta.get('size'),
                        'webViewLink': meta.get('webViewLink'),
                        'modifiedTime': meta.get('modifiedTime'),
                        'capabilities': meta.get('capabilities'),
                    }
                except Exception as exc:
                    row['metadata_error'] = str(exc)
            files.append(row)
        candidates.append({
            'course_id': course_id,
            'course_name': course.get('name'),
            'course_section': course.get('section'),
            'course_work_id': work.get('id'),
            'course_work_title': work.get('title'),
            'student_name': student.get('name'),
            'student_email': student.get('email'),
            'user_id': student.get('userId'),
            'submission_id': sub.get('id'),
            'submission_url': sub.get('alternateLink'),
            'state': sub.get('state'),
            'late': sub.get('late'),
            'draftGrade': sub.get('draftGrade'),
            'assignedGrade': sub.get('assignedGrade'),
            'updateTime': sub.get('updateTime'),
            'attachments': files,
        })

    unique = {(c['course_id'], c['course_work_id'], c['submission_id']): c for c in candidates}
    candidates = list(unique.values())
    if len(candidates) != 1:
        raise RuntimeError(
            f"XIMENA_INSPECT_TARGET_NOT_UNIQUE: expected 1 target, found {len(candidates)}"
        )
    result = candidates[0]
    print("XIMENA_INSPECT_JSON=" + json.dumps(result, ensure_ascii=False), flush=True)
    return result
