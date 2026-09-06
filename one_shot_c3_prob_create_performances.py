from __future__ import annotations

import json, sys, unicodedata
from typing import Any

ABBR = "C3 - Prob. condicional"
CAPACITY_TO_PERFORMANCE = [
    (
        "Representa datos con gráficos y medidas estadísticas o probabilísticas",
        "Representa situaciones de probabilidad condicional identificando el evento condicionado y el espacio muestral restringido en problemas con bolas, cartas, estudiantes y dados.",
    ),
    (
        "Comunica la comprensión de los conceptos estadísticos y probabilísticos",
        "Explica el significado de la probabilidad condicional como la probabilidad de un evento bajo una condición dada y comunica el resultado mediante fracciones, decimales o porcentajes.",
    ),
    (
        "Usa estrategias y procedimientos para recopilar y procesar datos.",
        "Aplica estrategias de conteo y procedimientos de probabilidad condicional para determinar casos favorables y posibles dentro del espacio muestral condicionado y calcular la probabilidad solicitada.",
    ),
    (
        "Sustenta conclusiones o decisiones en base a la información obtenida.",
        "Sustenta la respuesta de una situación de probabilidad condicional justificando la selección del espacio muestral condicionado, los casos favorables y la coherencia del resultado obtenido.",
    ),
]


def _canon(v: Any) -> str:
    t=unicodedata.normalize('NFKD',str(v or ''))
    t=''.join(ch for ch in t if not unicodedata.combining(ch))
    return ' '.join(''.join(ch if ch.isalnum() else ' ' for ch in t.lower()).split())


def _find_capacity(summary: dict[str,Any], description: str) -> dict[str,Any]:
    wanted=_canon(description)
    matches=[]
    for c in summary.get('criteria') or []:
        if int(c.get('nivelEva') or 0)!=2:
            continue
        text=c.get('descripcion') or c.get('desc') or ''
        if _canon(text)==wanted:
            matches.append(c)
    if len(matches)!=1:
        raise RuntimeError(f"C3_PROB_CREATE: capacidad no única: {description!r}; matches={len(matches)}")
    return matches[0]


def execute(classroom: Any) -> dict[str,Any]:
    main=sys.modules.get('__main__'); ns=vars(main) if main else {}; sieweb=ns.get('sieweb')
    if sieweb is None:
        raise RuntimeError('C3_PROB_CREATE: cliente SIEWeb no disponible')

    contexts=[]
    for section in ('5A','5B'):
        ctx=sieweb.resolve_class_context(section=section,period=2,course_code='05',id_ambito=525)
        contexts.append((section,ctx))

    # Deduplicar contextos físicos: actualmente 5A y 5B comparten la misma clase/periodo
    # en CIEWeb. Si en otro despliegue fueran distintos, se crea una alta verificada en cada uno.
    unique={}
    for section,ctx in contexts:
        key=(int(ctx.get('idClase')),int(ctx.get('idClasePeriodo')),int(ctx.get('idContenido')),int(ctx.get('idAmbito') or 525))
        unique.setdefault(key,{'ctx':ctx,'sections':[]})['sections'].append(section)

    writes=[]
    for key,group in unique.items():
        ctx=group['ctx']; sections=group['sections']
        extra={'idPeriodoAnt':int(ctx.get('idPeriodoAnt') or 0)}
        before=sieweb.get_gradebook_summary(
            class_period_id=int(ctx.get('idClasePeriodo')),
            root_content_id=int(ctx.get('idContenido')),
            extra_params=extra,
        )
        expected=[]; records=[]; parent_map=[]
        for cap_desc, perf_desc in CAPACITY_TO_PERFORMANCE:
            cap=_find_capacity(before,cap_desc)
            parent_id=int(cap.get('id'))
            parent_map.append({'capacity':cap_desc,'parent_id':parent_id,'performance':perf_desc})
            expected.append({'description':perf_desc,'parent_id':parent_id,'level':3})
            records.append({'ABREVIATURA':ABBR,'PESO':1,'SUMATIVO':0,'EXCLUIR':0})

        result=sieweb.upsert_criteria_verified(
            class_id=int(ctx.get('idClase')),
            class_period_id=int(ctx.get('idClasePeriodo')),
            root_content_id=int(ctx.get('idContenido')),
            id_ambito=int(ctx.get('idAmbito') or 525),
            records=records,
            replica={},
            expected=expected,
            extra_params=extra,
            verification_attempts=3,
        )
        writes.append({'sections':sections,'context':key,'parents':parent_map,'result':result})

    # Verificación explícita desde ambas secciones solicitadas.
    verification=[]
    for section,ctx in contexts:
        extra={'idPeriodoAnt':int(ctx.get('idPeriodoAnt') or 0)}
        summary=sieweb.get_gradebook_summary(
            class_period_id=int(ctx.get('idClasePeriodo')),
            root_content_id=int(ctx.get('idContenido')),
            extra_params=extra,
        )
        checks=[]
        for cap_desc, perf_desc in CAPACITY_TO_PERFORMANCE:
            cap=_find_capacity(summary,cap_desc)
            matches=sieweb.find_exact_criterion(summary,description=perf_desc,parent_id=int(cap.get('id')),level=3)
            checks.append({'capacity':cap_desc,'performance':perf_desc,'count':len(matches),'ids':[m.get('id') for m in matches],'abbr':[m.get('abreviatura') or m.get('desc') for m in matches]})
        ok=all(x['count']==1 for x in checks)
        verification.append({'section':section,'ok':ok,'checks':checks})
        if not ok:
            raise RuntimeError('C3_PROB_CREATE: verificación falló en '+section+': '+json.dumps(checks,ensure_ascii=False,default=str))

    print('C3_PROB_PERFORMANCES_CREATED='+json.dumps({'writes':writes,'verification':verification},ensure_ascii=False,default=str),flush=True)
    return {'queued':False,'count':0,'work':'C3 probability performances created','sections':['5A','5B'],'performance_count':4}
