from __future__ import annotations

import re
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


def _notice_key(item: dict[str, Any]) -> tuple[str, str, str]:
    return (
        str(item.get("type") or ""),
        _norm(item.get("title")),
        _norm(item.get("text") or item.get("due")),
    )


def _notices_payload(grade: str, section: str = "", limit: int = 20) -> dict[str, Any]:
    wanted_grade = _grade_value(grade)
    wanted_section = _section_value(section)
    if not wanted_grade:
        raise ValueError("grade debe ser 2 o 5")
    if str(section or "").strip() and not wanted_section:
        raise ValueError("section debe ser A o B")

    limit = max(1, min(int(limit or 20), 40))
    courses = [
        course
        for course in brain._client.list_courses(active_only=True)
        if _mobile_course_matches(course, wanted_grade)
        and _section_matches(course, wanted_grade, wanted_section)
    ]

    items: list[dict[str, Any]] = []
    sources: list[dict[str, str]] = []
    for course in courses:
        course_id = str(course.get("id") or "")
        course_name = str(course.get("name") or course_id)
        if not course_id:
            continue
        sources.append({"course_id": course_id, "course_name": course_name})

        try:
            announcements = brain._client.list_announcements(
                course_id, include_drafts=False
            )[:limit]
        except Exception:
            announcements = []
        for announcement in announcements:
            text = str(announcement.get("text") or "").strip()
            if not text:
                continue
            items.append(
                {
                    "id": str(announcement.get("id") or ""),
                    "type": "announcement",
                    "title": "Aviso de Classroom",
                    "text": text,
                    "course_id": course_id,
                    "course_name": course_name,
                    "updated_at": announcement.get("updateTime")
                    or announcement.get("creationTime"),
                    "link": announcement.get("alternateLink"),
                }
            )

        try:
            coursework = brain._client.list_coursework(
                course_id, include_drafts=False
            )[:limit]
        except Exception:
            coursework = []
        for work in coursework:
            items.append(
                {
                    "id": str(work.get("id") or ""),
                    "type": "coursework",
                    "title": str(work.get("title") or "Actividad de Classroom"),
                    "text": str(work.get("description") or "").strip()[:1200],
                    "course_id": course_id,
                    "course_name": course_name,
                    "updated_at": work.get("updateTime") or work.get("creationTime"),
                    "due": brain._format_due(work),
                    "max_points": work.get("maxPoints"),
                    "work_type": work.get("workType"),
                    "link": work.get("alternateLink"),
                }
            )

    # A/B suelen compartir contenido. Si se consulta solo por grado, evita duplicados visuales.
    deduped: list[dict[str, Any]] = []
    seen: set[tuple[str, str, str]] = set()
    for item in sorted(items, key=lambda row: str(row.get("updated_at") or ""), reverse=True):
        key = _notice_key(item)
        if key in seen:
            continue
        seen.add(key)
        deduped.append(item)
        if len(deduped) >= limit:
            break

    return {
        "ok": True,
        "api_version": API_VERSION,
        "grade": wanted_grade,
        "section": wanted_section or None,
        "count": len(deduped),
        "items": deduped,
        "sources": sources,
        "updated_at": brain._now_lima().isoformat(),
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
            "knowledge_base": True,
            "bitacora_private_context": True,
            "push_notifications": False,
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
