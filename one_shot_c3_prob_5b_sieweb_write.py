from __future__ import annotations

import json, sys, unicodedata
from typing import Any

TARGET_TITLE = "C3 EVALUACIÓN PROBABILIDAD CONDICIONAL"
EXPECTED_CONTEXT = {"idAmbito":525,"idClase":2126,"idClasePeriodo":6593,"idContenido":119886,"idPeriodoAnt":6592}
TARGET_HEADERS = [136301,136302,136303,136304]
EXPECTED_PARENTS = {136301:134888,136302:134890,136303:134892,136304:134894}
ABBR = "C3 - Prob. condicional"

EXPECTED_NUMERIC = {
"ALESSIA FERREIRA TEJADA":20,"ALEXANDRO ARTURO MARTINEZ ARMAS":20,"ANDRE ROBERTO YAFAC MEDINA":20,
"ARIANA SOFIA FIGUEROA VARGAS":20,"DIEGO ALEJANDRO LINARES ARTETA":20,"DORIAN NICOLAS FERNANDEZ MORIS RODRIGUEZ":20,
"FATIMA GABRIELA MUJICA KCOMT":19,"FATIMA MIA VARGAS ASENCIO":19,"FERNANDA LUCIA GONZALES TAPIA":20,
"GRECIA LUCIA BAZAN ROMERO":20,"HANNA ELENA VALENZUELA CABALLERO":20,"JORGE LUIS SAAVEDRA BENITES":20,
"JORGE RODRIGO CALLE QUEVEDO":20,"LEONARDO RODRIGO CHOQUE GALINDO":19,"MARCO POLO TIMOTEO ESPINOZA":20,
"MATIAS ANTONIO ALIAGA MONTOYA":19,"MAURICIO JESUS PACO FERNANDEZ":20,"MAYA CUEVA VALERA":0,
"NAARA MILAGROS QUISPE FLORES":20,"NICOLAS ANTONIO VARGAS SOLIS":20,"RENZO RYUJI VEGA OYANAGI":12,
"RODRIGO ALBERTO CADILLO WONG":20,"RODRIGO ALONSO RODRIGUEZ GAMONAL":20,"SEBASTIAN CORADO RIOFRIO":20,
"VALERIA ANDREA IZAGUIRRE SOLIS":20,"XIMENA ALEXANDRA SUAREZ ARGOTE":5}

Q2_MINOR={"FATIMA GABRIELA MUJICA KCOMT","FATIMA MIA VARGAS ASENCIO","LEONARDO RODRIGO CHOQUE GALINDO","MATIAS ANTONIO ALIAGA MONTOYA"}

def _norm(v:Any)->str:
    t=unicodedata.normalize('NFD',str(v or ''))
    t=''.join(ch for ch in t if unicodedata.category(ch)!='Mn')
    return ' '.join(t.upper().replace(':',' ').split())

def _cell(student:dict[str,Any],hid:int)->str:
    n=student.get('notas') or {}; x=n.get(str(hid)) or n.get(hid) or {}
    v=x.get('notaReg'); v=x.get('notaIni') if v in (None,'') else v
    return str(v or '').strip().upper()

def _levels(name:str)->tuple[str,str,str,str]:
    if name in Q2_MINOR: return ('A','A','A','B')
    if name=="RENZO RYUJI VEGA OYANAGI": return ('B','B','B','C')
    if name in {"MAYA CUEVA VALERA","XIMENA ALEXANDRA SUAREZ ARGOTE"}: return ('C','C','C','C')
    return ('A','A','A','A')

def execute(classroom:Any,sieweb:Any)->dict[str,Any]:
    # Classroom exact activity and verified current numeric grades.
    course=work=None; wanted=_norm(TARGET_TITLE)
    for c in classroom.list_courses(active_only=True):
        hay=_norm(f"{c.get('name') or ''} {c.get('section') or ''}")
        if 'MATE 5TO' not in hay or ('5TO - B' not in hay and '5TO B' not in hay): continue
        ms=[w for w in classroom.list_coursework(str(c.get('id') or ''),include_drafts=True) if _norm(w.get('title'))==wanted]
        if len(ms)==1: course,work=c,ms[0]; break
    if not course or not work: raise RuntimeError('C3_PROB_SIEWEB: actividad exacta no encontrada en 5B.')
    cid=str(course.get('id') or ''); wid=str(work.get('id') or '')
    roster={str(s.get('userId') or ''):s for s in classroom.list_students(cid)}
    maps=[{}, {}, {}, {}]; rows=[]
    seen=set()
    for sub in classroom.list_submissions(cid,wid):
        st=roster.get(str(sub.get('userId') or '')) or {}; name=_norm(st.get('name')); code=str(st.get('email') or '').split('@',1)[0].strip()
        if not name or not code: raise RuntimeError('C3_PROB_SIEWEB: alumno sin nombre/código.')
        if name not in EXPECTED_NUMERIC: raise RuntimeError('C3_PROB_SIEWEB: alumno inesperado '+name)
        grade=sub.get('assignedGrade') if sub.get('assignedGrade') is not None else sub.get('draftGrade')
        if grade is None or float(grade)!=float(EXPECTED_NUMERIC[name]):
            raise RuntimeError('C3_PROB_SIEWEB: nota Classroom cambió para '+name+f' observed={grade} expected={EXPECTED_NUMERIC[name]}')
        lv=_levels(name)
        for i,val in enumerate(lv): maps[i][code]=val
        rows.append({'name':st.get('name'),'code':code,'numeric':grade,'levels':lv}); seen.add(name)
    if seen!=set(EXPECTED_NUMERIC) or len(rows)!=26: raise RuntimeError('C3_PROB_SIEWEB: roster no coincide con 26 revisados.')
    print('C3_PROB_SIEWEB_CLASSROOM='+json.dumps(rows,ensure_ascii=False),flush=True)

    ctx=sieweb.resolve_class_context(section='5B',period=2,course_code='05',id_ambito=525)
    obs={"idAmbito":int(ctx.get('idAmbito') or 525),"idClase":int(ctx.get('idClase') or 0),"idClasePeriodo":int(ctx.get('idClasePeriodo') or 0),"idContenido":int(ctx.get('idContenido') or 0),"idPeriodoAnt":int(ctx.get('idPeriodoAnt') or 0)}
    if obs!=EXPECTED_CONTEXT: raise RuntimeError('C3_PROB_SIEWEB: contexto cambió '+json.dumps(obs))
    extra={'idPeriodoAnt':EXPECTED_CONTEXT['idPeriodoAnt']}
    before=sieweb.get_gradebook_summary(class_period_id=6593,root_content_id=119886,extra_params=extra)
    criteria={int(c.get('id') or 0):c for c in (before.get('criteria') or [])}
    for hid in TARGET_HEADERS:
        c=criteria.get(hid)
        if not c or int(c.get('nivelEva') or 0)!=3 or int(c.get('idpadre') or 0)!=EXPECTED_PARENTS[hid] or _norm(c.get('abreviatura'))!=_norm(ABBR):
            raise RuntimeError(f'C3_PROB_SIEWEB: desempeño {hid} no coincide con el creado.')
        sieweb.assert_performance_target(before,header_id=hid,performance_level=3)
    students={str(s.get('alucod') or '').strip():s for s in (before.get('students') or [])}
    allcodes=set(maps[0])
    if len(students)!=26 or set(students)!=allcodes: raise RuntimeError('C3_PROB_SIEWEB: nómina SIEWeb/Classroom no coincide.')

    # No sobrescribir valores ajenos: solo blanco o el valor deseado es aceptable.
    conflicts=[]
    for i,hid in enumerate(TARGET_HEADERS):
        for code,desired in maps[i].items():
            cur=_cell(students[code],hid)
            if cur not in ('',desired): conflicts.append({'code':code,'header':hid,'current':cur,'desired':desired})
    if conflicts: raise RuntimeError('C3_PROB_SIEWEB: conflicto previo; no se escribió nada '+json.dumps(conflicts,ensure_ascii=False))

    others=[int(c.get('id') or 0) for c in (before.get('criteria') or []) if int(c.get('nivelEva') or 0)==3 and int(c.get('id') or 0) not in TARGET_HEADERS]
    snap={code:{str(h):_cell(st,h) for h in others} for code,st in students.items()}
    scope=(before.get('class') or {}).get('arrNivelGrado')
    writes=[]
    for i,hid in enumerate(TARGET_HEADERS):
        if all(_cell(students[code],hid)==desired for code,desired in maps[i].items()):
            writes.append({'header':hid,'already_present':True}); continue
        r=sieweb.save_grades_verified(year='2026',course_code='05',class_period_id=6593,root_content_id=119886,period=2,section_ng=scope,header_id=hid,grades_by_student_code=maps[i],class_name=None,extra_params=extra,notify=False,verification_attempts=3,protect_achievement_level=True,performance_level=3)
        writes.append({'header':hid,'result':r})
        print('C3_PROB_SIEWEB_WRITE='+json.dumps({'header':hid,'result':r},ensure_ascii=False,default=str),flush=True)

    after=sieweb.get_gradebook_summary(class_period_id=6593,root_content_id=119886,extra_params=extra)
    aft={str(s.get('alucod') or '').strip():s for s in (after.get('students') or [])}
    failures=[]
    for i,hid in enumerate(TARGET_HEADERS):
        for code,desired in maps[i].items():
            got=_cell(aft.get(code) or {},hid)
            if got!=desired: failures.append({'code':code,'header':hid,'expected':desired,'observed':got})
    untouched=[]
    for code,b in snap.items():
        a={str(h):_cell(aft.get(code) or {},h) for h in others}
        if a!=b: untouched.append(code)
    if failures or untouched: raise RuntimeError('C3_PROB_SIEWEB_FINAL_VERIFY_FAILED '+json.dumps({'failures':failures,'untouched':untouched},ensure_ascii=False))
    summary={'students':26,'headers':TARGET_HEADERS,'verified_cells':104,'untouched_changes':0,'writes':writes,'performance_counts':[{'header':TARGET_HEADERS[i],'A':sum(1 for v in maps[i].values() if v=='A'),'B':sum(1 for v in maps[i].values() if v=='B'),'C':sum(1 for v in maps[i].values() if v=='C')} for i in range(4)]}
    print('C3_PROB_SIEWEB_SUCCESS='+json.dumps(summary,ensure_ascii=False,default=str),flush=True)
    return {'queued':False,'count':26,'work':TARGET_TITLE,'verified_cells':104,'summary':summary}
