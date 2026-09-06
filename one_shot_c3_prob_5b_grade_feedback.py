from __future__ import annotations

import json, unicodedata
from typing import Any

TARGET = "C3 EVALUACIÓN PROBABILIDAD CONDICIONAL"

GRADES = {
    "ALESSIA FERREIRA TEJADA": 20,
    "ALEXANDRO ARTURO MARTINEZ ARMAS": 20,
    "ANDRE ROBERTO YAFAC MEDINA": 20,
    "ARIANA SOFIA FIGUEROA VARGAS": 20,
    "DIEGO ALEJANDRO LINARES ARTETA": 20,
    "DORIAN NICOLAS FERNANDEZ MORIS RODRIGUEZ": 20,
    "FATIMA GABRIELA MUJICA KCOMT": 19,
    "FATIMA MIA VARGAS ASENCIO": 19,
    "FERNANDA LUCIA GONZALES TAPIA": 20,
    "GRECIA LUCIA BAZAN ROMERO": 20,
    "HANNA ELENA VALENZUELA CABALLERO": 20,
    "JORGE LUIS SAAVEDRA BENITES": 20,
    "JORGE RODRIGO CALLE QUEVEDO": 20,
    "LEONARDO RODRIGO CHOQUE GALINDO": 19,
    "MARCO POLO TIMOTEO ESPINOZA": 20,
    "MATIAS ANTONIO ALIAGA MONTOYA": 19,
    "MAURICIO JESUS PACO FERNANDEZ": 20,
    "MAYA CUEVA VALERA": 0,
    "NAARA MILAGROS QUISPE FLORES": 20,
    "NICOLAS ANTONIO VARGAS SOLIS": 20,
    "RENZO RYUJI VEGA OYANAGI": 12,
    "RODRIGO ALBERTO CADILLO WONG": 20,
    "RODRIGO ALONSO RODRIGUEZ GAMONAL": 20,
    "SEBASTIAN CORADO RIOFRIO": 20,
    "VALERIA ANDREA IZAGUIRRE SOLIS": 20,
    "XIMENA ALEXANDRA SUAREZ ARGOTE": 5,
}

Q2_WRONG_START = {
    "FATIMA GABRIELA MUJICA KCOMT": "4/52 = 1/4",
    "FATIMA MIA VARGAS ASENCIO": "4/52 → 1/4",
    "LEONARDO RODRIGO CHOQUE GALINDO": "13/52 = 1/4",
    "MATIAS ANTONIO ALIAGA MONTOYA": "13/52 → 1/4",
}


def _norm(v: Any) -> str:
    t=unicodedata.normalize("NFD",str(v or ""))
    t="".join(ch for ch in t if unicodedata.category(ch)!="Mn")
    return " ".join(t.upper().replace(":"," ").split())


def _first(name: str) -> str:
    return str(name or "Estudiante").split()[0].title()


def _perfect(name: str) -> str:
    f=_first(name)
    return f"""{f},
He revisado de manera detallada tu evidencia de C3: Evaluación de probabilidad condicional.

LO QUE HICISTE BIEN:
Pregunta 1: identificaste correctamente 5 casos favorables de 8 posibles y obtuviste 5/8 = 0,625 = 62,5%.
Pregunta 2: llegaste correctamente a 1/4 = 25%, que corresponde a 1 as de corazones entre los 4 ases cuando el espacio muestral queda condicionado a que la carta sea un as.
Pregunta 3: trabajaste correctamente con el grupo condicionado de 12 mujeres y obtuviste 8/12 = 2/3 ≈ 66,7% para la probabilidad de que use lentes.
Pregunta 4: restringiste correctamente los casos a las cinco parejas cuya suma es 6 y reconociste dos casos favorables, obteniendo 2/5 = 0,4 = 40%.

LO QUE DEBES MEJORAR:
No se identificaron errores matemáticos que requieran corrección en las cuatro respuestas revisadas. Como mejora de presentación, mantén siempre visible cuál es el espacio muestral después de aplicar la condición, porque esa es la idea central de la probabilidad condicional.

SUGERENCIAS:
Antes de efectuar una división, escribe primero la condición y vuelve a contar los casos posibles dentro de ese nuevo conjunto. Esto hace que el procedimiento sea más claro y evita confundir probabilidades simples con probabilidades condicionadas.

Tu calificación es 20/20 - (A).""".strip()


def _q2_minor(name: str, shown: str) -> str:
    f=_first(name)
    return f"""{f},
He revisado de manera detallada tu evidencia de C3: Evaluación de probabilidad condicional.

LO QUE HICISTE BIEN:
Pregunta 1: resolviste correctamente 5/8 = 0,625 = 62,5%.
Pregunta 2: tu resultado final 1/4 = 25% es correcto.
Pregunta 3: resolviste correctamente 8/12 = 2/3 ≈ 66,7%.
Pregunta 4: identificaste correctamente los cinco casos posibles cuya suma es 6 y los dos casos en los que aparece un 2, obteniendo 2/5 = 40%.

LO QUE DEBES MEJORAR:
Pregunta 2:
Tu respuesta/procedimiento: escribiste {shown} para llegar al 25%.
Error detectado: esa fracción inicial no representa el espacio muestral condicionado. Una vez que se sabe que la carta extraída es un as, ya no se trabaja con las 52 cartas de la baraja, sino únicamente con los 4 ases.
Procedimiento correcto: entre los 4 ases posibles existe exactamente 1 as de corazones, por lo que P(corazones | as) = 1/4.
Resultado correcto: 1/4 = 0,25 = 25%.

SUGERENCIAS:
En probabilidad condicional, aplica primero la condición y redefine el total de casos posibles. Después cuenta los casos favorables dentro de ese nuevo espacio muestral. Tu resultado fue correcto; lo que debes fortalecer es la justificación del procedimiento.

Tu calificación es 19/20 - (A).""".strip()


def _renzo(name: str) -> str:
    f=_first(name)
    return f"""{f},
He revisado de manera detallada tu evidencia de C3: Evaluación de probabilidad condicional.

LO QUE HICISTE BIEN:
Pregunta 1: registraste correctamente 62,5%, que corresponde a 5/8.
Pregunta 2: registraste correctamente 1/4 = 25% para el as de corazones dado que la carta es un as.
Pregunta 3: identificaste los datos relevantes: 20 estudiantes, 12 mujeres y 8 mujeres que usan lentes.

LO QUE DEBES MEJORAR:
Pregunta 3:
Tu respuesta/procedimiento: anotaste los datos 20, 12 y 8, pero no completaste el cálculo de la probabilidad solicitada.
Error detectado: al saberse que el estudiante elegido es mujer, el total condicionado es 12, no 20.
Procedimiento correcto: casos favorables = 8 mujeres que usan lentes; casos posibles bajo la condición = 12 mujeres. Entonces 8/12 = 2/3.
Resultado correcto: 2/3 ≈ 0,667 = 66,7%.

Pregunta 4:
Tu respuesta/procedimiento: aparecen anotaciones parciales, pero no se observa un cálculo completo ni una respuesta final verificable.
Error detectado: faltó construir el espacio muestral condicionado por la suma 6.
Procedimiento correcto: las parejas posibles son (1,5), (2,4), (3,3), (4,2) y (5,1). Los casos favorables en los que aparece un 2 son (2,4) y (4,2).
Resultado correcto: 2/5 = 0,4 = 40%.

SUGERENCIAS:
No te quedes únicamente en la identificación de los datos. En cada ejercicio escribe el espacio muestral condicionado, los casos favorables, la fracción final y su porcentaje. Eso permitirá evidenciar todo tu razonamiento.

Tu calificación es 12/20 - (B).""".strip()


def _ximena(name: str) -> str:
    f=_first(name)
    return f"""{f},
He revisado la evidencia adjunta en C3: Evaluación de probabilidad condicional.

LO QUE HICISTE BIEN:
La evidencia presentada es un video relacionado con probabilidad y permite reconocer una aproximación al tema trabajado. Sin embargo, no corresponde al formato JPG solicitado ni muestra de forma verificable el desarrollo de las cuatro preguntas específicas de esta evaluación.

LO QUE DEBES MEJORAR:
Pregunta 1:
Evidencia presentada: en el video no se observa una respuesta verificable a la pregunta de la urna con 5 bolas rojas y 3 bolas azules.
Dificultad para evaluar: al no aparecer el ejercicio del examen, no se puede comprobar tu procedimiento.
Procedimiento esperado: comparar 5 casos favorables con 8 casos posibles.
Resultado esperado: 5/8 = 0,625 = 62,5%.

Pregunta 2:
Evidencia presentada: no se observa una respuesta verificable al problema del as de corazones condicionado a que la carta sea un as.
Dificultad para evaluar: el video no muestra el procedimiento correspondiente a esta pregunta.
Procedimiento esperado: restringir el espacio muestral a los 4 ases y reconocer 1 as de corazones.
Resultado esperado: 1/4 = 25%.

Pregunta 3:
Evidencia presentada: no se observa una respuesta verificable al problema de las 12 mujeres, de las cuales 8 usan lentes.
Dificultad para evaluar: no aparece el cálculo correspondiente a la condición de que el estudiante elegido sea mujer.
Procedimiento esperado: usar 8 casos favorables entre 12 mujeres.
Resultado esperado: 8/12 = 2/3 ≈ 66,7%.

Pregunta 4:
Evidencia presentada: no se observa una respuesta verificable al problema de los dos dados condicionado a que la suma sea 6.
Dificultad para evaluar: no aparecen los cinco casos posibles ni los dos casos favorables de la evaluación.
Procedimiento esperado: considerar (1,5), (2,4), (3,3), (4,2) y (5,1), con dos casos donde aparece un 2.
Resultado esperado: 2/5 = 40%.

SUGERENCIAS:
Antes de entregar, verifica el formato solicitado y que el archivo corresponda exactamente a la actividad. Cuando se pida evidencia de una evaluación escrita, debe verse con claridad cada pregunta, su procedimiento y su respuesta final.

Tu calificación es 5/20 - (C).""".strip()


def _missing(name: str) -> str:
    f=_first(name)
    return f"""{f},
He revisado tu estado de entrega en C3: Evaluación de probabilidad condicional.

LO QUE HICISTE BIEN:
En esta oportunidad no se cuenta con una evidencia presentada que permita reconocer logros específicos de aprendizaje en las cuatro preguntas de la evaluación.

LO QUE DEBES MEJORAR:
No se presentó la fotografía solicitada del cuaderno, por lo que no es posible revisar procedimientos, operaciones ni respuestas de la evaluación. Al no existir evidencia, la actividad mantiene calificación cero.

SUGERENCIAS:
Fortalece la organización de tus tiempos y verifica siempre en Classroom que la evidencia haya quedado correctamente adjuntada y entregada dentro del plazo correspondiente.

Tu calificación es 0/20 - (C).""".strip()


def _comment(name: str, grade: int) -> str:
    if grade == 20:
        return _perfect(name)
    if name in Q2_WRONG_START:
        return _q2_minor(name,Q2_WRONG_START[name])
    if name == "RENZO RYUJI VEGA OYANAGI":
        return _renzo(name)
    if name == "XIMENA ALEXANDRA SUAREZ ARGOTE":
        return _ximena(name)
    if name == "MAYA CUEVA VALERA":
        return _missing(name)
    raise RuntimeError(f"C3_PROB_5B: no hay plantilla de comentario para {name} grade={grade}")


def execute(classroom: Any, bridge_queue: Any) -> dict[str, Any]:
    wanted=_norm(TARGET)
    course=work=None
    for c in classroom.list_courses(active_only=True):
        hay=_norm(f"{c.get('name') or ''} {c.get('section') or ''}")
        if "MATE 5TO" not in hay or ("5TO - B" not in hay and "5TO B" not in hay):
            continue
        matches=[w for w in classroom.list_coursework(str(c.get("id") or ""),include_drafts=True) if _norm(w.get("title"))==wanted]
        if len(matches)==1:
            course,work=c,matches[0]
            break
    if not course or not work:
        raise RuntimeError("C3_PROB_5B: no se encontró la actividad exacta.")
    cid=str(course.get("id") or ""); wid=str(work.get("id") or "")
    roster={str(s.get("userId") or ""):s for s in classroom.list_students(cid)}
    subs=classroom.list_submissions(cid,wid)
    by_name={}
    for sub in subs:
        st=roster.get(str(sub.get("userId") or "")) or {}
        name=_norm(st.get("name"))
        if name:
            by_name[name]=(st,sub)
    if set(by_name)!=set(GRADES):
        raise RuntimeError("C3_PROB_5B: cambió el roster de la actividad; se bloqueó el lote. "+json.dumps({"expected":sorted(GRADES),"observed":sorted(by_name)},ensure_ascii=False))

    for name,(st,sub) in by_name.items():
        att=((sub.get("assignmentSubmission") or {}).get("attachments") or [])
        if name=="MAYA CUEVA VALERA":
            if att:
                raise RuntimeError("C3_PROB_5B: Maya presentó evidencia nueva; requiere nueva revisión.")
        elif not att:
            raise RuntimeError(f"C3_PROB_5B: desapareció la evidencia de {name}; lote bloqueado.")

    api_results=[]
    for name,grade in GRADES.items():
        st,sub=by_name[name]
        sid=str(sub.get("id") or "")
        classroom.grade_submission(cid,wid,sid,grade=float(grade),return_to_student=False)
        api_results.append({"student":st.get("name"),"grade":grade,"submissionId":sid})
        print(f"C3_PROB_5B_API_GRADE: {st.get('name')} -> {grade}/20",flush=True)

    after=classroom.list_submissions(cid,wid)
    after_by_id={str(s.get("id") or ""):s for s in after}
    failures=[]
    for name,grade in GRADES.items():
        st,sub=by_name[name]; sid=str(sub.get("id") or "")
        row=after_by_id.get(sid) or {}
        dg=row.get("draftGrade"); ag=row.get("assignedGrade")
        if dg is None or ag is None or float(dg)!=float(grade) or float(ag)!=float(grade):
            failures.append({"student":st.get("name"),"expected":grade,"draftGrade":dg,"assignedGrade":ag})
    if failures:
        raise RuntimeError("C3_PROB_5B: falló verificación de notas Classroom: "+json.dumps(failures,ensure_ascii=False))
    print("C3_PROB_5B_API_VERIFIED: 26/26 notas cuantitativas confirmadas.",flush=True)

    jobs=[]
    for name,grade in GRADES.items():
        st,sub=by_name[name]
        comment=_comment(name,grade)
        sid=str(sub.get("id") or ""); surl=str(sub.get("alternateLink") or "")
        prior=[j for j in bridge_queue.matching(course_id=cid,course_work_id=wid,submission_id=sid,operation="post_private_comment")
               if str(getattr(j,"comment","") or "").strip()==comment and getattr(j,"status","") not in {"failed","cancelled"}]
        if prior:
            print(f"C3_PROB_5B_COMMENT_ALREADY_QUEUED: {st.get('name')} job={prior[0].id} status={prior[0].status}",flush=True)
            continue
        job=bridge_queue.enqueue(course_id=cid,course_work_id=wid,submission_id=sid,submission_url=surl,
                                 comment=comment,grade=None,return_after_comment=False,operation="post_private_comment")
        jobs.append({"student":st.get("name"),"grade":grade,"job":job.id,"guard":job.guard_job_id})
        print(f"C3_PROB_5B_COMMENT_ENQUEUED: {st.get('name')} grade={grade} job={job.id} guard={job.guard_job_id}",flush=True)

    print("C3_PROB_5B_READY="+json.dumps({"graded":len(api_results),"comment_jobs":len(jobs),"no_sieweb":True},ensure_ascii=False),flush=True)
    return {"queued":bool(jobs),"count":len(jobs),"graded":len(api_results),"work":work.get("title"),"jobs":jobs}
