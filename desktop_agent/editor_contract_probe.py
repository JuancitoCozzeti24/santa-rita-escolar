from __future__ import annotations

from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Any

from playwright.sync_api import Page


@dataclass
class EditorContractResult:
    ok: bool
    student_code: str
    student_name: str
    student_order: str
    column_index: int
    column_label: str
    row_selection_confirmed: bool
    editor_detected: bool
    active_element: dict[str, Any]
    ancestors: list[dict[str, Any]]
    nearby_controls: list[dict[str, Any]]
    event_listeners: list[dict[str, Any]]
    network_requests: list[dict[str, Any]]
    escape_sent: bool
    editor_closed_after_escape: bool
    grade_text_unchanged: bool
    error: str = ""

    def as_dict(self) -> dict[str, Any]:
        return asdict(self)


def _clean_text(value: str) -> str:
    return " ".join(str(value or "").replace("\xa0", " ").split())


def _selected_student_line(page: Page) -> str:
    return page.evaluate(
        r"""
        () => {
          const text = String(document.body?.innerText || '');
          const lines = text.split(/\r?\n/).map(x => x.replace(/\s+/g,' ').trim()).filter(Boolean);
          return lines.find(x => /^Estudiante\s*:/i.test(x)) || '';
        }
        """
    )


def _cell_text(page: Page, x: float, y: float) -> str:
    return page.evaluate(
        "([x,y]) => { const e=document.elementFromPoint(x,y); return e ? String(e.innerText || e.textContent || '').trim().slice(0,300) : ''; }",
        [x, y],
    )


def _active_contract(page: Page) -> tuple[dict[str, Any], list[dict[str, Any]], list[dict[str, Any]]]:
    payload = page.evaluate(
        r"""
        () => {
          const clean=(v,n=500)=>String(v??'').replace(/\s+/g,' ').trim().slice(0,n);
          const visible=(el)=>{ if(!el||!(el instanceof Element)) return false; const s=getComputedStyle(el),r=el.getBoundingClientRect(); return s.display!=='none'&&s.visibility!=='hidden'&&r.width>0&&r.height>0; };
          const safeValue=(el)=>{ try { const t=String(el.getAttribute?.('type')||'').toLowerCase(); if(t==='password'||t==='hidden') return ''; return ('value' in el)?clean(el.value,200):''; } catch(_){ return ''; } };
          const describe=(el)=>{
            if(!el) return {};
            const r=el.getBoundingClientRect?.()||{x:0,y:0,width:0,height:0};
            const attrs={};
            for(const name of ['id','class','name','type','role','tabindex','maxlength','minlength','pattern','inputmode','autocomplete','aria-label','aria-expanded','aria-controls','placeholder','contenteditable','readonly','disabled']){
              const v=el.getAttribute?.(name); if(v!==null&&v!==undefined&&String(v)!=='') attrs[name]=clean(v,240);
            }
            for(const a of Array.from(el.attributes||[])) if(a.name.startsWith('data-')) attrs[a.name]=clean(a.value,240);
            return {tag:clean(el.tagName||'',50).toLowerCase(), text:clean(el.innerText||el.textContent,500), value:safeValue(el), attrs, rect:{x:r.x||0,y:r.y||0,width:r.width||0,height:r.height||0}};
          };
          const active=document.activeElement;
          const activeInfo=describe(active);
          const ancestors=[];
          let cur=active?.parentElement;
          for(let depth=1;cur&&cur!==document.body&&depth<=6;depth++,cur=cur.parentElement){
            const info=describe(cur); info.depth=depth; ancestors.push(info);
          }
          const nearby=[];
          const root=(active?.closest?.('.q-popup-edit,.q-menu,.q-dialog,.q-card,.q-field')||active?.parentElement||document.body);
          for(const el of root.querySelectorAll?.('button,[role="button"],input,select,textarea,[role="option"],[role="combobox"]')||[]){
            if(!visible(el)) continue;
            const info=describe(el);
            if(info.attrs?.type==='password'||info.attrs?.type==='hidden') continue;
            nearby.push(info);
            if(nearby.length>=40) break;
          }
          return {active:activeInfo, ancestors, nearby};
        }
        """
    )
    return payload.get("active", {}), payload.get("ancestors", []), payload.get("nearby", [])


def _event_listeners_for_active(page: Page) -> list[dict[str, Any]]:
    session = None
    try:
        session = page.context.new_cdp_session(page)
        script_urls: dict[str, str] = {}
        def on_script(parsed: dict[str, Any]) -> None:
            sid = str(parsed.get("scriptId", ""))
            if sid:
                script_urls[sid] = str(parsed.get("url", ""))
        session.on("Debugger.scriptParsed", on_script)
        session.send("Debugger.enable")
        session.send("Runtime.enable")
        remote = session.send("Runtime.evaluate", {"expression":"document.activeElement","objectGroup":"sieroom-editor-contract","silent":True})
        object_id = ((remote or {}).get("result") or {}).get("objectId")
        if not object_id:
            return []
        interesting={"keydown","keyup","keypress","input","change","blur","focus","click","mousedown","pointerdown"}
        out=[]
        current_id=object_id
        for depth in range(5):
            response=session.send("DOMDebugger.getEventListeners", {"objectId":current_id})
            for item in (response or {}).get("listeners", []):
                typ=str(item.get("type", ""))
                if typ not in interesting:
                    continue
                handler=item.get("handler") or {}
                desc=str(handler.get("description", ""))[:1200]
                sid=str(item.get("scriptId", ""))
                out.append({"type":typ,"depth":depth,"line_number":item.get("lineNumber"),"column_number":item.get("columnNumber"),"script_id":sid,"source_url":script_urls.get(sid, ""),"handler_description":desc})
            parent=session.send("Runtime.callFunctionOn", {"objectId":current_id,"functionDeclaration":"function(){return this&&this.parentElement?this.parentElement:null;}","returnByValue":False,"silent":True})
            parent_id=((parent or {}).get("result") or {}).get("objectId")
            if not parent_id: break
            current_id=parent_id
        return out[:80]
    except Exception as exc:
        return [{"error":str(exc)[:700]}]
    finally:
        if session is not None:
            try: session.send("Runtime.releaseObjectGroup", {"objectGroup":"sieroom-editor-contract"})
            except Exception: pass
            try: session.detach()
            except Exception: pass


def probe_editor_contract(page: Page, cell_map: Any, student_order: int, column_number: int, evidence_dir: Path) -> EditorContractResult:
    try:
        student=next((s for s in cell_map.students if int(str(s.get("order") or 0))==int(student_order)),None)
        if not student:
            return EditorContractResult(False,"","",str(student_order),column_number-1,"",False,False,{},[],[],[],[],False,False,True,"Student order not found")
        cell=next((c for c in (student.get("grade_cells") or []) if int(c.get("column_index",-1))==column_number-1),None)
        if not cell:
            return EditorContractResult(False,str(student.get("code","")),str(student.get("name","")),str(student.get("order","")),column_number-1,"",False,False,{},[],[],[],[],False,False,True,"Mapped grade cell not found")
        column=next((c for c in cell_map.columns if int(c.get("index",-1))==column_number-1),{})
        label=str(column.get("header") or "")
        rr=student.get("row_rect") or {}
        row_x=float(rr.get("x",0))+max(10.0,float(rr.get("width",0))*0.72)
        row_y=float(rr.get("y",0))+float(rr.get("height",0))/2
        cell_x=float(cell.get("x",0))+float(cell.get("width",0))/2
        cell_y=float(cell.get("y",0))+float(cell.get("height",0))/2

        page.mouse.click(row_x,row_y)
        page.wait_for_timeout(550)
        selected=_selected_student_line(page)
        target_name=_clean_text(str(student.get("name",""))).casefold()
        row_confirmed=bool(target_name and target_name in _clean_text(selected).casefold())

        before_text=_cell_text(page,cell_x,cell_y)
        requests=[]
        def on_request(request) -> None:
            method=str(request.method or "GET").upper()
            if method in {"POST","PUT","PATCH","DELETE"}:
                requests.append({"method":method,"url":str(request.url)[:600],"resource_type":str(request.resource_type)[:80]})
        page.on("request",on_request)
        try:
            page.mouse.click(cell_x,cell_y)
            page.wait_for_timeout(650)
            active,ancestors,nearby=_active_contract(page)
            listeners=_event_listeners_for_active(page)
            editor_detected=str(active.get("tag","")) in {"input","textarea","select"} or str((active.get("attrs") or {}).get("contenteditable","")).lower()=="true" or str((active.get("attrs") or {}).get("role","")) in {"combobox","textbox","listbox"}
            page.keyboard.press("Escape")
            page.wait_for_timeout(450)
            after_text=_cell_text(page,cell_x,cell_y)
            closed_active,_,_=_active_contract(page)
            closed_tag=str(closed_active.get("tag",""))
            closed_role=str((closed_active.get("attrs") or {}).get("role",""))
            closed_ce=str((closed_active.get("attrs") or {}).get("contenteditable","")).lower()
            editor_closed=not (closed_tag in {"input","textarea","select"} or closed_role in {"combobox","textbox","listbox"} or closed_ce=="true")
            return EditorContractResult(True,str(student.get("code","")),str(student.get("name","")),str(student.get("order","")),column_number-1,label,row_confirmed,editor_detected,active,ancestors[:12],nearby[:40],listeners[:80],requests[:50],True,editor_closed,before_text==after_text,"")
        finally:
            try: page.remove_listener("request",on_request)
            except Exception: pass
    except Exception as exc:
        return EditorContractResult(False,"","",str(student_order),column_number-1,"",False,False,{},[],[],[],[],False,False,True,str(exc)[:1000])
