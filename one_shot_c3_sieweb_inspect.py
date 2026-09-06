from __future__ import annotations

import json
import unicodedata
from typing import Any

HEADERS = [135935, 135936, 135937, 135938]

def _norm(v: Any) -> str:
    t = unicodedata.normalize('NFD', str(v or ''))
    t = ''.join(ch for ch in t if unicodedata.category(ch) != 'Mn')
    return ' '.join(t.upper().split())

def _qual(g: Any) -> str | None:
    if g is None: return None
    x = float(g)
    return 'A' if x >= 15 else ('B' if x >= 11 else 'C')

def inspect(classroom: Any, sieweb: Any) -> dict[str, Any]:
    course = work = None
    for c in classroom.list_courses(active_only=True):
        hay = _norm(f"{c.get('name') or ''} {c.get('section') or ''}")
        if 'MATE 5TO' in hay and ('5TO - B' in hay or '5TO B' in hay):
            m = [w for w in classroom.list_coursework(str(c.get('id') or ''), include_drafts=True)
                 if all(tok in _norm(w.get('title')) for tok in ('C3','EVALUACION','SEMANAL','MATRICES'))]
            if len(m) == 1: course, work = c, m[0]; break
    if not course or not work: raise RuntimeError('C3_SIEWEB_INSPECT: actividad no encontrada de forma única.')
    cid, wid = str(course['id']), str(work['id'])
    by_user = {str(s.get('userId') or ''): s for s in classroom.list_students(cid)}
    class_by_code = {}
    for sub in classroom.list_submissions(cid, wid):
        st = by_user.get(str(sub.get('userId') or '')) or {}
        code = str(st.get('email') or '').split('@',1)[0]
        g = sub.get('assignedGrade') if sub.get('assignedGrade') is not None else sub.get('draftGrade')
        class_by_code[code] = {'name': st.get('name'), 'grade': g, 'target': _qual(g)}

    ctx = sieweb.resolve_class_context(section='5B', period=2, course_code='05', id_ambito=525)
    summary = sieweb.get_gradebook_summary(class_period_id=ctx['idClasePeriodo'], root_content_id=ctx['idContenido'], extra_params={'idPeriodoAnt': ctx.get('idPeriodoAnt',0)})
    for h in HEADERS: sieweb.assert_performance_target(summary, header_id=h, performance_level=3)
    comparison = []
    for s in summary.get('students') or []:
        code = str(s.get('alucod') or '')
        cr = class_by_code.get(code)
        if not cr: continue
        notas = s.get('notas') or {}
        current = []
        for h in HEADERS:
            cell = notas.get(str(h)) or notas.get(h) or {}
            current.append(cell.get('notaReg') if cell.get('notaReg') not in (None,'') else cell.get('notaIni'))
        comparison.append({'code':code,'name':cr['name'],'numeric':cr['grade'],'target':cr['target'],'current':current,'needs_change':any(v != cr['target'] for v in current)})
    comparison.sort(key=lambda x: _norm(x['name']))
    print('C3_SIEWEB_COMPARISON=' + json.dumps(comparison, ensure_ascii=False), flush=True)
    print('C3_SIEWEB_MISMATCHES=' + json.dumps([x for x in comparison if x['needs_change']], ensure_ascii=False), flush=True)
    return {'queued':False,'course_name':course.get('name'),'work':work.get('title'),'count':len(comparison),'context':ctx}
