from __future__ import annotations

import base64
import hashlib
import hmac
import json
import os
import re
import secrets
import threading
import time
import unicodedata
from datetime import datetime, timezone
from typing import Any
from urllib.parse import quote
from uuid import uuid4

from starlette.requests import Request
from starlette.responses import JSONResponse

from bitacora import DEFAULT_SPREADSHEET_ID, _google_request

SHEET_ID = os.getenv("BATTLE_SPREADSHEET_ID", "").strip()
TOKEN_SECRET = os.getenv("BATTLE_TOKEN_SECRET", "").strip()
ROSTER_SHEET_ID = os.getenv("BATTLE_ROSTER_SHEET_ID", DEFAULT_SPREADSHEET_ID).strip()

SCHOOL_SECTIONS = {"2A", "2B", "5A", "5B"}
PUBLIC_SECTION = "PUBLIC"
SECTIONS = SCHOOL_SECTIONS | {PUBLIC_SECTION}

_lock = threading.RLock()
_roster_lock = threading.RLock()
_roster_cache: dict[str, Any] = {"at": 0.0, "items": []}


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _cors(resp: JSONResponse) -> JSONResponse:
    resp.headers["Access-Control-Allow-Origin"] = "*"
    resp.headers["Access-Control-Allow-Headers"] = "Content-Type, Authorization"
    resp.headers["Access-Control-Allow-Methods"] = "GET, POST, OPTIONS"
    resp.headers["Cache-Control"] = "no-store"
    return resp


def _json(data: dict[str, Any], status: int = 200) -> JSONResponse:
    return _cors(JSONResponse(data, status_code=status))


def _b64(raw: bytes) -> str:
    return base64.urlsafe_b64encode(raw).decode("ascii").rstrip("=")


def _b64d(text: str) -> bytes:
    return base64.urlsafe_b64decode(text + "=" * ((4 - len(text) % 4) % 4))


def _token(account_id: str, username: str) -> str:
    if not TOKEN_SECRET:
        raise RuntimeError("BATTLE_TOKEN_SECRET no está configurado")
    payload = {
        "sub": account_id,
        "usr": username,
        "iat": int(time.time()),
        "exp": int(time.time()) + 30 * 86400,
    }
    body = _b64(json.dumps(payload, separators=(",", ":"), ensure_ascii=False).encode("utf-8"))
    sig = _b64(hmac.new(TOKEN_SECRET.encode("utf-8"), body.encode("ascii"), hashlib.sha256).digest())
    return body + "." + sig


def _verify_token(value: str) -> dict[str, Any] | None:
    try:
        body, sig = value.split(".", 1)
        expected = _b64(hmac.new(TOKEN_SECRET.encode("utf-8"), body.encode("ascii"), hashlib.sha256).digest())
        if not hmac.compare_digest(sig, expected):
            return None
        payload = json.loads(_b64d(body))
        if int(payload.get("exp") or 0) < int(time.time()):
            return None
        if not payload.get("sub"):
            return None
        return payload
    except Exception:
        return None


def _pin_hash(pin: str, salt_b64: str) -> str:
    salt = _b64d(salt_b64)
    return _b64(hashlib.pbkdf2_hmac("sha256", pin.encode("utf-8"), salt, 180_000, dklen=32))


def _sheet_get_from(sheet_id: str, a1: str) -> list[list[Any]]:
    url = f"https://sheets.googleapis.com/v4/spreadsheets/{sheet_id}/values/{quote(a1, safe='')}"
    return list((_google_request("GET", url).get("values") or []))


def _sheet_get(a1: str) -> list[list[Any]]:
    return _sheet_get_from(SHEET_ID, a1)


def _sheet_append(a1: str, row: list[Any]) -> None:
    url = f"https://sheets.googleapis.com/v4/spreadsheets/{SHEET_ID}/values/{quote(a1, safe='')}:append"
    _google_request(
        "POST",
        url,
        params={"valueInputOption": "RAW", "insertDataOption": "INSERT_ROWS"},
        json_body={"values": [row]},
    )


def _sheet_update(a1: str, values: list[list[Any]]) -> None:
    url = f"https://sheets.googleapis.com/v4/spreadsheets/{SHEET_ID}/values/{quote(a1, safe='')}"
    _google_request("PUT", url, params={"valueInputOption": "RAW"}, json_body={"values": values})


def _accounts() -> list[dict[str, Any]]:
    rows = _sheet_get("CUENTAS!A2:M2000")
    out = []
    for idx, raw in enumerate(rows, start=2):
        row = list(raw) + [""] * (13 - len(raw))
        if not str(row[0]).strip():
            continue
        try:
            best_score = int(float(row[10] or 0))
        except Exception:
            best_score = 0
        out.append(
            {
                "row": idx,
                "account_id": str(row[0]),
                "username": str(row[1]).lower(),
                "pin_salt": str(row[2]),
                "pin_hash": str(row[3]),
                "display_name": str(row[4]),
                "section": str(row[5]).upper(),
                "avatar": str(row[6]),
                "created_at": str(row[7]),
                "last_login_at": str(row[8]),
                "active": str(row[9]).lower() not in {"false", "0", "no"},
                "best_score": best_score,
                "best_score_at": str(row[11]),
                "student_key": str(row[12]).strip(),
            }
        )
    return out


def _public(a: dict[str, Any]) -> dict[str, Any]:
    return {
        "account_id": a["account_id"],
        "username": a["username"],
        "display_name": a["display_name"],
        "section": a["section"],
        "avatar": a["avatar"],
        "best_score": a["best_score"],
    }


def _auth(request: Request) -> dict[str, Any] | None:
    raw = str(request.headers.get("authorization") or "")
    if not raw.lower().startswith("bearer "):
        return None
    payload = _verify_token(raw[7:].strip())
    if not payload:
        return None
    for account in _accounts():
        if account["account_id"] == payload.get("sub") and account["active"]:
            return account
    return None


def _norm_text(value: Any) -> str:
    text = unicodedata.normalize("NFKD", str(value or ""))
    text = "".join(ch for ch in text if not unicodedata.combining(ch))
    text = re.sub(r"[^A-Za-z0-9]+", " ", text).upper()
    return " ".join(text.split())


def _normalize_section(value: Any) -> str:
    raw = _norm_text(value)
    if raw in {"PUBLIC", "PUBLICO", "PUBLICO GENERAL", "GENERAL"}:
        return PUBLIC_SECTION
    text = re.sub(r"[^25AB]", "", raw)
    return text if text in SCHOOL_SECTIONS else ""


def _normalize_username(value: Any) -> str:
    return re.sub(r"[^a-z0-9._-]", "", str(value or "").strip().lower())


def _safe_student_display(full_name: str) -> str:
    raw = " ".join(str(full_name or "").split()).strip()
    if not raw:
        return ""
    if "," in raw:
        surname_part, given_part = [part.strip() for part in raw.split(",", 1)]
    else:
        bits = raw.split()
        surname_part = bits[0] if bits else ""
        given_part = bits[-1] if bits else ""
    first_name = (given_part.split()[0] if given_part.split() else "").title()
    surname = surname_part.split()[0] if surname_part.split() else ""
    initial = surname[:1].upper()
    return f"{first_name} {initial}.".strip()


def _roster_items(force: bool = False) -> list[dict[str, str]]:
    now = time.time()
    with _roster_lock:
        if not force and _roster_cache["items"] and now - float(_roster_cache["at"]) < 300:
            return list(_roster_cache["items"])
        rows = _sheet_get_from(ROSTER_SHEET_ID, "ALUMNOS!A2:G1000")
        items: list[dict[str, str]] = []
        for raw in rows:
            row = list(raw) + [""] * (7 - len(raw))
            student_key = str(row[0]).strip()
            full_name = str(row[1]).strip()
            grade = re.search(r"[25]", str(row[2] or ""))
            section_letter = _norm_text(row[3])
            active = _norm_text(row[5]) in {"ACTIVO", "ACTIVE", "SI", "TRUE", "1"}
            if not student_key or not full_name or not grade or section_letter not in {"A", "B"} or not active:
                continue
            section = f"{grade.group(0)}{section_letter}"
            if section not in SCHOOL_SECTIONS:
                continue
            items.append(
                {
                    "student_key": student_key,
                    "display_name": _safe_student_display(full_name),
                    "section": section,
                }
            )
        _roster_cache["at"] = now
        _roster_cache["items"] = items
        return list(items)


def _student_for(section: str, student_key: str) -> dict[str, str] | None:
    key = str(student_key or "").strip()
    if not key:
        return None
    return next(
        (item for item in _roster_items() if item["section"] == section and item["student_key"] == key),
        None,
    )


def _clean_public_name(value: Any) -> str:
    name = " ".join(str(value or "").split()).strip()
    if not (3 <= len(name) <= 40):
        return ""
    if re.fullmatch(r"[A-Za-zÁÉÍÓÚÜÑáéíóúüñ'’-]{2,24}\s+[A-Za-zÁÉÍÓÚÜÑáéíóúüñ'’-](?:\.|[A-Za-zÁÉÍÓÚÜÑáéíóúüñ'’-]{1,30})", name):
        return name
    return ""


def _leaderboard(section: str = "", limit: int = 100) -> list[dict[str, Any]]:
    accounts = [
        account
        for account in _accounts()
        if account["active"]
        and account["best_score"] > 0
        and (not section or account["section"] == section)
    ]
    accounts.sort(key=lambda account: (-account["best_score"], account["best_score_at"] or "9999"))
    return [{"rank": i + 1, **_public(account)} for i, account in enumerate(accounts[:limit])]


def _rank_for(account_id: str, section: str = "") -> int | None:
    board = _leaderboard(section, 5000)
    return next((entry["rank"] for entry in board if entry["account_id"] == account_id), None)


def install(mcp) -> None:
    @mcp.custom_route("/battle/v1/status", methods=["GET"])
    async def status(request: Request):
        return _json(
            {
                "ok": True,
                "service": "Batalla Matemática Accounts",
                "online_accounts": bool(SHEET_ID and TOKEN_SECRET),
                "roster_validation": bool(ROSTER_SHEET_ID),
                "groups": ["2A", "2B", "5A", "5B", PUBLIC_SECTION],
            }
        )

    @mcp.custom_route("/battle/v1/roster", methods=["GET", "OPTIONS"])
    async def roster(request: Request):
        if request.method == "OPTIONS":
            return _json({"ok": True})
        section = _normalize_section(request.query_params.get("section"))
        if section not in SCHOOL_SECTIONS:
            return _json({"ok": False, "error": "invalid_section"}, 400)
        try:
            taken = {a["student_key"] for a in _accounts() if a["active"] and a.get("student_key")}
            players = [
                {
                    "student_key": item["student_key"],
                    "display_name": item["display_name"],
                    "available": item["student_key"] not in taken,
                }
                for item in _roster_items()
                if item["section"] == section
            ]
            players.sort(key=lambda item: _norm_text(item["display_name"]))
            return _json({"ok": True, "section": section, "players": players})
        except Exception:
            return _json({"ok": False, "error": "roster_unavailable"}, 503)

    @mcp.custom_route("/battle/v1/register", methods=["POST", "OPTIONS"])
    async def register(request: Request):
        if request.method == "OPTIONS":
            return _json({"ok": True})
        try:
            body = await request.json()
        except Exception:
            body = {}
        username = _normalize_username(body.get("username"))
        pin = str(body.get("pin") or "").strip()
        section = _normalize_section(body.get("section"))
        avatar = str(body.get("avatar") or "🥷🏻")[:16]
        student_key = str(body.get("student_key") or "").strip()

        if not re.fullmatch(r"[a-z0-9._-]{4,20}", username):
            return _json({"ok": False, "error": "invalid_username"}, 400)
        if not re.fullmatch(r"\d{6}", pin):
            return _json({"ok": False, "error": "invalid_pin"}, 400)
        if section not in SECTIONS:
            return _json({"ok": False, "error": "invalid_section"}, 400)

        if section in SCHOOL_SECTIONS:
            student = _student_for(section, student_key)
            if not student:
                return _json({"ok": False, "error": "invalid_student"}, 400)
            name = student["display_name"]
        else:
            student_key = ""
            name = _clean_public_name(body.get("display_name"))
            if not name:
                return _json({"ok": False, "error": "invalid_display_name"}, 400)

        with _lock:
            accounts = _accounts()
            if any(a["username"] == username for a in accounts):
                return _json({"ok": False, "error": "username_taken"}, 409)
            if student_key and any(a.get("student_key") == student_key and a["active"] for a in accounts):
                return _json({"ok": False, "error": "student_taken"}, 409)

            account_id = str(uuid4())
            salt = _b64(secrets.token_bytes(16))
            now = _now()
            _sheet_append(
                "CUENTAS!A:M",
                [
                    account_id,
                    username,
                    salt,
                    _pin_hash(pin, salt),
                    name,
                    section,
                    avatar,
                    now,
                    now,
                    True,
                    0,
                    "",
                    student_key,
                ],
            )

        account = next(a for a in _accounts() if a["account_id"] == account_id)
        return _json(
            {
                "ok": True,
                "token": _token(account_id, username),
                "profile": _public(account),
            }
        )

    @mcp.custom_route("/battle/v1/login", methods=["POST", "OPTIONS"])
    async def login(request: Request):
        if request.method == "OPTIONS":
            return _json({"ok": True})
        try:
            body = await request.json()
        except Exception:
            body = {}
        username = _normalize_username(body.get("username"))
        pin = str(body.get("pin") or "").strip()
        account = next((a for a in _accounts() if a["username"] == username and a["active"]), None)
        if (
            not account
            or not re.fullmatch(r"\d{6}", pin)
            or not hmac.compare_digest(account["pin_hash"], _pin_hash(pin, account["pin_salt"]))
        ):
            return _json({"ok": False, "error": "invalid_credentials"}, 401)
        _sheet_update(f"CUENTAS!I{account['row']}", [[_now()]])
        return _json(
            {
                "ok": True,
                "token": _token(account["account_id"], account["username"]),
                "profile": _public(account),
            }
        )

    @mcp.custom_route("/battle/v1/me", methods=["GET", "OPTIONS"])
    async def me(request: Request):
        if request.method == "OPTIONS":
            return _json({"ok": True})
        account = _auth(request)
        if not account:
            return _json({"ok": False, "error": "unauthorized"}, 401)
        return _json({"ok": True, "profile": _public(account)})

    @mcp.custom_route("/battle/v1/score", methods=["POST", "OPTIONS"])
    async def score(request: Request):
        if request.method == "OPTIONS":
            return _json({"ok": True})
        account = _auth(request)
        if not account:
            return _json({"ok": False, "error": "unauthorized"}, 401)
        try:
            body = await request.json()
        except Exception:
            body = {}
        try:
            pts = int(body.get("score"))
            level = int(body.get("level", 1))
            accuracy = int(body.get("accuracy", 0))
        except Exception:
            return _json({"ok": False, "error": "invalid_score"}, 400)
        if not (0 <= pts <= 5000 and 1 <= level <= 3 and 0 <= accuracy <= 100):
            return _json({"ok": False, "error": "invalid_score"}, 400)

        now = _now()
        result_id = str(uuid4())
        _sheet_append(
            "RESULTADOS!A:L",
            [
                result_id,
                account["account_id"],
                account["username"],
                account["display_name"],
                account["section"],
                pts,
                level,
                accuracy,
                now,
                str(body.get("client_version") or ""),
                str(body.get("game_session_id") or ""),
                True,
            ],
        )
        if pts > account["best_score"]:
            _sheet_update(f"CUENTAS!K{account['row']}:L{account['row']}", [[pts, now]])

        section_rank = _rank_for(account["account_id"], account["section"])
        global_rank = _rank_for(account["account_id"], "")
        return _json(
            {
                "ok": True,
                "score_saved": True,
                "personal_best": max(pts, account["best_score"]),
                "section_rank": section_rank,
                "global_rank": global_rank,
                "section": account["section"],
            }
        )

    @mcp.custom_route("/battle/v1/leaderboard", methods=["GET", "OPTIONS"])
    async def leaderboard(request: Request):
        if request.method == "OPTIONS":
            return _json({"ok": True})
        raw_section = request.query_params.get("section")
        section = _normalize_section(raw_section) if raw_section else ""
        if raw_section and section not in SECTIONS:
            return _json({"ok": False, "error": "invalid_section"}, 400)
        try:
            limit = max(1, min(500, int(request.query_params.get("limit") or 100)))
        except Exception:
            limit = 100
        return _json(
            {
                "ok": True,
                "section": section or "GLOBAL",
                "players": _leaderboard(section, limit),
                "updated_at": _now(),
            }
        )

    print(
        "BATALLA MATEMÁTICA: cuentas online, roster y ranking global /battle/v1 instalados.",
        flush=True,
    )
