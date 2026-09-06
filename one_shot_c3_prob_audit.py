from __future__ import annotations

import json, unicodedata
from typing import Any

TARGET = "C3 EVALUACIÓN PROBABILIDAD CONDICIONAL"

def _norm(v: Any) -> str:
    t = unicodedata.normalize("NFD", str(v or ""))
    t = "".join(ch for ch in t if unicodedata.category(ch) != "Mn")
    return " ".join(t.upper().replace(":", " ").split())

def _attachments(sub: dict[str, Any]) -> list[dict[str, Any]]:
    out=[]
    for item in ((sub.get("assignmentSubmission") or {}).get("attachments") or []):
        if not isinstance(item,dict): continue
        df=item.get("driveFile") or {}
        if isinstance(df,dict) and df.get("id"):
            out.append({"id":df.get("id"),"title":df.get("title"),"alternateLink":df.get("alternateLink")})
    return out

def inspect(classroom: Any) -> dict[str, Any]:
    found=[]
    wanted=_norm(TARGET)
    for c in classroom.list_courses(active_only=True):
        hay=_norm(f"{c.get('name') or ''} {c.get('section') or ''}")
        if "MATE 5TO" not in hay: continue
        section = "5A" if ("5TO - A" in hay or "5TO A" in hay) else ("5B" if ("5TO - B" in hay or "5TO B" in hay) else "")
        if not section: continue
        works=classroom.list_coursework(str(c.get("id") or ""), include_drafts=True)
        matches=[]
        for w in works:
            nt=_norm(w.get("title"))
            if nt == wanted or ("C3" in nt and "EVALUACION" in nt and "PROBABILIDAD" in nt and "CONDICIONAL" in nt):
                matches.append(w)
        for w in matches:
            cid=str(c.get("id") or ""); wid=str(w.get("id") or "")
            roster={str(s.get("userId") or ""):s for s in classroom.list_students(cid)}
            rows=[]
            for sub in classroom.list_submissions(cid,wid):
                at=_attachments(sub)
                if at:
                    st=roster.get(str(sub.get("userId") or "")) or {}
                    rows.append({"name":st.get("name"),"state":sub.get("state"),"grade":sub.get("assignedGrade") if sub.get("assignedGrade") is not None else sub.get("draftGrade"),"attachments":at})
            found.append({"section":section,"course":c.get("name"),"courseId":cid,"title":w.get("title"),"courseWorkId":wid,"description":w.get("description"),"maxPoints":w.get("maxPoints"),"materials":w.get("materials"),"evidence_samples":rows[:8],"evidence_count":len(rows)})
    print("C3_PROB_AUDIT="+json.dumps(found,ensure_ascii=False,default=str),flush=True)
    if not found:
        raise RuntimeError("C3_PROB_AUDIT: no se encontró la actividad en 5A/5B")
    return {"queued":False,"count":0,"work":"C3 conditional probability audit","found":len(found)}
