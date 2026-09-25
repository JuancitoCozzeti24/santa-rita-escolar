from __future__ import annotations

import base64
import calendar
import hashlib
import hmac
import json
import os
import re
import time
import unicodedata
from datetime import date, datetime
from typing import Any
from urllib.parse import quote

from starlette.requests import Request
from starlette.responses import JSONResponse

import battle_accounts as ba
import profe_johnny_brain as brain
from bitacora import DEFAULT_SPREADSHEET_ID, _google_request

API_VERSION = "2026-09-10-identity-v3"
TOKEN_SECRET = os.getenv("PROFE_JOHNNY_TOKEN_SECRET", "").strip()
OWNER_SECRET_HASH = os.getenv("PROFE_JOHNNY_OWNER_SECRET_HASH", "").strip()
FAMILY_SHEET_ID = os.getenv("PROFE_JOHNNY_FAMILY_SHEET_ID", DEFAULT_SPREADSHEET_ID).strip()
FAMILY_TAB = "PROFE_APP_FAMILIAS"
TOKEN_TTL = 30 * 86400
DEFAULT_CLASSROOM_START = date(2026, 9, 9)
TRIMESTER_RANGES = {
    1: (date(2026, 3, 2), date(2026, 6, 1)),
    2: (date(2026, 6, 2), date(2026, 9, 8)),
    3: (date(2026, 9, 9), None),
}
MONTHS_ES = {
    "ENERO": 1, "FEBRERO": 2, "MARZO": 3, "ABRIL": 4,
    "MAYO": 5, "JUNIO": 6, "JULIO": 7, "AGOSTO": 8,
    "SEPTIEMBRE": 9, "SETIEMBRE": 9, "OCTUBRE": 10,
    "NOVIEMBRE": 11, "DICIEMBRE": 12,
}


def _iso_date(value: Any) -> date | None:
    text = str(value or "").strip()
    if not text:
        return None
    try:
        return datetime.fromisoformat(text.replace("Z", "+00:00")).date()
    except Exception:
        return None


def _coursework_date(work: dict[str, Any]) -> date | None:
    due = work.get("dueDate") or {}
    try:
        if due.get("year") and due.get("month") and due.get("day"):
            return date(int(due["year"]), int(due["month"]), int(due["day"]))
    except Exception:
        pass
    return _iso_date(work.get("creationTime")) or _iso_date(work.get("updateTime"))


def _period_from_message(message: str) -> tuple[date | None, date | None, str, bool]:
    raw = str(message or "")
    q = _norm(raw)

    match = re.search(r"\b(\d{1,2})[/-](\d{1,2})(?:[/-](\d{2,4}))?\b", raw)
    if match:
        day = int(match.group(1))
        month = int(match.group(2))
        year_text = match.group(3)
        year = int(year_text) if year_text else 2026
        if year < 100:
            year += 2000
        try:
            exact = date(year, month, day)
            return exact, exact, exact.strftime("%d/%m/%Y"), False
        except ValueError:
            pass

    if any(x in q for x in ("TERCER TRIMESTRE", "3 TRIMESTRE", "III TRIMESTRE")):
        start, end = TRIMESTER_RANGES[3]
        return start, end, "III trimestre 2026", False
    if any(x in q for x in ("SEGUNDO TRIMESTRE", "2 TRIMESTRE", "II TRIMESTRE")):
        start, end = TRIMESTER_RANGES[2]
        return start, end, "II trimestre 2026", False
    if any(x in q for x in ("PRIMER TRIMESTRE", "1 TRIMESTRE", "I TRIMESTRE")):
        start, end = TRIMESTER_RANGES[1]
        return start, end, "I trimestre 2026", False

    for month_name, month_number in MONTHS_ES.items():
        exact_match = re.search(rf"\\b(\\d{{1,2}})\\s+DE\\s+{month_name}\\b", q)
        if exact_match:
            try:
                exact = date(2026, month_number, int(exact_match.group(1)))
                return exact, exact, exact.strftime("%d/%m/%Y"), False
            except ValueError:
                pass

    for month_name, month_number in MONTHS_ES.items():
        if month_name in q:
            start = date(2026, month_number, 1)
            end = date(2026, month_number, calendar.monthrange(2026, month_number)[1])
            return start, end, month_name.title() + " 2026", False

    historical_markers = (
        "ANTERIOR", "ANTES", "HISTORIAL", "PASADO", "OTRO TRIMESTRE",
        "TRIMESTRES ANTERIORES", "MESES ANTERIORES",
    )
    if any(marker in q for marker in historical_markers):
        return None, None, "", True

    return DEFAULT_CLASSROOM_START, None, "desde el 09/09/2026", False


def _norm(value: Any) -> str:
    text = unicodedata.normalize("NFKD", str(value or ""))
    text = "".join(ch for ch in text if not unicodedata.combining(ch))
    text = re.sub(r"[^A-Za-z0-9]+", " ", text).upper()
    return " ".join(text.split())


def _json(data: dict[str, Any], status: int = 200) -> JSONResponse:
    resp = JSONResponse(data, status_code=status)
    resp.headers["Access-Control-Allow-Origin"] = "*"
    resp.headers["Access-Control-Allow-Headers"] = "Content-Type, Authorization"
    resp.headers["Access-Control-Allow-Methods"] = "GET, POST, OPTIONS"
    resp.headers["Cache-Control"] = "no-store"
    return resp


def _b64(raw: bytes) -> str:
    return base64.urlsafe_b64encode(raw).decode("ascii").rstrip("=")


def _b64d(text: str) -> bytes:
    return base64.urlsafe_b64decode(text + "=" * ((4 - len(text) % 4) % 4))


def _sign(payload: dict[str, Any]) -> str:
    if not TOKEN_SECRET:
        raise RuntimeError("PROFE_JOHNNY_TOKEN_SECRET no configurado")
    body = _b64(json.dumps(payload, separators=(",", ":"), ensure_ascii=False).encode("utf-8"))
    sig = _b64(hmac.new(TOKEN_SECRET.encode("utf-8"), body.encode("ascii"), hashlib.sha256).digest())
    return body + "." + sig


def _token(role: str, *, subject: str, section: str = "", children: list[str] | None = None) -> str:
    now = int(time.time())
    return _sign({"sub": subject, "role": role, "section": section, "children": list(children or []), "iat": now, "exp": now + TOKEN_TTL})


def _verify_token(value: str) -> dict[str, Any] | None:
    try:
        body, sig = value.split(".", 1)
        expected = _b64(hmac.new(TOKEN_SECRET.encode("utf-8"), body.encode("ascii"), hashlib.sha256).digest())
        if not hmac.compare_digest(sig, expected):
            return None
        payload = json.loads(_b64d(body))
        if int(payload.get("exp") or 0) < int(time.time()):
            return None
        if payload.get("role") not in {"student", "family", "owner"}:
            return None
        return payload
    except Exception:
        return None


def _auth(request: Request) -> dict[str, Any] | None:
    raw = str(request.headers.get("authorization") or "")
    if not raw.lower().startswith("bearer "):
        return None
    return _verify_token(raw[7:].strip())


def _verify_owner_secret(value: str) -> bool:
    if not OWNER_SECRET_HASH:
        return False
    try:
        algorithm, iterations, salt_b64, digest_b64 = OWNER_SECRET_HASH.split("$", 3)
        if algorithm != "pbkdf2_sha256":
            return False
        salt = _b64d(salt_b64)
        actual = hashlib.pbkdf2_hmac("sha256", value.encode("utf-8"), salt, int(iterations), dklen=32)
        return hmac.compare_digest(_b64(actual), digest_b64)
    except Exception:
        return False


def _roster_record(student_key: str) -> dict[str, str] | None:
    key = str(student_key or "").strip()
    if not key:
        return None
    rows = ba._sheet_get_from(ba.ROSTER_SHEET_ID, "ALUMNOS!A2:G1000")
    for raw in rows:
        row = list(raw) + [""] * (7 - len(raw))
        if str(row[0]).strip() != key:
            continue
        grade_match = re.search(r"[25]", str(row[2] or ""))
        section_letter = _norm(row[3])
        active = _norm(row[5]) in {"ACTIVO", "ACTIVE", "SI", "TRUE", "1"}
        if not grade_match or section_letter not in {"A", "B"} or not active:
            return None
        return {"student_key": key, "full_name": str(row[1]).strip(), "grade": grade_match.group(0), "section": section_letter, "group": grade_match.group(0) + section_letter, "alucod": str(row[6]).strip()}
    return None


def _family_rows() -> list[dict[str, str]]:
    try:
        rows = ba._sheet_get_from(FAMILY_SHEET_ID, f"{FAMILY_TAB}!A2:E2000")
    except Exception:
        return []
    out: list[dict[str, str]] = []
    for raw in rows:
        row = list(raw) + [""] * (5 - len(raw))
        code, student_key, label, active, created_at = [str(x).strip() for x in row[:5]]
        if code and student_key and _norm(active) not in {"NO", "FALSE", "0", "INACTIVO"}:
            out.append({"family_code": code, "student_key": student_key, "label": label, "created_at": created_at})
    return out


def _family_links(code: str) -> list[dict[str, str]]:
    wanted = str(code or "").strip()
    return [row for row in _family_rows() if hmac.compare_digest(row["family_code"], wanted)]


def _student_login(code: str) -> dict[str, Any] | None:
    student = _roster_record(code)
    if not student:
        return None
    return {"token": _token("student", subject=student["student_key"], section=student["group"]), "profile": {"role": "student", "display_name": student["full_name"], "grade": student["grade"], "section": student["section"]}}


def _family_login(code: str) -> dict[str, Any] | None:
    links = _family_links(code)
    children: list[dict[str, str]] = []
    keys: list[str] = []
    for link in links:
        student = _roster_record(link["student_key"])
        if not student:
            continue
        keys.append(student["student_key"])
        children.append({"student_key": student["student_key"], "display_name": student["full_name"], "grade": student["grade"], "section": student["section"]})
    if not keys:
        return None
    return {"token": _token("family", subject=hashlib.sha256(code.encode()).hexdigest()[:16], children=keys), "profile": {"role": "family", "children": children}}


def _course_for_student(student: dict[str, str]) -> tuple[dict[str, Any] | None, dict[str, Any] | None]:
    courses = [c for c in brain._client.list_courses(active_only=True) if brain._course_matches(c, student["grade"], student["section"])]
    target_name = _norm(student["full_name"])
    for course in courses:
        course_id = str(course.get("id") or "")
        if not course_id:
            continue
        for roster in brain._client.list_students(course_id):
            if _norm(roster.get("name")) == target_name:
                return course, roster
    return (courses[0] if courses else None), None


def _all_active_students() -> list[dict[str, str]]:
    rows = ba._sheet_get_from(ba.ROSTER_SHEET_ID, "ALUMNOS!A2:G1000")
    out: list[dict[str, str]] = []
    for raw in rows:
        row = list(raw) + [""] * (7 - len(raw))
        key = str(row[0] or "").strip()
        full_name = str(row[1] or "").strip()
        grade_match = re.search(r"[25]", str(row[2] or ""))
        section_letter = _norm(row[3])
        active = _norm(row[5]) in {"ACTIVO", "ACTIVE", "SI", "TRUE", "1"}
        if not key or not full_name or not grade_match or section_letter not in {"A", "B"} or not active:
            continue
        out.append({
            "student_key": key,
            "full_name": full_name,
            "grade": grade_match.group(0),
            "section": section_letter,
            "group": grade_match.group(0) + section_letter,
            "alucod": str(row[6] or "").strip(),
        })
    return out


def _resolve_student_from_text(text: str) -> dict[str, str] | None:
    query = _norm(text)
    if not query:
        return None
    query_tokens = set(query.split())
    candidates: list[tuple[float, dict[str, str]]] = []
    for student in _all_active_students():
        name = _norm(student["full_name"])
        tokens = [t for t in name.split() if len(t) > 1]
        if not tokens:
            continue
        exact = bool(name and name in query)
        overlap = len(set(tokens) & query_tokens)
        if exact:
            score = 100.0 + len(tokens)
        elif overlap >= 2:
            score = overlap * 10.0 + (overlap / max(1, len(set(tokens))))
        else:
            continue
        group = student.get("group", "")
        if group and _norm(group) in query:
            score += 2.0
        candidates.append((score, student))
    if not candidates:
        return None
    candidates.sort(key=lambda item: (-item[0], _norm(item[1]["full_name"])))
    if len(candidates) > 1 and abs(candidates[0][0] - candidates[1][0]) < 0.0001:
        return None
    return candidates[0][1]


def _student_classroom_summary(student_key: str, limit: int = 100, start_date: date | None = None, end_date: date | None = None) -> dict[str, Any]:
    student = _roster_record(student_key)
    if not student:
        raise ValueError("student_not_found")
    course, roster = _course_for_student(student)
    if not course:
        return {
            "student": student,
            "course": None,
            "activities": [],
            "progress": {
                "total": 0,
                "submitted": 0,
                "pending": 0,
                "late": 0,
                "graded": 0,
                "ungraded_submitted": 0,
                "average_percent": None,
            },
            "warning": "classroom_course_not_found",
        }

    course_id = str(course.get("id") or "")
    user_id = str((roster or {}).get("userId") or "")
    if start_date is None and end_date is None:
        start_date = DEFAULT_CLASSROOM_START
    all_works = brain._client.list_coursework(course_id, include_drafts=False)
    works = []
    for work in all_works:
        work_date = _coursework_date(work)
        if start_date and (work_date is None or work_date < start_date):
            continue
        if end_date and (work_date is None or work_date > end_date):
            continue
        works.append(work)
        if len(works) >= max(1, min(limit, 100)):
            break

    by_work: dict[str, dict[str, Any]] = {}
    if user_id:
        try:
            for sub in brain._client.list_submissions(course_id, "-"):
                if str(sub.get("userId") or "") == user_id:
                    by_work[str(sub.get("courseWorkId") or "")] = sub
        except Exception:
            by_work = {}

    activities: list[dict[str, Any]] = []
    submitted_count = 0
    pending_count = 0
    late_count = 0
    graded_count = 0
    ungraded_submitted = 0
    earned_sum = 0.0
    max_sum = 0.0

    labels = {
        "TURNED_IN": "Entregada",
        "RETURNED": "Devuelta / calificada",
        "RECLAIMED_BY_STUDENT": "Retirada por el estudiante",
        "CREATED": "Pendiente",
        "NEW": "Pendiente",
    }

    for work in works:
        work_id = str(work.get("id") or "")
        item: dict[str, Any] = {
            "id": work_id,
            "title": str(work.get("title") or ""),
            "due": brain._format_due(work),
            "max_points": work.get("maxPoints"),
            "state": None,
            "status": "Pendiente",
            "late": False,
            "grade": None,
            "submitted": False,
            "updated_at": None,
        }

        sub = by_work.get(work_id)
        if sub is None and user_id and work_id and not by_work:
            try:
                sub = next(
                    (
                        row
                        for row in brain._client.list_submissions(course_id, work_id)
                        if str(row.get("userId") or "") == user_id
                    ),
                    None,
                )
            except Exception:
                sub = None

        if sub:
            state = str(sub.get("state") or "")
            grade = sub.get("assignedGrade")
            if grade is None:
                grade = sub.get("draftGrade")
            is_submitted = state in {"TURNED_IN", "RETURNED"}
            item.update({
                "state": state or None,
                "status": labels.get(state, state or "Pendiente"),
                "late": bool(sub.get("late")),
                "grade": grade,
                "submitted": is_submitted,
                "updated_at": sub.get("updateTime"),
            })

        if item["submitted"]:
            submitted_count += 1
            if item["grade"] is None:
                ungraded_submitted += 1
        else:
            pending_count += 1
        if item["late"]:
            late_count += 1
        if item["grade"] is not None:
            graded_count += 1
            try:
                max_points = float(item["max_points"])
                grade_value = float(item["grade"])
                if max_points > 0:
                    earned_sum += grade_value
                    max_sum += max_points
            except (TypeError, ValueError):
                pass
        activities.append(item)

    average_percent = round((earned_sum / max_sum) * 100.0, 1) if max_sum > 0 else None
    return {
        "student": {
            "student_key": student["student_key"],
            "display_name": student["full_name"],
            "grade": student["grade"],
            "section": student["section"],
        },
        "course": {"id": course_id, "name": course.get("name"), "section": course.get("section")},
        "classroom_user_resolved": bool(user_id),
        "period": {
            "start": start_date.isoformat() if start_date else None,
            "end": end_date.isoformat() if end_date else None,
        },
        "progress": {
            "total": len(activities),
            "submitted": submitted_count,
            "pending": pending_count,
            "late": late_count,
            "graded": graded_count,
            "ungraded_submitted": ungraded_submitted,
            "average_percent": average_percent,
        },
        "activities": activities,
    }

def _allowed_student(payload: dict[str, Any], requested: str = "") -> str:
    role = str(payload.get("role") or "")
    if role == "student":
        return str(payload.get("sub") or "")
    if role == "family":
        children = [str(x) for x in (payload.get("children") or [])]
        if requested and requested in children:
            return requested
        return children[0] if len(children) == 1 else ""
    if role == "owner":
        return str(requested or "")
    return ""


def _private_context(student_key: str, start_date: date | None = None, end_date: date | None = None, role: str = "student") -> tuple[str, dict[str, Any]]:
    summary = _student_classroom_summary(student_key, start_date=start_date, end_date=end_date)
    lines = ["## CLASSROOM PRIVADO DEL USUARIO AUTENTICADO", f"Estudiante: {summary['student']['display_name']} | {summary['student']['grade']}.º {summary['student']['section']}"]
    for item in summary.get("activities") or []:
        lines.append(f"- {item['title']} | límite={item['due']} | estado={item.get('state')} | nota={item.get('grade')} / {item.get('max_points')} | tardía={item.get('late')}")
    lines.append("## POLÍTICA SIEWEB")
    lines.append("Para estudiantes y familias, cualquier información de SIEweb/CIEweb debe convertirse en orientación pedagógica sin revelar letra o nota cruda; para owner sí puede mostrarse el dato disponible. No inventes SIEweb si no está en el contexto.")
    return "\n".join(lines), summary


def _write_family_link(family_code: str, student_key: str, label: str = "") -> None:
    student = _roster_record(student_key)
    if not student:
        raise ValueError("student_not_found")
    if any(r["family_code"] == family_code and r["student_key"] == student_key for r in _family_rows()):
        return
    url = f"https://sheets.googleapis.com/v4/spreadsheets/{FAMILY_SHEET_ID}/values/{quote(FAMILY_TAB + '!A:E', safe='')}:append"
    _google_request("POST", url, params={"valueInputOption": "RAW", "insertDataOption": "INSERT_ROWS"}, json_body={"values": [[family_code, student_key, label, "ACTIVO", brain._now_lima().isoformat()]]})


def install(mcp: Any) -> None:
    if getattr(mcp, "_profe_johnny_identity_v3_installed", False):
        return

    @mcp.custom_route("/profe-johnny/v1/auth", methods=["POST", "OPTIONS"])
    async def auth_route(request: Request):
        if request.method == "OPTIONS":
            return _json({"ok": True})
        try:
            body = await request.json()
        except Exception:
            body = {}
        role = str(body.get("role") or "auto").strip().lower()
        code = str(body.get("code") or "").strip()
        if not code:
            return _json({"ok": False, "error": "invalid_credentials"}, 401)

        if role in {"auto", ""}:
            if _verify_owner_secret(code):
                result = {
                    "token": _token("owner", subject="owner"),
                    "profile": {"role": "owner", "display_name": "Profe Johnny"},
                }
            else:
                result = _student_login(code)
                if not result:
                    result = _family_login(code)
        elif role == "student":
            result = _student_login(code)
        elif role == "family":
            result = _family_login(code)
        elif role == "owner":
            result = {
                "token": _token("owner", subject="owner"),
                "profile": {"role": "owner", "display_name": "Profe Johnny"},
            } if _verify_owner_secret(code) else None
        else:
            return _json({"ok": False, "error": "invalid_role"}, 400)
        if not result:
            return _json({"ok": False, "error": "invalid_credentials"}, 401)
        return _json({"ok": True, **result})

    @mcp.custom_route("/profe-johnny/v1/me", methods=["GET", "OPTIONS"])
    async def me_route(request: Request):
        if request.method == "OPTIONS":
            return _json({"ok": True})
        payload = _auth(request)
        if not payload:
            return _json({"ok": False, "error": "unauthorized"}, 401)
        role = payload["role"]
        if role == "student":
            profile = {"role": role, "student": _roster_record(str(payload.get("sub") or ""))}
        elif role == "family":
            profile = {"role": role, "children": [_roster_record(str(k)) for k in payload.get("children") or []]}
        else:
            profile = {"role": "owner", "display_name": "Profe Johnny"}
        return _json({"ok": True, "profile": profile})

    @mcp.custom_route("/profe-johnny/v1/student-summary", methods=["GET", "OPTIONS"])
    async def student_summary_route(request: Request):
        if request.method == "OPTIONS":
            return _json({"ok": True})
        payload = _auth(request)
        if not payload:
            return _json({"ok": False, "error": "unauthorized"}, 401)
        requested = str(request.query_params.get("student_key") or "").strip()
        allowed = _allowed_student(payload, requested)
        if not allowed:
            return _json({"ok": False, "error": "student_selection_required"}, 400)
        if payload["role"] != "owner" and requested and requested != allowed:
            return _json({"ok": False, "error": "forbidden"}, 403)
        try:
            summary = _student_classroom_summary(allowed)
        except ValueError as exc:
            return _json({"ok": False, "error": str(exc)}, 404)
        return _json({"ok": True, **summary})

    @mcp.custom_route("/profe-johnny/v1/secure-chat", methods=["POST", "OPTIONS"])
    async def secure_chat_route(request: Request):
        if request.method == "OPTIONS":
            return _json({"ok": True})
        payload = _auth(request)
        if not payload:
            return _json({"ok": False, "error": "unauthorized"}, 401)
        try:
            body = await request.json()
        except Exception:
            body = {}
        message = str(body.get("message") or "").strip()
        requested = str(body.get("student_key") or "").strip()
        if not message:
            return _json({"ok": False, "error": "empty_message"}, 400)

        owner_auto_resolved = None
        if payload.get("role") == "owner" and not requested:
            owner_auto_resolved = _resolve_student_from_text(message)
            if owner_auto_resolved:
                requested = owner_auto_resolved["student_key"]

        period_start, period_end, period_label, needs_period = _period_from_message(message)
        if needs_period:
            return _json({
                "ok": True,
                "reply": (
                    "Claro. Para revisar información anterior al periodo actual, indícame de qué "
                    "trimestre, mes o fecha específica deseas saber."
                ),
                "meta": {
                    "role": payload["role"],
                    "period_selection_required": True,
                    "api_version": API_VERSION,
                },
            })

        student_key = _allowed_student(payload, requested)
        private_context = ""
        summary: dict[str, Any] | None = None
        if student_key:
            try:
                private_context, summary = _private_context(
                    student_key,
                    start_date=period_start,
                    end_date=period_end,
                    role=str(payload.get("role") or "student"),
                )
            except Exception as exc:
                private_context = f"## DATOS PRIVADOS\nNo se pudo cargar Classroom privado: {type(exc).__name__}."
        elif payload["role"] != "owner":
            return _json({"ok": False, "error": "student_selection_required"}, 400)
        rules = {
            "student": (
                "Responde solo sobre el estudiante autenticado. Puedes mostrar sus propias notas exactas de Classroom. "
                "Nunca datos de compañeros. Mantén un tono pedagógico, claro y respetuoso."
            ),
            "family": (
                "Responde solo sobre hijos vinculados al código familiar. Usa SIEMPRE lenguaje psicopedagógico, "
                "respetuoso, constructivo y orientado al acompañamiento. Describe hechos observables y su impacto; "
                "no etiquetes al estudiante ni uses expresiones como molestar, fastidiar, portarse mal, flojo, "
                "irresponsable o problemático. No reveles nombres ni datos de otros menores. Si existe una incidencia, "
                "explica brevemente qué se observó, cómo pudo afectar el aprendizaje o la convivencia y una sugerencia "
                "realista para acompañar. Presenta la respuesta con párrafos cortos, títulos en negrita y viñetas "
                "cuando ayuden a la lectura. Nunca datos de otros estudiantes."
            ),
            "owner": (
                "El usuario autenticado es el propietario/docente. Puede consultar cualquier estudiante y recibir "
                "datos académicos completos disponibles."
            ),
        }
        context = (
            f"## IDENTIDAD VERIFICADA\nRol: {payload['role']}\n{rules[payload['role']]}\n"
            f"Periodo consultado: {period_label or 'periodo indicado'}\n\n"
            + private_context
        )
        grade = str(summary["student"]["grade"]) + ".º año" if summary else "según contexto"
        try:
            reply = brain._openai_reply(message, grade, context)
        except Exception:
            reply = ""
        if not reply:
            reply = "No pude generar la respuesta completa en este momento, pero tu identidad sí quedó verificada."
        return _json({
            "ok": True,
            "reply": reply,
            "meta": {
                "role": payload["role"],
                "student_key": student_key or None,
                "private_classroom_used": bool(summary),
                "period": {
                    "label": period_label,
                    "start": period_start.isoformat() if period_start else None,
                    "end": period_end.isoformat() if period_end else None,
                },
                "owner_auto_resolved_student": (
                    {
                        "student_key": owner_auto_resolved["student_key"],
                        "display_name": owner_auto_resolved["full_name"],
                        "grade": owner_auto_resolved["grade"],
                        "section": owner_auto_resolved["section"],
                    }
                    if owner_auto_resolved else None
                ),
                "api_version": API_VERSION,
            },
        })

    @mcp.custom_route("/profe-johnny/v1/owner/family-link", methods=["POST", "OPTIONS"])
    async def family_link_route(request: Request):
        if request.method == "OPTIONS":
            return _json({"ok": True})
        payload = _auth(request)
        if not payload or payload.get("role") != "owner":
            return _json({"ok": False, "error": "forbidden"}, 403)
        try:
            body = await request.json()
        except Exception:
            body = {}
        family_code = str(body.get("family_code") or "").strip()
        student_key = str(body.get("student_key") or "").strip()
        label = str(body.get("label") or "").strip()[:80]
        if not re.fullmatch(r"[A-Za-z0-9._-]{6,40}", family_code):
            return _json({"ok": False, "error": "invalid_family_code"}, 400)
        try:
            _write_family_link(family_code, student_key, label)
        except Exception as exc:
            return _json({"ok": False, "error": f"{type(exc).__name__}: {exc}"}, 500)
        return _json({"ok": True, "linked": True})

    setattr(mcp, "_profe_johnny_identity_v3_installed", True)
    print("PROFE JOHNNY APP Identity v3: auth, me, student-summary y secure-chat instalados.", flush=True)
