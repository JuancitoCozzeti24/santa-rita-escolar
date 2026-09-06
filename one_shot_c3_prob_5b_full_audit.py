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
        if not isinstance(item,dict):
            continue
        df=item.get("driveFile") or {}
        if isinstance(df,dict) and df.get("id"):
            out.append({"id":str(df.get("id")),"title":df.get("title"),"alternateLink":df.get("alternateLink")})
    return out

def inspect(classroom: Any) -> dict[str, Any]:
    wanted=_norm(TARGET)
    course=work=None
    for c in classroom.list_courses(active_only=True):
        hay=_norm(f"{c.get('name') or ''} {c.get('section') or ''}")
        if "MATE 5TO" not in hay or ("5TO - B" not in hay and "5TO B" not in hay):
            continue
        matches=[w for w in classroom.list_coursework(str(c.get("id") or ""),include_drafts=True)
                 if _norm(w.get("title"))==wanted]
        if len(matches)==1:
            course,work=c,matches[0]
            break
    if not course or not work:
        raise RuntimeError("C3_PROB_5B_AUDIT: no se encontró de forma única la actividad exacta.")
    cid=str(course.get("id") or ""); wid=str(work.get("id") or "")
    roster={str(s.get("userId") or ""):s for s in classroom.list_students(cid)}
    rows=[]
    for sub in classroom.list_submissions(cid,wid):
        st=roster.get(str(sub.get("userId") or "")) or {}
        rows.append({
            "name":st.get("name"),
            "email":st.get("email"),
            "userId":sub.get("userId"),
            "submissionId":sub.get("id"),
            "state":sub.get("state"),
            "draftGrade":sub.get("draftGrade"),
            "assignedGrade":sub.get("assignedGrade"),
            "late":sub.get("late"),
            "alternateLink":sub.get("alternateLink"),
            "attachments":_attachments(sub),
        })
    rows.sort(key=lambda r:_norm(r.get("name")))
    payload={"course":course.get("name"),"courseId":cid,"work":work.get("title"),"courseWorkId":wid,"maxPoints":work.get("maxPoints"),"description":work.get("description"),"rows":rows,"count":len(rows)}
    print("C3_PROB_5B_FULL_AUDIT="+json.dumps(payload,ensure_ascii=False,default=str),flush=True)
    return {"queued":False,"count":0,"work":work.get("title"),"students":len(rows)}
