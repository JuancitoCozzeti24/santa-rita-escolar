from __future__ import annotations

from dataclasses import asdict, dataclass
from typing import Any

from playwright.sync_api import Page


@dataclass
class EditorClosureProbeResult:
    cdp_supported: bool
    editor_detected: bool
    listeners_inspected: int
    closure_functions_found: int
    findings: list[dict[str, Any]]
    escape_sent: bool
    editor_closed_after_escape: bool
    error: str = ""

    def as_dict(self) -> dict[str, Any]:
        return asdict(self)


KEYWORDS = (
    "blur", "keydown", "input", "change", "click", "clickedicion", "clickalumno",
    "guardar", "save", "actualizar", "update", "nota", "calificacion", "calificación",
    "registrar", "enviar", "submit", "enter", "escape", "axios", "$http", "fetch",
)


def _desc(obj: dict[str, Any]) -> str:
    return str(obj.get("description") or obj.get("value") or "")[:2200]


def _interesting_text(text: str) -> bool:
    low = text.casefold()
    return any(k.casefold() in low for k in KEYWORDS)


def _remote_properties(session, object_id: str) -> dict[str, Any]:
    return session.send(
        "Runtime.getProperties",
        {
            "objectId": object_id,
            "ownProperties": True,
            "accessorPropertiesOnly": False,
            "generatePreview": True,
        },
    )


def _inspect_object(
    session,
    remote_obj: dict[str, Any],
    *,
    path: str,
    depth: int,
    seen: set[str],
    findings: list[dict[str, Any]],
) -> None:
    if depth > 4:
        return
    object_id = remote_obj.get("objectId")
    if not object_id or object_id in seen:
        return
    seen.add(object_id)

    try:
        props = _remote_properties(session, object_id)
    except Exception:
        return

    description = _desc(remote_obj)
    if remote_obj.get("type") == "function" and _interesting_text(description):
        findings.append({
            "path": path,
            "type": "function",
            "description": description,
        })

    for prop in (props or {}).get("result", []):
        name = str(prop.get("name", ""))
        val = prop.get("value") or {}
        text = _desc(val)
        joined = f"{name} {text}"
        if _interesting_text(joined):
            findings.append({
                "path": f"{path}.{name}",
                "type": str(val.get("type", "")),
                "class_name": str(val.get("className", "")),
                "description": text,
            })
        if val.get("objectId") and (
            depth < 2
            or _interesting_text(joined)
            or name in {"value", "handler", "fns", "invoker", "original", "originalHandler", "e", "ctx", "context", "$options"}
        ):
            _inspect_object(
                session,
                val,
                path=f"{path}.{name}",
                depth=depth + 1,
                seen=seen,
                findings=findings,
            )

    # The crucial part: inspect the function's [[Scopes]] internal property.
    for internal in (props or {}).get("internalProperties", []):
        name = str(internal.get("name", ""))
        val = internal.get("value") or {}
        if name != "[[Scopes]]" or not val.get("objectId"):
            continue
        try:
            scope_list = _remote_properties(session, val["objectId"])
        except Exception:
            continue
        for scope_prop in (scope_list or {}).get("result", [])[:12]:
            scope_val = scope_prop.get("value") or {}
            if not scope_val.get("objectId"):
                continue
            scope_name = str(scope_prop.get("name", "scope"))
            try:
                scope_vars = _remote_properties(session, scope_val["objectId"])
            except Exception:
                continue
            for var_prop in (scope_vars or {}).get("result", [])[:80]:
                var_name = str(var_prop.get("name", ""))
                var_val = var_prop.get("value") or {}
                var_text = _desc(var_val)
                joined = f"{var_name} {var_text}"
                if _interesting_text(joined):
                    findings.append({
                        "path": f"{path}.[[Scopes]].{scope_name}.{var_name}",
                        "type": str(var_val.get("type", "")),
                        "class_name": str(var_val.get("className", "")),
                        "description": var_text,
                    })
                if var_val.get("objectId") and (var_name in {"e", "ctx", "context", "vm", "self"} or _interesting_text(joined)):
                    _inspect_object(
                        session,
                        var_val,
                        path=f"{path}.[[Scopes]].{scope_name}.{var_name}",
                        depth=depth + 1,
                        seen=seen,
                        findings=findings,
                    )


def inspect_editor_closures(page: Page) -> EditorClosureProbeResult:
    """Inspect closure-scoped callback functions behind the active editor listeners.

    This function never types, never dispatches input/change manually, and never presses
    Enter. It only reads CDP object metadata and closes the editor with Escape.
    """
    session = None
    try:
        active_tag = page.evaluate(
            "() => { const e=document.activeElement; return e ? String(e.tagName||'').toLowerCase() : ''; }"
        )
        if active_tag not in {"input", "textarea", "select"}:
            return EditorClosureProbeResult(False, False, 0, 0, [], False, False, "No active editor")

        session = page.context.new_cdp_session(page)
        session.send("Runtime.enable")
        remote = session.send(
            "Runtime.evaluate",
            {"expression": "document.activeElement", "objectGroup": "sieroom-editor-closure", "silent": True},
        )
        active_id = ((remote or {}).get("result") or {}).get("objectId")
        if not active_id:
            return EditorClosureProbeResult(False, True, 0, 0, [], False, False, "No objectId")

        interesting_types = {"blur", "keydown", "input", "change", "click"}
        findings: list[dict[str, Any]] = []
        seen: set[str] = set()
        listeners_count = 0
        current_id = active_id

        for depth in range(4):
            response = session.send("DOMDebugger.getEventListeners", {"objectId": current_id})
            for idx, item in enumerate((response or {}).get("listeners", [])):
                typ = str(item.get("type", ""))
                if typ not in interesting_types:
                    continue
                listeners_count += 1
                for key in ("handler", "originalHandler"):
                    remote_handler = item.get(key) or {}
                    if not remote_handler.get("objectId"):
                        continue
                    _inspect_object(
                        session,
                        remote_handler,
                        path=f"{typ}[depth={depth}].{key}",
                        depth=0,
                        seen=seen,
                        findings=findings,
                    )
            parent = session.send(
                "Runtime.callFunctionOn",
                {
                    "objectId": current_id,
                    "functionDeclaration": "function(){return this&&this.parentElement?this.parentElement:null;}",
                    "returnByValue": False,
                    "silent": True,
                },
            )
            parent_id = ((parent or {}).get("result") or {}).get("objectId")
            if not parent_id:
                break
            current_id = parent_id

        # Deduplicate noisy framework paths/descriptions.
        unique: list[dict[str, Any]] = []
        keys: set[tuple[str, str]] = set()
        for item in findings:
            key = (str(item.get("path", "")), str(item.get("description", ""))[:500])
            if key in keys:
                continue
            keys.add(key)
            unique.append(item)

        page.keyboard.press("Escape")
        page.wait_for_timeout(450)
        closed_tag = page.evaluate(
            "() => { const e=document.activeElement; return e ? String(e.tagName||'').toLowerCase() : ''; }"
        )
        closed = closed_tag not in {"input", "textarea", "select"}

        function_count = sum(1 for x in unique if x.get("type") == "function")
        return EditorClosureProbeResult(
            cdp_supported=True,
            editor_detected=True,
            listeners_inspected=listeners_count,
            closure_functions_found=function_count,
            findings=unique[:120],
            escape_sent=True,
            editor_closed_after_escape=closed,
        )
    except Exception as exc:
        try:
            page.keyboard.press("Escape")
        except Exception:
            pass
        return EditorClosureProbeResult(False, False, 0, 0, [], True, False, str(exc)[:1200])
    finally:
        if session is not None:
            try:
                session.send("Runtime.releaseObjectGroup", {"objectGroup": "sieroom-editor-closure"})
            except Exception:
                pass
            try:
                session.detach()
            except Exception:
                pass
