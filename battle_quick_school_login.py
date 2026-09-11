from __future__ import annotations

import re
import secrets
from uuid import uuid4

from starlette.requests import Request

import battle_accounts as ba


def _school_roster_full():
    rows = ba._sheet_get_from(ba.ROSTER_SHEET_ID, "ALUMNOS!A2:G1000")
    out = []
    for raw in rows:
        row = list(raw) + [""] * (7 - len(raw))
        student_key = str(row[0]).strip()
        full_name = " ".join(str(row[1] or "").split()).strip()
        grade = re.search(r"[25]", str(row[2] or ""))
        section_letter = ba._norm_text(row[3])
        active = ba._norm_text(row[5]) in {"ACTIVO", "ACTIVE", "SI", "TRUE", "1"}
        if not student_key or not full_name or not grade or section_letter not in {"A", "B"} or not active:
            continue
        section = f"{grade.group(0)}{section_letter}"
        if section not in ba.SCHOOL_SECTIONS:
            continue
        out.append({"student_key": student_key, "full_name": full_name, "section": section})
    return out


def _username_from_name(full_name: str, student_key: str) -> str:
    base = ba._norm_text(full_name).lower().replace(" ", ".")
    base = re.sub(r"[^a-z0-9._-]", "", base).strip(".")[:16] or "alumno"
    return f"{base}.{str(student_key)[-3:].lower()}"[:20]


def install(mcp) -> None:
    @mcp.custom_route("/battle/v1/school-login", methods=["POST", "OPTIONS"])
    async def school_login(request: Request):
        if request.method == "OPTIONS":
            return ba._json({"ok": True})
        try:
            body = await request.json()
        except Exception:
            body = {}
        entered = " ".join(str(body.get("full_name") or "").split()).strip()
        if len(entered) < 5:
            return ba._json({"ok": False, "error": "name_required"}, 400)

        wanted = ba._norm_text(entered)
        matches = [r for r in _school_roster_full() if ba._norm_text(r["full_name"]) == wanted]
        if not matches:
            return ba._json({"ok": False, "error": "student_not_found"}, 404)
        if len(matches) > 1:
            return ba._json({"ok": False, "error": "duplicate_name"}, 409)
        student = matches[0]

        with ba._lock:
            accounts = ba._accounts()
            account = next((a for a in accounts if a.get("student_key") == student["student_key"] and a["active"]), None)
            if account is None:
                username = _username_from_name(student["full_name"], student["student_key"])
                taken = {a["username"] for a in accounts}
                if username in taken:
                    username = f"u{secrets.token_hex(4)}"[:20]
                account_id = str(uuid4())
                salt = ba._b64(secrets.token_bytes(16))
                hidden_pin = f"{secrets.randbelow(1000000):06d}"
                now = ba._now()
                ba._sheet_append(
                    "CUENTAS!A:M",
                    [account_id, username, salt, ba._pin_hash(hidden_pin, salt), student["full_name"], student["section"], "⚡", now, now, True, 0, "", student["student_key"]],
                )
                account = next(a for a in ba._accounts() if a["account_id"] == account_id)
            else:
                ba._sheet_update(f"CUENTAS!I{account['row']}", [[ba._now()]])

        return ba._json({"ok": True, "token": ba._token(account["account_id"], account["username"]), "profile": ba._public(account)})

    print("BATALLA MATEMÁTICA: ingreso directo por nombre completo escolar activado.", flush=True)
