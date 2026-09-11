from __future__ import annotations

import hmac
import re
import secrets
from uuid import uuid4

from starlette.requests import Request

from battle_accounts import (
    PUBLIC_SECTION,
    SCHOOL_SECTIONS,
    SECTIONS,
    _accounts,
    _auth,
    _b64,
    _clean_public_name,
    _json,
    _normalize_section,
    _normalize_username,
    _now,
    _pin_hash,
    _public,
    _sheet_append,
    _sheet_update,
    _student_for,
)


def install(mcp) -> None:
    @mcp.custom_route("/battle/v1/create", methods=["POST", "OPTIONS"])
    async def create_account(request: Request):
        if request.method == "OPTIONS":
            return _json({"ok": True})
        try:
            body = await request.json()
        except Exception:
            body = {}

        username = _normalize_username(body.get("username"))
        pin = str(body.get("pin") or "").strip()
        avatar = str(body.get("avatar") or "🥷🏻")[:16]

        if not re.fullmatch(r"[a-z0-9._-]{4,20}", username):
            return _json({"ok": False, "error": "invalid_username"}, 400)
        if not re.fullmatch(r"\d{6}", pin):
            return _json({"ok": False, "error": "invalid_pin"}, 400)

        accounts = _accounts()
        if any(a["username"] == username for a in accounts):
            return _json({"ok": False, "error": "username_taken"}, 409)

        account_id = str(uuid4())
        salt = _b64(secrets.token_bytes(16))
        now = _now()
        _sheet_append(
            "CUENTAS!A:M",
            [account_id, username, salt, _pin_hash(pin, salt), "", "", avatar, now, now, True, 0, "", ""],
        )
        return _json({"ok": True, "account_created": True, "username": username})

    @mcp.custom_route("/battle/v1/claim", methods=["POST", "OPTIONS"])
    async def claim_identity(request: Request):
        if request.method == "OPTIONS":
            return _json({"ok": True})
        account = _auth(request)
        if not account:
            return _json({"ok": False, "error": "unauthorized"}, 401)
        if account.get("section") or account.get("display_name"):
            return _json({"ok": False, "error": "identity_already_claimed"}, 409)

        try:
            body = await request.json()
        except Exception:
            body = {}
        section = _normalize_section(body.get("section"))
        if section not in SECTIONS:
            return _json({"ok": False, "error": "invalid_section"}, 400)

        student_key = ""
        if section in SCHOOL_SECTIONS:
            student_key = str(body.get("student_key") or "").strip()
            student = _student_for(section, student_key)
            if not student:
                return _json({"ok": False, "error": "invalid_student"}, 400)
            if any(a.get("student_key") == student_key and a["active"] for a in _accounts()):
                return _json({"ok": False, "error": "student_taken"}, 409)
            display_name = student["display_name"]
        else:
            display_name = _clean_public_name(body.get("display_name"))
            if not display_name:
                return _json({"ok": False, "error": "invalid_display_name"}, 400)

        row = account["row"]
        _sheet_update(f"CUENTAS!E{row}:G{row}", [[display_name, section, account.get("avatar") or "🥷🏻"]])
        _sheet_update(f"CUENTAS!M{row}", [[student_key]])
        refreshed = next(a for a in _accounts() if a["account_id"] == account["account_id"])
        return _json({"ok": True, "profile": _public(refreshed)})

    print("BATALLA MATEMÁTICA: flujo /create + /claim instalado.", flush=True)
