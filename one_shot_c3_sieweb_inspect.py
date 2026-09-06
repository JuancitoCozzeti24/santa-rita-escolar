from __future__ import annotations

import json
import unicodedata
from typing import Any


def _norm(v: Any) -> str:
    t = unicodedata.normalize('NFD', str(v or ''))
    t = ''.join(ch for ch in t if unicodedata.category(ch) != 'Mn')
    return ' '.join(t.upper().split())


def inspect(classroom: Any, sieweb: Any) -> dict[str, Any]:
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
    grades.sort(key=lambda x: _norm(x.get('name')))
    print('C3_CLASSROOM_GRADES_COMPACT=' + json.dumps(grades, ensure_ascii=False), flush=True)

    ctx = sieweb.resolve_class_context(section='5B', period=2, course_code='05', id_ambito=525)
    extra = {'idPeriodoAnt': ctx.get('idPeriodoAnt', 0)}
    summary = sieweb.get_gradebook_summary(class_period_id=ctx['idClasePeriodo'], root_content_id=ctx['idContenido'], extra_params=extra)
    print('C3_SIEWEB_CONTEXT=' + json.dumps(ctx, ensure_ascii=False, default=str), flush=True)
    criteria = summary.get('criteria') or []
    print('C3_SIEWEB_CRITERIA=' + json.dumps(criteria, ensure_ascii=False, default=str), flush=True)
    searches = {q: sieweb.find_criteria_in_gradebook(summary, q) for q in ('C3','MATRIZ','MATRICES','EVALUACION','SEMANAL')}
    print('C3_SIEWEB_SEARCHES=' + json.dumps(searches, ensure_ascii=False, default=str), flush=True)
    # Student cells are included so we can compare existing SIEWeb values before writing.
    print('C3_SIEWEB_STUDENTS=' + json.dumps(summary.get('students') or [], ensure_ascii=False, default=str), flush=True)
    return {'queued': False, 'course_name': course.get('name'), 'work': work.get('title'), 'count': len(grades), 'context': ctx}
