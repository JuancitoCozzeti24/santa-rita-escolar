from __future__ import annotations

import json
import unicodedata
from typing import Any


def _norm(v: Any) -> str:
    t = unicodedata.normalize('NFD', str(v or ''))
    t = ''.join(ch for ch in t if unicodedata.category(ch) != 'Mn')
    return ' '.join(t.upper().split())


def inspect(classroom: Any, sieweb: Any) -> dict[str, Any]:
    # Classroom: current official grades for exact C3.
    course = work = None
    for c in classroom.list_courses(active_only=True):
        hay = _norm(f"{c.get('name') or ''} {c.get('section') or ''}")
        if 'MATE 5TO' in hay and ('5TO - B' in hay or '5TO B' in hay):
            matches = [w for w in classroom.list_coursework(str(c.get('id') or ''), include_drafts=True)
                       if all(tok in _norm(w.get('title')) for tok in ('C3','EVALUACION','SEMANAL','MATRICES'))]
            if len(matches) == 1:
                course, work = c, matches[0]; break
    if not course or not work:
        raise RuntimeError('C3_SIEWEB_INSPECT: no se encontró la actividad exacta en 5B.')
    cid = str(course.get('id') or ''); wid = str(work.get('id') or '')
    roster = classroom.list_students(cid); by_user = {str(s.get('userId') or ''): s for s in roster}
    grades = []
    for sub in classroom.list_submissions(cid, wid):
        st = by_user.get(str(sub.get('userId') or '')) or {}
        grade = sub.get('assignedGrade') if sub.get('assignedGrade') is not None else sub.get('draftGrade')
        grades.append({'name': st.get('name'), 'code': str(st.get('email') or '').split('@',1)[0], 'grade': grade})
    print('C3_CLASSROOM_GRADES_COMPACT=' + json.dumps(grades, ensure_ascii=False), flush=True)

    # Discover 5B scope read-only. 5A is known as 524; scan nearby scopes and inspect class names.
    candidates = {}
    for ambito in range(520, 531):
        try:
            payload = sieweb.list_classes(id_ambito=ambito)
            rows = (payload.get('json') or []) if isinstance(payload, dict) else []
            if rows:
                candidates[str(ambito)] = rows
        except Exception as exc:
            candidates[str(ambito)] = {'error': str(exc)}
    print('C3_SIEWEB_AMBITO_SCAN=' + json.dumps(candidates, ensure_ascii=False, default=str), flush=True)
    return {'queued': False, 'course_name': course.get('name'), 'work': work.get('title'), 'count': len(grades)}
