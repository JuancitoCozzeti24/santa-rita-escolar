from __future__ import annotations
import json, sys, unicodedata
from typing import Any

def _norm(v: Any)->str:
    t=unicodedata.normalize('NFD',str(v or ''))
    t=''.join(ch for ch in t if unicodedata.category(ch)!='Mn')
    return ' '.join(t.upper().split())

def inspect(classroom: Any)->dict[str,Any]:
    main=sys.modules.get('__main__'); ns=vars(main) if main else {}; sieweb=ns.get('sieweb')
    if sieweb is None: raise RuntimeError('C3_PROB_SIEWEB_AUDIT: cliente no disponible')
    out=[]
    for section in ('5A','5B'):
        ctx=sieweb.resolve_class_context(section=section,period=2,course_code='05',id_ambito=525)
        extra={'idPeriodoAnt':int(ctx.get('idPeriodoAnt') or 0)}
        summary=sieweb.get_gradebook_summary(class_period_id=int(ctx.get('idClasePeriodo')),root_content_id=int(ctx.get('idContenido')),extra_params=extra)
        criteria=summary.get('criteria') or []
        rows=[]
        for c in criteria:
            text=' | '.join(str(c.get(k) or '') for k in ('desc','abreviatura','descripcion','programa'))
            n=_norm(text)
            if int(c.get('nivelEva') or 0) in (1,2) or 'PROBABIL' in n or 'INCERTIDUM' in n or ('C3' in n and int(c.get('nivelEva') or 0)==3):
                rows.append(c)
        out.append({'section':section,'context':ctx,'criteria':rows})
    print('C3_PROB_SIEWEB_AUDIT='+json.dumps(out,ensure_ascii=False,default=str),flush=True)
    return {'queued':False,'count':0,'work':'C3 probability SIEWEB audit'}
