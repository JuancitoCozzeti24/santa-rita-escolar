from __future__ import annotations

from dataclasses import asdict, dataclass
from typing import Any

from playwright.sync_api import Page


@dataclass
class EventListenerProbe:
    cdp_supported: bool
    listener_count: int
    listener_types: list[str]
    source_urls: list[str]
    samples: list[dict[str, Any]]
    error: str = ""

    def as_dict(self) -> dict[str, Any]:
        return asdict(self)


def inspect_grade_cell_event_listeners(page: Page, grade_cell_probe: Any) -> EventListenerProbe:
    """Read Chromium event-listener metadata for representative grade cells.

    This function is intentionally read-only: it never clicks, dispatches events,
    changes DOM values, or submits network requests.
    """

    signatures = list(getattr(grade_cell_probe, "cell_signatures", []) or [])
    if not signatures:
        return EventListenerProbe(False, 0, [], [], [], "No grade-cell signatures available")

    session = None
    try:
        session = page.context.new_cdp_session(page)
        script_urls: dict[str, str] = {}

        def on_script(parsed: dict[str, Any]) -> None:
            script_id = str(parsed.get("scriptId", ""))
            if script_id:
                script_urls[script_id] = str(parsed.get("url", ""))

        session.on("Debugger.scriptParsed", on_script)
        session.send("Debugger.enable")
        session.send("Runtime.enable")

        interesting = {
            "click", "dblclick", "mousedown", "mouseup",
            "pointerdown", "pointerup", "keydown", "keyup",
            "input", "change", "focus", "blur",
        }

        samples: list[dict[str, Any]] = []
        seen_columns: set[int] = set()
        all_types: set[str] = set()
        all_urls: set[str] = set()
        total = 0

        for sig in signatures:
            column_index = int(sig.get("column_index", -1))
            if column_index in seen_columns:
                continue
            seen_columns.add(column_index)

            rect = sig.get("rect") or {}
            x = float(rect.get("x", 0)) + float(rect.get("width", 0)) / 2
            y = float(rect.get("y", 0)) + float(rect.get("height", 0)) / 2
            expression = f"document.elementFromPoint({x!r}, {y!r})"
            remote = session.send(
                "Runtime.evaluate",
                {
                    "expression": expression,
                    "objectGroup": "sieroom-readonly-listener-probe",
                    "includeCommandLineAPI": False,
                    "silent": True,
                },
            )
            object_id = ((remote or {}).get("result") or {}).get("objectId")
            if not object_id:
                samples.append({
                    "column_index": column_index,
                    "student_code": sig.get("sample_student_code", ""),
                    "listeners": [],
                    "note": "No DOM object resolved at the mapped cell center",
                })
                continue

            chain: list[dict[str, Any]] = []
            current_id = object_id
            for depth in range(6):
                response = session.send(
                    "DOMDebugger.getEventListeners",
                    {"objectId": current_id},
                )
                listeners = []
                for item in (response or {}).get("listeners", []):
                    event_type = str(item.get("type", ""))
                    if event_type not in interesting:
                        continue
                    script_id = str(item.get("scriptId", ""))
                    source_url = script_urls.get(script_id, "")
                    record = {
                        "type": event_type,
                        "depth": depth,
                        "use_capture": bool(item.get("useCapture", False)),
                        "passive": bool(item.get("passive", False)),
                        "once": bool(item.get("once", False)),
                        "script_id": script_id,
                        "line_number": item.get("lineNumber"),
                        "column_number": item.get("columnNumber"),
                        "source_url": source_url,
                    }
                    listeners.append(record)
                    total += 1
                    all_types.add(event_type)
                    if source_url:
                        all_urls.add(source_url)

                if listeners:
                    chain.extend(listeners)

                parent = session.send(
                    "Runtime.callFunctionOn",
                    {
                        "objectId": current_id,
                        "functionDeclaration": "function(){ return this && this.parentElement ? this.parentElement : null; }",
                        "returnByValue": False,
                        "silent": True,
                    },
                )
                parent_result = (parent or {}).get("result") or {}
                parent_id = parent_result.get("objectId")
                if not parent_id:
                    break
                current_id = parent_id

            samples.append({
                "column_index": column_index,
                "student_code": sig.get("sample_student_code", ""),
                "student_name": sig.get("sample_student_name", ""),
                "class_name": sig.get("class_name", ""),
                "listeners": chain,
            })

        try:
            session.send("Runtime.releaseObjectGroup", {"objectGroup": "sieroom-readonly-listener-probe"})
        except Exception:
            pass
        try:
            session.send("Debugger.disable")
        except Exception:
            pass

        return EventListenerProbe(
            cdp_supported=True,
            listener_count=total,
            listener_types=sorted(all_types),
            source_urls=sorted(all_urls),
            samples=samples,
        )
    except Exception as exc:
        return EventListenerProbe(
            cdp_supported=False,
            listener_count=0,
            listener_types=[],
            source_urls=[],
            samples=[],
            error=str(exc)[:800],
        )
    finally:
        if session is not None:
            try:
                session.detach()
            except Exception:
                pass
