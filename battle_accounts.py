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
from datetime import datetime, timezone
from typing import Any
from urllib.parse import quote
from uuid import uuid4

from starlette.requests import Request
from starlette.responses import JSONResponse

from bitacora import _google_request

SHEET_ID = os.getenv("BATTLE_SPREADSHEET_ID", "").strip()
TOKEN_SECRET = os.getenv("BATTLE_TOKEN_SECRET", "").strip()
SECTIONS = {"2A", "2B", "5A", "5B"}
_lock = threading.RLock()


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
    payload = {"sub": account_id, "usr": username, "iat": int(time.time()), "exp": int(time.time()) + 30 * 86400}
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


def _sheet_get(a1: str) -> list[list[Any]]:
    url = f"https://sheets.googleapis.com/v4/spreadsheets/{SHEET_ID}/values/{quote(a1, safe='')}"
    return list((_google_request("GET", url).get("values") or []))


def _sheet_append(a1: str, row: list[Any]) -> None:
    url = f"https://sheets.googleapis.com/v4/spreadsheets/{SHEET_ID}/values/{quote(a1, safe='')}:append"
    _google_request("POST", url, params={"valueInputOption": "RAW", "insertDataOption": "INSERT_ROWS"}, json_body={"values": [row]})


def _sheet_update(a1: str, values: list[list[Any]]) -> None:
    url = f"https://sheets.googleapis.com/v4/spreadsheets/{SHEET_ID}/values/{quote(a1, safe='')}"
    _google_request("PUT", url, params={"valueInputOption": "RAW"}, json_body={"values": values})


def _accounts() -> list[dict[str, Any]]:
    rows = _sheet_get("CUENTAS!A2:L2000")
    out = []
    for idx, raw in enumerate(rows, start=2):
        row = list(raw) + [""] * (12 - len(raw))
        if not str(row[0]).strip():
            continue
        out.append({
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
            "best_score": int(float(row[10] or 0)),
            "best_score_at": str(row[11]),
        })
    return out


def _public(a: dict[str, Any]) -> dict[str, Any]:
    return {
        "account_id": a["account_id"], "username": a["username"], "display_name": a["display_name"],
        "section": a["section"], "avatar": a["avatar"], "best_score": a["best_score"],
    }


def _auth(request: Request) -> dict[str, Any] | None:
    raw = str(request.headers.get("authorization") or "")
    if not raw.lower().startswith("bearer "):
        return None
    payload = _verify_token(raw[7:].strip())
    if not payload:
        return None
    for a in _accounts():
        if a["account_id"] == payload.get("sub") and a["active"]:
            return a
    return None


def _normalize_section(value: Any) -> str:
    text = re.sub(r"[^25AB]", "", str(value or "").upper())
    if text in SECTIONS:
        return text
    return ""


def _normalize_username(value: Any) -> str:
    return re.sub(r"[^a-z0-9._-]", "", str(value or "").strip().lower())


def _leaderboard(section: str = "", limit: int = 100) -> list[dict[str, Any]]:
    accounts = [a for a in _accounts() if a["active"] and a["best_score"] > 0 and (not section or a["section"] == section)]
    accounts.sort(key=lambda a: (-a["best_score"], a["best_score_at"] or "9999"))
    return [{"rank": i + 1, **_public(a)} for i, a in enumerate(accounts[:limit])]


def install(mcp) -> None:
    @mcp.custom_route("/battle/v1/status", methods=["GET"])
    async def status(request: Request):
        return _json({"ok": True, "service": "Batalla Matemática Accounts", "online_accounts": bool(SHEET_ID and TOKEN_SECRET)})

    @mcp.custom_route("/battle/v1/register", methods=["POST", "OPTIONS"])
    async def register(request: Request):
        if request.method == "OPTIONS": return _json({"ok": True})
        try: body = await request.json()
        except Exception: body = {}
        username = _normalize_username(body.get("username"))
        pin = str(body.get("pin") or "").strip()
        name = " ".join(str(body.get("display_name") or "").split()).strip()
        section = _normalize_section(body.get("section"))
        avatar = str(body.get("avatar") or "🥷🏻")[:16]
        if not re.fullmatch(r"[a-z0-9._-]{4,20}", username): return _json({"ok": False, "error": "invalid_username"}, 400)
        if not re.fullmatch(r"\d{6}", pin): return _json({"ok": False, "error": "invalid_pin"}, 400)
        if not (2 <= len(name) <= 40): return _json({"ok": False, "error": "invalid_display_name"}, 400)
        if section not in SECTIONS: return _json({"ok": False, "error": "invalid_section"}, 400)
        with _lock:
            if any(a["username"] == username for a in _accounts()): return _json({"ok": False, "error": "username_taken"}, 409)
            account_id = str(uuid4()); salt = _b64(secrets.token_bytes(16)); now = _now()
            _sheet_append("CUENTAS!A:L", [account_id, username, salt, _pin_hash(pin, salt), name, section, avatar, now, now, True, 0, ""])
        account = next(a for a in _accounts() if a["account_id"] == account_id)
        return _json({"ok": True, "token": _token(account_id, username), "profile": _public(account)})

    @mcp.custom_route("/battle/v1/login", methods=["POST", "OPTIONS"])
    async def login(request: Request):
        if request.method == "OPTIONS": return _json({"ok": True})
        try: body = await request.json()
        except Exception: body = {}
        username = _normalize_username(body.get("username")); pin = str(body.get("pin") or "").strip()
        account = next((a for a in _accounts() if a["username"] == username and a["active"]), None)
        if not account or not re.fullmatch(r"\d{6}", pin) or not hmac.compare_digest(account["pin_hash"], _pin_hash(pin, account["pin_salt"])):
            return _json({"ok": False, "error": "invalid_credentials"}, 401)
        _sheet_update(f"CUENTAS!I{account['row']}", [[_now()]])
        return _json({"ok": True, "token": _token(account["account_id"], account["username"]), "profile": _public(account)})

    @mcp.custom_route("/battle/v1/me", methods=["GET", "OPTIONS"])
    async def me(request: Request):
        if request.method == "OPTIONS": return _json({"ok": True})
        account = _auth(request)
        if not account: return _json({"ok": False, "error": "unauthorized"}, 401)
        return _json({"ok": True, "profile": _public(account)})

    @mcp.custom_route("/battle/v1/score", methods=["POST", "OPTIONS"])
    async def score(request: Request):
        if request.method == "OPTIONS": return _json({"ok": True})
        account = _auth(request)
        if not account: return _json({"ok": False, "error": "unauthorized"}, 401)
        try: body = await request.json()
        except Exception: body = {}
        try: pts = int(body.get("score")); level = int(body.get("level", 1)); accuracy = int(body.get("accuracy", 0))
        except Exception: return _json({"ok": False, "error": "invalid_score"}, 400)
        if not (0 <= pts <= 5000 and 1 <= level <= 3 and 0 <= accuracy <= 100): return _json({"ok": False, "error": "invalid_score"}, 400)
        now = _now(); result_id = str(uuid4())
        _sheet_append("RESULTADOS!A:L", [result_id, account["account_id"], account["username"], account["display_name"], account["section"], pts, level, accuracy, now, str(body.get("client_version") or ""), str(body.get("game_session_id") or ""), True])
        if pts > account["best_score"]:
            _sheet_update(f"CUENTAS!K{account['row']}:L{account['row']}", [[pts, now]])
        board = _leaderboard(account["section"], 500)
        rank = next((x["rank"] for x in board if x["account_id"] == account["account_id"]), None)
        return _json({"ok": True, "score_saved": True, "personal_best": max(pts, account["best_score"]), "section_rank": rank})

    @mcp.custom_route("/battle/v1/leaderboard", methods=["GET", "OPTIONS"])
    async def leaderboard(request: Request):
        if request.method == "OPTIONS": return _json({"ok": True})
        section = _normalize_section(request.query_params.get("section")) if request.query_params.get("section") else ""
        try: limit = max(1, min(500, int(request.query_params.get("limit") or 100)))
        except Exception: limit = 100
        return _json({"ok": True, "section": section or "GLOBAL", "players": _leaderboard(section, limit), "updated_at": _now()})

    print("BATALLA MATEMÁTICA: cuentas online y ranking /battle/v1 instalados.", flush=True)
