from __future__ import annotations

from dataclasses import asdict, dataclass
from time import monotonic
from typing import Any

from playwright.sync_api import Page


@dataclass
class EditorComponentV2Result:
    cdp_supported: bool
    editor_detected: bool
    assign_function_found: bool
    component_found: bool
    component_label: str
    component_description: str
    properties: list[dict[str, Any]]
    elapsed_ms: int
    escape_sent: bool
    editor_closed_after_escape: bool
    error: str = ""

    def as_dict(self) -> dict[str, Any]:
        return asdict(self)


TARGET_WORDS = (
    "nota", "blur", "keydown", "keyup", "keypress", "input", "change", "guardar",
    "save", "actual", "update", "calif", "registro", "submit", "enter", "edicion",
    "clickedicion", "clickalumno", "niveleva", "evaluacion", "evaluación", "grabar",
    "persist", "axios", "fetch", "http", "post", "put", "patch",
)


def _interesting(name: str, desc: str = "") -> bool:
    text = f"{name} {desc}".casefold()
    return any(word.casefold() in text for word in TARGET_WORDS)


def _get_props(session, object_id: str, own: bool = True) -> dict[str, Any]:
    return session.send(
        "Runtime.getProperties",
        {
            "objectId": object_id,
            "ownProperties": own,
            "accessorPropertiesOnly": False,
            "generatePreview": True,
        },
    )


def _get_assign_function(session, active_id: str) -> dict[str, Any] | None:
    """Read the input's Symbol(_assign) function without invoking application callbacks."""
    try:
        resp = session.send(
            "Runtime.callFunctionOn",
            {
                "objectId": active_id,
                "functionDeclaration": "function(){const s=Object.getOwnPropertySymbols(this).find(x=>String(x).includes('_assign'));return s?this[s]:null;}",
                "returnByValue": False,
                "silent": True,
            },
        )
        obj = (resp or {}).get("result") or {}
        if obj.get("type") == "function" and obj.get("objectId"):
            return obj
    except Exception:
        pass
    return None


def _component_from_function_scope(session, fn_obj: dict[str, Any]) -> tuple[dict[str, Any] | None, str]:
    """Find the non-DOM object captured by function(a){return e.nota=a}."""
    oid = fn_obj.get("objectId")
    if not oid:
        return None, ""
    try:
        data = _get_props(session, oid)
    except Exception:
        return None, ""

    candidates: list[tuple[dict[str, Any], str]] = []
    for internal in (data or {}).get("internalProperties", []):
        if str(internal.get("name") or "") != "[[Scopes]]":
            continue
        scopes = internal.get("value") or {}
        sid = scopes.get("objectId")
        if not sid:
            continue
        try:
            scope_list = _get_props(session, sid)
        except Exception:
            continue
        for scope_prop in (scope_list or {}).get("result", [])[:8]:
            scope_val = scope_prop.get("value") or {}
            scope_id = scope_val.get("objectId")
            if not scope_id:
                continue
            scope_name = str(scope_prop.get("name") or "scope")
            try:
                vars_data = _get_props(session, scope_id)
            except Exception:
                continue
            for var_prop in (vars_data or {}).get("result", [])[:80]:
                name = str(var_prop.get("name") or "")
                val = var_prop.get("value") or {}
                if not val.get("objectId"):
                    continue
                desc = str(val.get("description") or "")
                cls = str(val.get("className") or "")
                # The assignment function source specifically references e.nota.
                # Prefer a captured variable named e that is not a DOM node/window.
                if name == "e":
                    low = f"{desc} {cls}".casefold()
                    if "html" not in low and "window" not in low and "document" not in low and "node" not in low:
                        return val, f"{scope_name}.{name}"
                    candidates.append((val, f"{scope_name}.{name}"))
                elif name in {"vm", "ctx", "context", "self"}:
                    candidates.append((val, f"{scope_name}.{name}"))

    # Last resort: return the first non-obvious DOM candidate for diagnostics.
    for val, label in candidates:
        low = f"{val.get('description','')} {val.get('className','')}".casefold()
        if "htmlinputelement" not in low and "window" not in low:
            return val, label
    return None, ""


def _record_properties(session, root_obj: dict[str, Any], label: str, max_depth: int = 3) -> list[dict[str, Any]]:
    """Read matching data/functions on object + prototypes without invoking getters."""
    out: list[dict[str, Any]] = []
    current = root_obj
    seen_ids: set[str] = set()

    for depth in range(max_depth + 1):
        oid = current.get("objectId")
        if not oid or oid in seen_ids:
            break
        seen_ids.add(oid)
        try:
            data = _get_props(session, oid, own=True)
        except Exception as exc:
            out.append({"depth": depth, "name": "<getProperties>", "type": "error", "description": str(exc)[:500]})
            break

        for prop in (data or {}).get("result", [])[:250]:
            name = str(prop.get("name") or "")
            value = prop.get("value") or {}
            desc = str(value.get("description") or value.get("value") or "")
            getter = prop.get("get") or {}
            setter = prop.get("set") or {}
            getter_desc = str(getter.get("description") or "")
            setter_desc = str(setter.get("description") or "")
            if not (_interesting(name, desc) or _interesting(name, getter_desc) or _interesting(name, setter_desc)):
                continue
            out.append(
                {
                    "depth": depth,
                    "name": name,
                    "type": str(value.get("type") or ("accessor" if getter or setter else "")),
                    "class_name": str(value.get("className") or ""),
                    "description": desc[:2200],
                    "getter": getter_desc[:2200],
                    "setter": setter_desc[:2200],
                }
            )

        # Get prototype as a remote object; no application getter/method is invoked.
        try:
            proto = session.send(
                "Runtime.callFunctionOn",
                {
                    "objectId": oid,
                    "functionDeclaration": "function(){return Object.getPrototypeOf(this);}",
                    "returnByValue": False,
                    "silent": True,
                },
            )
            current = (proto or {}).get("result") or {}
        except Exception:
            break

    return out


def inspect_editor_component_v2(page: Page, budget_seconds: float = 8.0) -> EditorComponentV2Result:
    """Trace input Symbol(_assign) -> captured e component. Read-only."""
    session = None
    started = monotonic()
    try:
        active_tag = page.evaluate("() => {const e=document.activeElement;return e?String(e.tagName||'').toLowerCase():'';}")
        if active_tag not in {"input", "textarea", "select"}:
            return EditorComponentV2Result(False, False, False, False, "", "", [], 0, False, False, "No active editor")

        session = page.context.new_cdp_session(page)
        session.send("Runtime.enable")
        remote = session.send(
            "Runtime.evaluate",
            {"expression": "document.activeElement", "objectGroup": "sieroom-editor-component-v2", "silent": True},
        )
        active = (remote or {}).get("result") or {}
        active_id = active.get("objectId")
        if not active_id:
            return EditorComponentV2Result(False, True, False, False, "", "", [], 0, False, False, "No active objectId")

        assign_fn = _get_assign_function(session, active_id)
        assign_found = bool(assign_fn)
        component = None
        component_label = ""
        if assign_fn:
            component, component_label = _component_from_function_scope(session, assign_fn)

        properties: list[dict[str, Any]] = []
        component_desc = ""
        if component:
            component_desc = str(component.get("description") or component.get("className") or "")[:800]
            if monotonic() - started <= budget_seconds:
                properties = _record_properties(session, component, component_label, max_depth=3)

        page.keyboard.press("Escape")
        page.wait_for_timeout(350)
        closed_tag = page.evaluate("() => {const e=document.activeElement;return e?String(e.tagName||'').toLowerCase():'';}")
        closed = closed_tag not in {"input", "textarea", "select"}
        elapsed = int((monotonic() - started) * 1000)
        return EditorComponentV2Result(
            True,
            True,
            assign_found,
            component is not None,
            component_label,
            component_desc,
            properties[:120],
            elapsed,
            True,
            closed,
        )
    except Exception as exc:
        try:
            page.keyboard.press("Escape")
        except Exception:
            pass
        return EditorComponentV2Result(False, False, False, False, "", "", [], int((monotonic()-started)*1000), True, False, str(exc)[:1200])
    finally:
        if session is not None:
            try:
                session.send("Runtime.releaseObjectGroup", {"objectGroup": "sieroom-editor-component-v2"})
            except Exception:
                pass
            try:
                session.detach()
            except Exception:
                pass
