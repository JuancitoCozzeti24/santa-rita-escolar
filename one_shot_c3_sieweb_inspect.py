from __future__ import annotations

import json
import unicodedata
from typing import Any


def _norm(v: Any) -> str:
    t = unicodedata.normalize('NFD', str(v or ''))
    t = ''.join(ch for ch in t if unicodedata.category(ch) != 'Mn')
    return ' '.join(t.upper().split())


def _scalar(d: dict[str, Any], *keys: str) -> Any:
    wanted = {k.lower() for k in keys}
    for k, v in d.items():
        if str(k).lower() in wanted:
            return v
    return None


def _collect_level3(value: Any, out: list[dict[str, Any]], seen: set[str]) -> None:
    if isinstance(value, dict):
        level = _scalar(value, 'nivelEva', 'NIVEL_EVA', 'nivel', 'NIVEL')
        try:
            is3 = int(level) == 3
        except Exception:
            is3 = False
        if is3:
            row = {
                'id': _scalar(value, 'id', 'ID', 'idContenido', 'ID_CONTENIDO', 'idClaseContenido', 'ID_CLASE_CONTENIDO'),
                'parent_id': _scalar(value, 'idpadre', 'ID_PADRE', 'idContenidoRef', 'ID_CONTENIDO_REF', 'parent_id'),
                'description': _scalar(value, 'descripcion', 'DESCRIPCION', 'description', 'nombre', 'NOMBRE'),
                'abbr': _scalar(value, 'abreviatura', 'ABREVIATURA', 'abrev', 'ABREV', 'nomCorto', 'NOM_CORTO'),
                'nivelEva': level,
                'raw_header_id': _scalar(value, 'idCabecera', 'ID_CABECERA', 'header_id', 'idNota', 'ID_NOTA'),
            }
            key = json.dumps(row, ensure_ascii=False, sort_keys=True, default=str)
            if key not in seen:
                seen.add(key); out.append(row)
        for v in value.values():
            _collect_level3(v, out, seen)
    elif isinstance(value, list):
        for item in value:
            _collect_level3(item, out, seen)


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
    roster = classroom.list_students(cid)
    by_user = {str(s.get('userId') or ''): s for s in roster}
    rows = []
    for sub in classroom.list_submissions(cid, wid):
        st = by_user.get(str(sub.get('userId') or '')) or {}
        grade = sub.get('assignedGrade')
        source = 'assignedGrade'
        if grade is None:
            grade = sub.get('draftGrade'); source = 'draftGrade'
        rows.append({
            'name': st.get('name'), 'email': st.get('email'), 'code': str(st.get('email') or '').split('@',1)[0],
            'state': sub.get('state'), 'assignedGrade': sub.get('assignedGrade'), 'draftGrade': sub.get('draftGrade'),
            'effective_grade': grade, 'grade_source': source if grade is not None else None,
        })
    rows.sort(key=lambda r: _norm(r.get('name')))
    print('C3_CLASSROOM_GRADES=' + json.dumps(rows, ensure_ascii=False, default=str), flush=True)

    ctx = sieweb.resolve_class_context(section='5B', period=2, course_code='05', id_ambito=None)
    extra = {'idPeriodoAnt': ctx.get('idPeriodoAnt', 0)}
    summary = sieweb.get_gradebook_summary(class_period_id=ctx['idClasePeriodo'], root_content_id=ctx['idContenido'], extra_params=extra)
    print('C3_SIEWEB_CONTEXT=' + json.dumps(ctx, ensure_ascii=False, default=str), flush=True)
    print('C3_SIEWEB_SUMMARY_KEYS=' + json.dumps(sorted(summary.keys()), ensure_ascii=False), flush=True)
    lvl3: list[dict[str, Any]] = []
    _collect_level3(summary, lvl3, set())
    print('C3_SIEWEB_LEVEL3=' + json.dumps(lvl3, ensure_ascii=False, default=str), flush=True)

    # También usa el buscador nativo para términos probables del ítem.
    searches = {}
    for q in ('C3', 'MATRIZ', 'MATRICES', 'EVALUACION', 'SEMANAL'):
        try:
            searches[q] = sieweb.find_criteria_in_gradebook(summary, q)
        except Exception as exc:
            searches[q] = {'error': str(exc)}
    print('C3_SIEWEB_SEARCHES=' + json.dumps(searches, ensure_ascii=False, default=str), flush=True)
    return {'course_name': course.get('name'), 'work': work.get('title'), 'count': len(rows), 'context': ctx}
