from __future__ import annotations

import hmac
import re
import secrets
from uuid import uuid4

from starlette.requests import Request

import battle_accounts as ba


def install(mcp) -> None:
    @mcp.custom_route("/battle/v1/create", methods=["POST", "OPTIONS"])
    async def create_account(request: Request):
        if request.method == "OPTIONS":
            return ba._json({"ok": True})
        try:
            body = await request.json()
        except Exception:
            body = {}
        username = ba._normalize_username(body.get("username"))
        pin = str(body.get("pin") or "").strip()
        avatar = str(body.get("avatar") or "🥷🏻")[:16]
        if not re.fullmatch(r"[a-z0-9._-]{4,20}", username):
            return ba._json({"ok": False, "error": "invalid_username"}, 400)
        if not re.fullmatch(r"\d{6}", pin):
            return ba._json({"ok": False, "error": "invalid_pin"}, 400)

        with ba._lock:
            accounts = ba._accounts()
            if any(a["username"] == username for a in accounts):
                return ba._json({"ok": False, "error": "username_taken"}, 409)
            account_id = str(uuid4())
            salt = ba._b64(secrets.token_bytes(16))
            now = ba._now()
            ba._sheet_append(
                "CUENTAS!A:M",
                [account_id, username, salt, ba._pin_hash(pin, salt), "", "", avatar,
                 now, now, True, 0, "", ""],
            )
        account = next(a for a in ba._accounts() if a["account_id"] == account_id)
        return ba._json({"ok": True, "created": True, "profile": ba._public(account)})

    @mcp.custom_route("/battle/v1/claim", methods=["POST", "OPTIONS"])
    async def claim_identity(request: Request):
        if request.method == "OPTIONS":
            return ba._json({"ok": True})
        account = ba._auth(request)
        if not account:
            return ba._json({"ok": False, "error": "unauthorized"}, 401)
        if account.get("section") and account.get("display_name"):
            return ba._json({"ok": True, "already_claimed": True, "profile": ba._public(account)})
        try:
            body = await request.json()
        except Exception:
            body = {}
        section = ba._normalize_section(body.get("section"))
        avatar = str(body.get("avatar") or account.get("avatar") or "🥷🏻")[:16]
        student_key = str(body.get("student_key") or "").strip()
        if section not in ba.SECTIONS:
            return ba._json({"ok": False, "error": "invalid_section"}, 400)

        if section in ba.SCHOOL_SECTIONS:
            student = ba._student_for(section, student_key)
            if not student:
                return ba._json({"ok": False, "error": "invalid_student"}, 400)
            name = student["display_name"]
            with ba._lock:
                accounts = ba._accounts()
                if any(a.get("student_key") == student_key and a["active"] and a["account_id"] != account["account_id"] for a in accounts):
                    return ba._json({"ok": False, "error": "student_taken"}, 409)
        else:
            student_key = ""
            name = ba._clean_public_name(body.get("display_name"))
            if not name:
                return ba._json({"ok": False, "error": "invalid_display_name"}, 400)

        row = account["row"]
        ba._sheet_update(f"CUENTAS!E{row}:G{row}", [[name, section, avatar]])
        ba._sheet_update(f"CUENTAS!M{row}", [[student_key]])
        updated = next(a for a in ba._accounts() if a["account_id"] == account["account_id"])
        return ba._json({"ok": True, "claimed": True, "profile": ba._public(updated)})

    print("BATALLA MATEMÁTICA v17: alta previa + selección de grupo/identidad instaladas.", flush=True)
