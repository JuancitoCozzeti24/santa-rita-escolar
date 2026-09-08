from __future__ import annotations

from dataclasses import asdict, dataclass
from time import monotonic
from typing import Any

from playwright.sync_api import Page


@dataclass
class FastClosureProbeResult:
    cdp_supported: bool
    editor_detected: bool
    listeners_inspected: int
    event_types: list[str]
    findings: list[dict[str, Any]]
    elapsed_ms: int
    escape_sent: bool
    editor_closed_after_escape: bool
    stopped_by_budget: bool = False
    error: str = ""

    def as_dict(self) -> dict[str, Any]:
        return asdict(self)


KEYWORDS = (
    "blur", "keydown", "input", "change", "click", "clickedicion", "clickalumno",
    "guardar", "save", "actualizar", "update", "nota", "calificacion", "calificación",
    "registrar", "enviar", "submit", "enter", "escape", "axios", "$http", "fetch",
)


def _interesting(text: str) -> bool:
    low = text.casefold()
    return any(k.casefold() in low for k in KEYWORDS)


def _desc(value: dict[str, Any]) -> str:
    return str(value.get("description") or value.get("value") or "")[:1200]


def _props(session, object_id: str) -> dict[str, Any]:
    return session.send(
        "Runtime.getProperties",
        {
            "objectId": object_id,
            "ownProperties": True,
            "accessorPropertiesOnly": False,
            "generatePreview": True,
        },
    )


def _shallow_object(session, remote_obj: dict[str, Any], path: str, findings: list[dict[str, Any]], max_props: int = 40) -> None:
    object_id = remote_obj.get("objectId")
    if not object_id:
        return
    try:
        data = _props(session, object_id)
    except Exception as exc:
        findings.append({"path": path, "type": "error", "description": str(exc)[:400]})
        return

    for prop in (data or {}).get("result", [])[:max_props]:
        name = str(prop.get("name", ""))
        val = prop.get("value") or {}
        text = _desc(val)
        joined = f"{name} {text}"
        if _interesting(joined) or name in {"blur", "keydown", "input", "change", "click", "clickEdicion", "clickAlumno"}:
            findings.append({
                "path": f"{path}.{name}",
                "type": str(val.get("type", "")),
                "class_name": str(val.get("className", "")),
                "description": text,
            })

    # Inspect only the function's scope list and only shallow variables. No recursion.
    for internal in (data or {}).get("internalProperties", []):
        if str(internal.get("name", "")) != "[[Scopes]]":
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
            scope_name = str(scope_prop.get("name", "scope"))
            try:
                vars_data = _props(session, scope_id)
            except Exception:
                continue
            for var_prop in (vars_data or {}).get("result", [])[:30]:
                var_name = str(var_prop.get("name", ""))
                var_val = var_prop.get("value") or {}
                text = _desc(var_val)
                joined = f"{var_name} {text}"
                if _interesting(joined) or var_name in {"e", "ctx", "context", "vm", "self"}:
                    findings.append({
                        "path": f"{path}.[[Scopes]].{scope_name}.{var_name}",
                        "type": str(var_val.get("type", "")),
                        "class_name": str(var_val.get("className", "")),
                        "description": text,
                    })
                    # For likely component/context objects, inspect one shallow level only.
                    if var_name in {"e", "ctx", "context", "vm", "self"} and var_val.get("objectId"):
                        _shallow_component(session, var_val, f"{path}.[[Scopes]].{scope_name}.{var_name}", findings)


def _shallow_component(session, remote_obj: dict[str, Any], path: str, findings: list[dict[str, Any]]) -> None:
    object_id = remote_obj.get("objectId")
    if not object_id:
        return
    try:
        data = _props(session, object_id)
    except Exception:
        return
    wanted = {"blur", "keydown", "input", "change", "click", "clickEdicion", "clickAlumno", "guardar", "save", "actualizar", "update"}
    for prop in (data or {}).get("result", [])[:80]:
        name = str(prop.get("name", ""))
        val = prop.get("value") or {}
        text = _desc(val)
        if name in wanted or _interesting(f"{name} {text}"):
            findings.append({
                "path": f"{path}.{name}",
                "type": str(val.get("type", "")),
                "class_name": str(val.get("className", "")),
                "description": text,
            })


def inspect_editor_closures_fast(page: Page, budget_seconds: float = 12.0) -> FastClosureProbeResult:
    """Bounded, shallow CDP inspection. Never types, never presses Enter, never saves."""
    session = None
    started = monotonic()
    stopped = False
    try:
        active_tag = page.evaluate("() => { const e=document.activeElement; return e ? String(e.tagName||'').toLowerCase() : ''; }")
        if active_tag not in {"input", "textarea", "select"}:
            return FastClosureProbeResult(False, False, 0, [], [], 0, False, False, False, "No active editor")

        session = page.context.new_cdp_session(page)
        session.send("Runtime.enable")
        remote = session.send("Runtime.evaluate", {"expression": "document.activeElement", "objectGroup": "sieroom-editor-fast", "silent": True})
        active_id = ((remote or {}).get("result") or {}).get("objectId")
        if not active_id:
            return FastClosureProbeResult(False, True, 0, [], [], 0, False, False, False, "No objectId")

        findings: list[dict[str, Any]] = []
        types: set[str] = set()
        inspected = 0
        current_id = active_id
        priority = {"blur", "keydown", "input", "change", "click"}

        for depth in range(3):
            if monotonic() - started > budget_seconds:
                stopped = True
                break
            response = session.send("DOMDebugger.getEventListeners", {"objectId": current_id})
            for item in (response or {}).get("listeners", []):
                typ = str(item.get("type", ""))
                if typ not in priority:
                    continue
                if monotonic() - started > budget_seconds:
                    stopped = True
                    break
                inspected += 1
                types.add(typ)
                # Only inspect the actual handler. originalHandler duplicates framework noise.
                handler = item.get("handler") or {}
                if handler.get("objectId"):
                    _shallow_object(session, handler, f"{typ}[depth={depth}].handler", findings)
                # One listener per type per depth is enough for this probe.
                if inspected >= 8:
                    break
            if stopped or inspected >= 8:
                break
            parent = session.send("Runtime.callFunctionOn", {
                "objectId": current_id,
                "functionDeclaration": "function(){return this&&this.parentElement?this.parentElement:null;}",
                "returnByValue": False,
                "silent": True,
            })
            parent_id = ((parent or {}).get("result") or {}).get("objectId")
            if not parent_id:
                break
            current_id = parent_id

        # Deduplicate before output.
        unique: list[dict[str, Any]] = []
        seen: set[tuple[str, str]] = set()
        for item in findings:
            key = (str(item.get("path", "")), str(item.get("description", ""))[:300])
            if key not in seen:
                seen.add(key)
                unique.append(item)

        page.keyboard.press("Escape")
        page.wait_for_timeout(350)
        closed_tag = page.evaluate("() => { const e=document.activeElement; return e ? String(e.tagName||'').toLowerCase() : ''; }")
        closed = closed_tag not in {"input", "textarea", "select"}
        elapsed = int((monotonic() - started) * 1000)
        return FastClosureProbeResult(True, True, inspected, sorted(types), unique[:80], elapsed, True, closed, stopped)
    except Exception as exc:
        try:
            page.keyboard.press("Escape")
        except Exception:
            pass
        elapsed = int((monotonic() - started) * 1000)
        return FastClosureProbeResult(False, False, 0, [], [], elapsed, True, False, stopped, str(exc)[:1000])
    finally:
        if session is not None:
            try:
                session.send("Runtime.releaseObjectGroup", {"objectGroup": "sieroom-editor-fast"})
            except Exception:
                pass
            try:
                session.detach()
            except Exception:
                pass
