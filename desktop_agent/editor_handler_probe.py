from __future__ import annotations

from dataclasses import asdict, dataclass
from typing import Any

from playwright.sync_api import Page


@dataclass
class EditorHandlerProbeResult:
    cdp_supported: bool
    editor_detected: bool
    handlers_found: int
    event_types: list[str]
    callback_hints: list[str]
    listeners: list[dict[str, Any]]
    escape_sent: bool
    editor_closed_after_escape: bool
    error: str = ""

    def as_dict(self) -> dict[str, Any]:
        return asdict(self)


def _details(session, remote_obj: dict[str, Any], depth: int = 0) -> dict[str, Any]:
    out: dict[str, Any] = {
        "type": remote_obj.get("type", ""),
        "class_name": remote_obj.get("className", ""),
        "description": str(remote_obj.get("description", ""))[:2400],
    }
    object_id = remote_obj.get("objectId")
    if not object_id or depth > 2:
        return out
    try:
        props = session.send(
            "Runtime.getProperties",
            {
                "objectId": object_id,
                "ownProperties": True,
                "accessorPropertiesOnly": False,
                "generatePreview": True,
            },
        )
    except Exception as exc:
        out["properties_error"] = str(exc)[:500]
        return out

    interesting = {
        "value", "fns", "handler", "invoker", "original", "originalHandler",
        "name", "length", "attached", "_wrapper", "_withTask", "_vei", "__weh",
    }
    values: list[dict[str, Any]] = []
    nested: list[dict[str, Any]] = []
    for prop in (props or {}).get("result", []):
        name = str(prop.get("name", ""))
        val = prop.get("value") or {}
        if name in interesting or name.startswith("_") or "fn" in name.lower() or "handler" in name.lower():
            values.append({
                "name": name,
                "type": val.get("type", ""),
                "class_name": val.get("className", ""),
                "description": str(val.get("description") or val.get("value") or "")[:1800],
            })
        if name in {"value", "fns", "handler", "invoker", "original", "originalHandler"} and val.get("objectId"):
            nested.append({"property": name, "details": _details(session, val, depth + 1)})
    out["properties"] = values[:60]
    out["nested"] = nested[:18]
    return out


def _collect_text(details: dict[str, Any] | None) -> str:
    if not details:
        return ""
    chunks = [str(details.get("description") or "")]
    for p in details.get("properties") or []:
        chunks.append(str(p.get("description") or ""))
    for nested in details.get("nested") or []:
        chunks.append(_collect_text(nested.get("details") or {}))
    return "\n".join(chunks)


def _callback_hints(text: str) -> list[str]:
    low = text.casefold()
    candidates = [
        "clickEdicion", "clickAlumno", "guardar", "save", "actualizar", "update",
        "editar", "edicion", "blur", "keydown", "keyup", "enter", "escape",
        "cambiar", "change", "input", "nota", "calificacion", "calificación",
        "registrar", "registro", "enviar", "submit", "axios", "$http", "fetch",
    ]
    found: list[str] = []
    for item in candidates:
        if item.casefold() in low and item not in found:
            found.append(item)
    return found


def inspect_editor_handlers(page: Page) -> EditorHandlerProbeResult:
    """Inspect the already-open grade editor's input listeners without typing or submitting."""
    session = None
    try:
        active = page.evaluate("() => { const e=document.activeElement; return e ? String(e.tagName||'').toLowerCase() : ''; }")
        if active not in {"input", "textarea", "select"}:
            return EditorHandlerProbeResult(False, False, 0, [], [], [], False, False, "No active editor input")

        session = page.context.new_cdp_session(page)
        script_urls: dict[str, str] = {}

        def on_script(parsed: dict[str, Any]) -> None:
            sid = str(parsed.get("scriptId", ""))
            if sid:
                script_urls[sid] = str(parsed.get("url", ""))

        session.on("Debugger.scriptParsed", on_script)
        session.send("Debugger.enable")
        session.send("Runtime.enable")
        remote = session.send(
            "Runtime.evaluate",
            {"expression": "document.activeElement", "objectGroup": "sieroom-editor-handlers", "silent": True},
        )
        object_id = ((remote or {}).get("result") or {}).get("objectId")
        if not object_id:
            return EditorHandlerProbeResult(False, True, 0, [], [], [], False, False, "No objectId for active editor")

        interesting = {"input", "change", "blur", "keydown", "keyup", "keypress", "click", "focus"}
        listeners: list[dict[str, Any]] = []
        types: set[str] = set()
        hints: set[str] = set()
        current_id = object_id
        for depth in range(5):
            response = session.send("DOMDebugger.getEventListeners", {"objectId": current_id})
            for item in (response or {}).get("listeners", []):
                typ = str(item.get("type", ""))
                if typ not in interesting:
                    continue
                handler = item.get("handler") or {}
                original = item.get("originalHandler") or {}
                h_details = _details(session, handler)
                o_details = _details(session, original) if original else None
                combined = _collect_text(h_details) + "\n" + _collect_text(o_details)
                for hint in _callback_hints(combined):
                    hints.add(hint)
                sid = str(item.get("scriptId", ""))
                listeners.append({
                    "type": typ,
                    "depth": depth,
                    "line_number": item.get("lineNumber"),
                    "column_number": item.get("columnNumber"),
                    "script_id": sid,
                    "source_url": script_urls.get(sid, ""),
                    "handler": h_details,
                    "original_handler": o_details,
                })
                types.add(typ)
            parent = session.send(
                "Runtime.callFunctionOn",
                {
                    "objectId": current_id,
                    "functionDeclaration": "function(){ return this&&this.parentElement?this.parentElement:null; }",
                    "returnByValue": False,
                    "silent": True,
                },
            )
            parent_id = ((parent or {}).get("result") or {}).get("objectId")
            if not parent_id:
                break
            current_id = parent_id

        page.keyboard.press("Escape")
        page.wait_for_timeout(450)
        closed_tag = page.evaluate("() => { const e=document.activeElement; return e ? String(e.tagName||'').toLowerCase() : ''; }")
        closed = closed_tag not in {"input", "textarea", "select"}

        return EditorHandlerProbeResult(
            cdp_supported=True,
            editor_detected=True,
            handlers_found=len(listeners),
            event_types=sorted(types),
            callback_hints=sorted(hints),
            listeners=listeners[:100],
            escape_sent=True,
            editor_closed_after_escape=closed,
        )
    except Exception as exc:
        try:
            page.keyboard.press("Escape")
        except Exception:
            pass
        return EditorHandlerProbeResult(False, False, 0, [], [], [], True, False, str(exc)[:1000])
    finally:
        if session is not None:
            try:
                session.send("Runtime.releaseObjectGroup", {"objectGroup": "sieroom-editor-handlers"})
            except Exception:
                pass
            try:
                session.detach()
            except Exception:
                pass
