from __future__ import annotations

from dataclasses import asdict, dataclass
from time import monotonic
from typing import Any

from playwright.sync_api import Page


@dataclass
class EditorComponentProbeResult:
    cdp_supported: bool
    editor_detected: bool
    component_objects_found: int
    component_summaries: list[dict[str, Any]]
    elapsed_ms: int
    escape_sent: bool
    editor_closed_after_escape: bool
    error: str = ""

    def as_dict(self) -> dict[str, Any]:
        return asdict(self)


TARGET_RE = r"nota|blur|keydown|keyup|keypress|input|change|guardar|save|actual|update|calif|registro|submit|enter|edicion|clickEdicion|clickAlumno|nivelEva|evaluacion|evaluación"


def _props(session, object_id: str, own: bool = True) -> dict[str, Any]:
    return session.send(
        "Runtime.getProperties",
        {
            "objectId": object_id,
            "ownProperties": own,
            "accessorPropertiesOnly": False,
            "generatePreview": True,
        },
    )


def _find_component_objects(session, handler_obj: dict[str, Any]) -> list[dict[str, Any]]:
    """Return closure variables named e/ctx/vm/context without recursively walking the world."""
    out: list[dict[str, Any]] = []
    oid = handler_obj.get("objectId")
    if not oid:
        return out
    try:
        data = _props(session, oid)
    except Exception:
        return out
    for internal in (data or {}).get("internalProperties", []):
        if str(internal.get("name") or "") != "[[Scopes]]":
            continue
        scopes = internal.get("value") or {}
        sid = scopes.get("objectId")
        if not sid:
            continue
        try:
            scope_list = _props(session, sid)
        except Exception:
            continue
        for scope_prop in (scope_list or {}).get("result", [])[:5]:
            scope_val = scope_prop.get("value") or {}
            scope_id = scope_val.get("objectId")
            if not scope_id:
                continue
            try:
                vars_data = _props(session, scope_id)
            except Exception:
                continue
            for var_prop in (vars_data or {}).get("result", [])[:50]:
                name = str(var_prop.get("name") or "")
                val = var_prop.get("value") or {}
                if name not in {"e", "ctx", "context", "vm"} or not val.get("objectId"):
                    continue
                out.append({
                    "scope": str(scope_prop.get("name") or "scope"),
                    "name": name,
                    "remote": val,
                })
    return out


def _summarize_component(session, remote_obj: dict[str, Any], label: str) -> dict[str, Any]:
    oid = remote_obj.get("objectId")
    if not oid:
        return {"label": label, "error": "no objectId"}

    # This function only READS property values and function sources. It never invokes the discovered handlers.
    fn = r'''function(){
      const rx = new RegExp("''' + TARGET_RE + r'''", "i");
      const items = [];
      const seen = new Set();
      let cur = this;
      let depth = 0;
      while (cur && depth < 5) {
        let keys = [];
        try { keys = Reflect.ownKeys(cur); } catch (e) { keys = []; }
        for (const key of keys) {
          const name = String(key);
          if (!rx.test(name)) continue;
          const dedup = depth + ":" + name;
          if (seen.has(dedup)) continue;
          seen.add(dedup);
          let v;
          let err = "";
          try { v = cur[key]; } catch (e) { err = String(e); }
          let text = "";
          let type = typeof v;
          if (!err) {
            try {
              if (type === "function") text = Function.prototype.toString.call(v).slice(0, 1600);
              else if (v === null) text = "null";
              else if (type === "object") text = Object.prototype.toString.call(v);
              else text = String(v).slice(0, 800);
            } catch (e) { text = "<unreadable>"; }
          }
          items.push({depth, name, type, text, error: err.slice(0,300)});
        }
        try { cur = Object.getPrototypeOf(cur); } catch (e) { cur = null; }
        depth++;
      }
      let tag = "";
      try { tag = Object.prototype.toString.call(this); } catch (e) {}
      return {tag, items};
    }'''
    try:
        resp = session.send(
            "Runtime.callFunctionOn",
            {
                "objectId": oid,
                "functionDeclaration": fn,
                "returnByValue": True,
                "silent": True,
            },
        )
        value = ((resp or {}).get("result") or {}).get("value") or {}
        return {"label": label, "tag": value.get("tag", ""), "items": value.get("items", [])[:80]}
    except Exception as exc:
        return {"label": label, "error": str(exc)[:600]}


def inspect_editor_component(page: Page, budget_seconds: float = 8.0) -> EditorComponentProbeResult:
    """Inspect the specific component object captured by the active grade editor.

    Read-only: does not type, dispatch input/change, press Enter, or invoke blur/keydown/save handlers.
    """
    session = None
    started = monotonic()
    try:
        active_tag = page.evaluate("() => { const e=document.activeElement; return e ? String(e.tagName||'').toLowerCase() : ''; }")
        if active_tag not in {"input", "textarea", "select"}:
            return EditorComponentProbeResult(False, False, 0, [], 0, False, False, "No active editor")

        session = page.context.new_cdp_session(page)
        session.send("Runtime.enable")
        remote = session.send("Runtime.evaluate", {"expression": "document.activeElement", "objectGroup": "sieroom-editor-component", "silent": True})
        active_id = ((remote or {}).get("result") or {}).get("objectId")
        if not active_id:
            return EditorComponentProbeResult(False, True, 0, [], 0, False, False, "No objectId")

        response = session.send("DOMDebugger.getEventListeners", {"objectId": active_id})
        wanted_types = {"input", "change", "blur", "keydown"}
        components: list[dict[str, Any]] = []
        seen_ids: set[str] = set()

        for item in (response or {}).get("listeners", []):
            if monotonic() - started > budget_seconds:
                break
            typ = str(item.get("type") or "")
            if typ not in wanted_types:
                continue
            handler = item.get("handler") or {}
            for comp in _find_component_objects(session, handler):
                oid = (comp.get("remote") or {}).get("objectId")
                if not oid or oid in seen_ids:
                    continue
                seen_ids.add(oid)
                components.append({"event": typ, **comp})

        summaries: list[dict[str, Any]] = []
        for comp in components[:8]:
            if monotonic() - started > budget_seconds:
                break
            summaries.append(
                _summarize_component(
                    session,
                    comp.get("remote") or {},
                    f"{comp.get('event')} -> {comp.get('scope')}.{comp.get('name')}",
                )
            )

        page.keyboard.press("Escape")
        page.wait_for_timeout(350)
        closed_tag = page.evaluate("() => { const e=document.activeElement; return e ? String(e.tagName||'').toLowerCase() : ''; }")
        closed = closed_tag not in {"input", "textarea", "select"}
        elapsed = int((monotonic() - started) * 1000)
        return EditorComponentProbeResult(True, True, len(components), summaries, elapsed, True, closed)
    except Exception as exc:
        try:
            page.keyboard.press("Escape")
        except Exception:
            pass
        elapsed = int((monotonic() - started) * 1000)
        return EditorComponentProbeResult(False, False, 0, [], elapsed, True, False, str(exc)[:1000])
    finally:
        if session is not None:
            try:
                session.send("Runtime.releaseObjectGroup", {"objectGroup": "sieroom-editor-component"})
            except Exception:
                pass
            try:
                session.detach()
            except Exception:
                pass
