from __future__ import annotations

import json
import re
from pathlib import Path
from typing import Any

from starlette.requests import Request
from starlette.responses import JSONResponse

import profe_johnny_brain as brain


API_VERSION = "2026-09-10-mobile-v2"


def _norm(value: Any) -> str:
    return brain._norm(str(value or ""))


def _grade_value(value: Any) -> str:
    raw = str(value or "").strip()
    return raw[:1] if raw[:1] in {"2", "5"} else ""


def _section_value(value: Any) -> str:
    raw = str(value or "").strip().upper()
    return raw[:1] if raw[:1] in {"A", "B"} else ""


def _mobile_course_matches(course: dict[str, Any], grade: str) -> bool:
    """Reconoce los Classroom reales MATE 2DO/5TO, no solo 'matem...'."""
    wanted = _grade_value(grade)
    if not wanted:
        return False

    name = _norm(course.get("name"))
    hay = _norm(
        " ".join(
            str(course.get(key) or "")
            for key in ("name", "section", "descriptionHeading", "description", "subject")
        )
    )

    # Los cursos reales del profesor se llaman MATE 2DO - A/B y MATE 5TO - A/B.
    if not re.search(r"(^| )mate($| )", name) and "matem" not in name:
        return False

    markers = (
        ("2do", "2 do", "2 secundaria", "segundo")
        if wanted == "2"
        else ("5to", "5 to", "5 secundaria", "quinto")
    )
    return any(_norm(marker) in hay for marker in markers) or re.search(
        rf"(^|\D){wanted}(\D|$)", hay
    ) is not None


def _section_matches(course: dict[str, Any], grade: str, section: str) -> bool:
    wanted_grade = _grade_value(grade)
    wanted_section = _section_value(section)
    if not wanted_section:
        return True
    compact = re.sub(r"[^0-9a-z]", "", _norm(course.get("name")))
    return (
        f"{wanted_grade}do{wanted_section.lower()}" in compact
        or f"{wanted_grade}to{wanted_section.lower()}" in compact
    )


def _safe_int(value: Any, default: int = 20) -> int:
    try:
        return int(value)
    except Exception:
        return default


NOTICES_FILE = Path(__file__).with_name("profe_johnny_notices.json")


def _load_manual_notices() -> dict[str, Any]:
    try:
        raw = json.loads(NOTICES_FILE.read_text(encoding="utf-8"))
        if not isinstance(raw, dict):
            raise ValueError("notices_root_not_object")
        items = raw.get("items")
        if not isinstance(items, list):
            items = []
        return {
            "version": int(raw.get("version") or 1),
            "updated_at": str(raw.get("updated_at") or ""),
            "items": items,
        }
    except FileNotFoundError:
        return {"version": 1, "updated_at": "", "items": []}
    except Exception:
        return {"version": 1, "updated_at": "", "items": []}


def _notices_payload(grade: str, section: str = "", limit: int = 50) -> dict[str, Any]:
    wanted_grade = _grade_value(grade)
    wanted_section = _section_value(section)
    if not wanted_grade:
        raise ValueError("grade debe ser 2 o 5")
    if str(section or "").strip() and not wanted_section:
        raise ValueError("section debe ser A o B")

    limit = max(1, min(int(limit or 50), 100))
    store = _load_manual_notices()

    filtered: list[dict[str, Any]] = []
    for raw in store.get("items") or []:
        if not isinstance(raw, dict):
            continue
        item_grade = _grade_value(raw.get("grade"))
        item_section = _section_value(raw.get("section"))
        active = bool(raw.get("active", True))
        if not active or item_grade != wanted_grade:
            continue
        if wanted_section and item_section != wanted_section:
            continue
        filtered.append({
            "id": str(raw.get("id") or ""),
            "type": str(raw.get("type") or "activity"),
            "grade": item_grade,
            "section": item_section,
            "title": str(raw.get("title") or "").strip(),
            "description": str(raw.get("description") or "").strip(),
            "due_date": str(raw.get("due_date") or "").strip(),
            "due_time": str(raw.get("due_time") or "").strip(),
            "status": str(raw.get("status") or "vigente").strip(),
            "topic": str(raw.get("topic") or "").strip(),
            "note": str(raw.get("note") or "").strip(),
            "created_at": str(raw.get("created_at") or "").strip(),
            "updated_at": str(raw.get("updated_at") or "").strip(),
        })

    def sort_key(item: dict[str, Any]) -> tuple[str, str, str]:
        date_text = str(item.get("due_date") or "9999-99-99")
        time_text = str(item.get("due_time") or "99:99")
        return (date_text, time_text, str(item.get("title") or ""))

    filtered.sort(key=sort_key)
    return {
        "ok": True,
        "api_version": API_VERSION,
        "grade": wanted_grade,
        "section": wanted_section or None,
        "count": min(len(filtered), limit),
        "items": filtered[:limit],
        "updated_at": str(store.get("updated_at") or brain._now_lima().isoformat()),
        "source": "profe_johnny_section_itinerary",
        "personalized": False,
    }


def _bootstrap_payload() -> dict[str, Any]:
    return {
        "ok": True,
        "api_version": API_VERSION,
        "app": "PROFE JOHNNY APP",
        "mode": "family_student_read_only",
        "grades": [
            {"grade": "2", "label": "2.º año", "sections": ["A", "B"]},
            {"grade": "5", "label": "5.º año", "sections": ["A", "B"]},
        ],
        "features": {
            "chat": True,
            "classroom_live_context": True,
            "notices": True,
            "notices_dynamic_server": True,
            "notices_manual_section_itinerary": True,
            "push_notifications": False,
            "knowledge_base": True,
            "bitacora_private_context": True,
            "verified_family_login": False,
        },
        "endpoints": {
            "status": "/profe-johnny/v1/status",
            "bootstrap": "/profe-johnny/v1/bootstrap",
            "chat": "/profe-johnny/v1/chat",
            "notices": "/profe-johnny/v1/notices?grade=2",
        },
        "updated_at": brain._now_lima().isoformat(),
    }


def install(mcp: Any) -> None:
    if getattr(mcp, "_profe_johnny_mobile_v2_installed", False):
        return

    # Corrige de forma global el filtro que alimenta al chat existente.
    brain._course_matches = _mobile_course_matches

    @mcp.custom_route("/profe-johnny/v1/bootstrap", methods=["GET"])
    async def profe_johnny_bootstrap(_request: Request):
        return JSONResponse(_bootstrap_payload())

    @mcp.custom_route("/profe-johnny/v1/notices", methods=["GET"])
    async def profe_johnny_notices(request: Request):
        grade = str(request.query_params.get("grade") or "").strip()
        section = str(request.query_params.get("section") or "").strip()
        limit = _safe_int(request.query_params.get("limit"), 20)
        try:
            return JSONResponse(_notices_payload(grade, section, limit))
        except ValueError as exc:
            return JSONResponse({"ok": False, "error": str(exc)}, status_code=400)
        except Exception as exc:
            return JSONResponse(
                {"ok": False, "error": f"{type(exc).__name__}: {exc}"},
                status_code=500,
            )

    setattr(mcp, "_profe_johnny_mobile_v2_installed", True)
    print(
        "PROFE JOHNNY APP V2: filtro Classroom corregido; /bootstrap y /notices cargados.",
        flush=True,
    )
