from __future__ import annotations

from dataclasses import asdict, dataclass
from typing import Any

from playwright.sync_api import Page


@dataclass
class VueEventProbe:
    cdp_supported: bool
    inspected_columns: int
    handlers_found: int
    framework_markers: list[str]
    samples: list[dict[str, Any]]
    error: str = ""

    def as_dict(self) -> dict[str, Any]:
        return asdict(self)


def _safe_value(prop: dict[str, Any]) -> str:
    value = prop.get("value") or {}
    if "value" in value and isinstance(value.get("value"), (str, int, float, bool)):
        return str(value.get("value"))[:500]
    return str(value.get("description") or value.get("className") or value.get("type") or "")[:500]


def _function_details(session, remote_obj: dict[str, Any], depth: int = 0) -> dict[str, Any]:
    result: dict[str, Any] = {
        "type": remote_obj.get("type", ""),
        "class_name": remote_obj.get("className", ""),
        "description": str(remote_obj.get("description", ""))[:1600],
    }
    object_id = remote_obj.get("objectId")
    if not object_id or depth > 2:
        return result

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
        result["properties_error"] = str(exc)[:500]
        return result

    useful_names = {
        "name", "length", "fns", "value", "handler", "invoker",
        "_wrapper", "_withTask", "_vei", "__weh", "attached",
    }
    properties: list[dict[str, Any]] = []
    nested: list[dict[str, Any]] = []
    for prop in (props or {}).get("result", []):
        name = str(prop.get("name", ""))
        value = prop.get("value") or {}
        if name in useful_names or name.startswith("_") or "fn" in name.lower() or "handler" in name.lower():
            properties.append({
                "name": name,
                "value": _safe_value(prop),
                "type": value.get("type", ""),
                "class_name": value.get("className", ""),
            })
        if name in {"fns", "value", "handler", "invoker"} and value.get("objectId"):
            nested.append({
                "property": name,
                "details": _function_details(session, value, depth + 1),
            })
    result["properties"] = properties[:50]
    result["nested"] = nested[:12]
    return result


def inspect_vue_event_handlers(page: Page, grade_cell_probe: Any) -> VueEventProbe:
    """Inspect Vue/Quasar listener wrappers without dispatching any event.

    The probe reads Chromium listener objects and common Vue markers. It does not
    click, focus, type, change DOM values, or submit requests.
    """
    signatures = list(getattr(grade_cell_probe, "cell_signatures", []) or [])
    if not signatures:
        return VueEventProbe(False, 0, 0, [], [], "No grade-cell signatures available")

    session = None
    try:
        session = page.context.new_cdp_session(page)
        session.send("Runtime.enable")
        session.send("Debugger.enable")

        samples: list[dict[str, Any]] = []
        framework_markers: set[str] = set()
        seen_columns: set[int] = set()
        handler_count = 0

        for sig in signatures:
            column_index = int(sig.get("column_index", -1))
            if column_index in seen_columns:
                continue
            seen_columns.add(column_index)

            rect = sig.get("rect") or {}
            x = float(rect.get("x", 0)) + float(rect.get("width", 0)) / 2
            y = float(rect.get("y", 0)) + float(rect.get("height", 0)) / 2
            remote = session.send(
                "Runtime.evaluate",
                {
                    "expression": f"document.elementFromPoint({x!r}, {y!r})",
                    "objectGroup": "sieroom-vue-readonly",
                    "silent": True,
                },
            )
            object_id = ((remote or {}).get("result") or {}).get("objectId")
            if not object_id:
                continue

            chain: list[dict[str, Any]] = []
            current_id = object_id
            for depth in range(7):
                own_names: list[str] = []
                try:
                    props = session.send(
                        "Runtime.getProperties",
                        {"objectId": current_id, "ownProperties": True, "generatePreview": False},
                    )
                    for prop in (props or {}).get("result", []):
                        name = str(prop.get("name", ""))
                        if name.startswith("__vue") or name in {"_vei", "__vnode", "_vnode", "__vue__"}:
                            own_names.append(name)
                            framework_markers.add(name)
                except Exception:
                    pass

                response = session.send("DOMDebugger.getEventListeners", {"objectId": current_id})
                listeners: list[dict[str, Any]] = []
                for item in (response or {}).get("listeners", []):
                    if str(item.get("type", "")) != "click":
                        continue
                    handler = item.get("handler") or {}
                    original = item.get("originalHandler") or {}
                    record = {
                        "depth": depth,
                        "script_id": str(item.get("scriptId", "")),
                        "line_number": item.get("lineNumber"),
                        "column_number": item.get("columnNumber"),
                        "use_capture": bool(item.get("useCapture", False)),
                        "handler": _function_details(session, handler),
                        "original_handler": _function_details(session, original) if original else None,
                    }
                    listeners.append(record)
                    handler_count += 1

                if listeners or own_names:
                    chain.append({
                        "depth": depth,
                        "framework_properties": own_names,
                        "click_listeners": listeners,
                    })

                parent = session.send(
                    "Runtime.callFunctionOn",
                    {
                        "objectId": current_id,
                        "functionDeclaration": "function(){ return this && this.parentElement ? this.parentElement : null; }",
                        "returnByValue": False,
                        "silent": True,
                    },
                )
                parent_id = ((parent or {}).get("result") or {}).get("objectId")
                if not parent_id:
                    break
                current_id = parent_id

            samples.append({
                "column_index": column_index,
                "student_code": sig.get("sample_student_code", ""),
                "student_name": sig.get("sample_student_name", ""),
                "chain": chain,
            })

        try:
            session.send("Runtime.releaseObjectGroup", {"objectGroup": "sieroom-vue-readonly"})
        except Exception:
            pass

        return VueEventProbe(
            cdp_supported=True,
            inspected_columns=len(seen_columns),
            handlers_found=handler_count,
            framework_markers=sorted(framework_markers),
            samples=samples,
        )
    except Exception as exc:
        return VueEventProbe(False, 0, 0, [], [], str(exc)[:1000])
    finally:
        if session is not None:
            try:
                session.detach()
            except Exception:
                pass
