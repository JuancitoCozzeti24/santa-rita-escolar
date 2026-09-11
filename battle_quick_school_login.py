from __future__ import annotations

import re
import secrets
import unicodedata
from uuid import uuid4

from starlette.requests import Request

import battle_accounts as ba


def _norm_name(value: str) -> str:
    text = unicodedata.normalize("NFKD", str(value or "").strip())
    text = "".join(ch for ch in text if not unicodedata.combining(ch))
    text = re.sub(r"[^A-Za-z0-9]+", " ", text).strip().lower()
    return " ".join(text.split())


def _clean_name(value: str) -> str:
    text = " ".join(str(value or "").split()).strip()
    return text[:40]


def _username_from_name(full_name: str, used: set[str]) -> str:
    base = _norm_name(full_name).replace(" ", ".")
    base = re.sub(r"[^a-z0-9._-]", "", base).strip(".")[:18] or "jugador"
    username = base
    if username not in used:
        return username
    for i in range(2, 1000):
        candidate = (base[:16] + str(i))[:20]
        if candidate not in used:
            return candidate
    return (base[:12] + secrets.token_hex(3))[:20]


def install(mcp) -> None:
    @mcp.custom_route("/battle/v1/school-login", methods=["POST", "OPTIONS"])
    async def school_login(request: Request):
        if request.method == "OPTIONS":
            return ba._json({"ok": True})
        try:
            body = await request.json()
        except Exception:
            body = {}

        entered = _clean_name(body.get("full_name"))
        if len(entered) < 2:
            return ba._json({"ok": False, "error": "name_required"}, 400)

        wanted = _norm_name(entered)
        free_key = "FREE:" + wanted

        with ba._lock:
            accounts = ba._accounts()
            account = next(
                (a for a in accounts if a["active"] and str(a.get("student_key") or "") == free_key),
                None,
            )
            if account is None:
                used = {a["username"] for a in accounts}
                username = _username_from_name(entered, used)
                account_id = str(uuid4())
                salt = ba._b64(secrets.token_bytes(16))
                hidden_pin = f"{secrets.randbelow(1000000):06d}"
                now = ba._now()
                ba._sheet_append(
                    "CUENTAS!A:M",
                    [
                        account_id,
                        username,
                        salt,
                        ba._pin_hash(hidden_pin, salt),
                        entered,
                        ba.PUBLIC_SECTION,
                        "⚡",
                        now,
                        now,
                        True,
                        0,
                        "",
                        free_key,
                    ],
                )
                account = next(a for a in ba._accounts() if a["account_id"] == account_id)
            else:
                if account.get("display_name") != entered:
                    ba._sheet_update(f"CUENTAS!E{account['row']}", [[entered]])
                    account = next(a for a in ba._accounts() if a["account_id"] == account["account_id"])
                ba._sheet_update(f"CUENTAS!I{account['row']}", [[ba._now()]])

        return ba._json({
            "ok": True,
            "token": ba._token(account["account_id"], account["username"]),
            "profile": ba._public(account),
        })

    print("BATALLA MATEMÁTICA: ingreso libre por nombre sin PIN ni lista activado.", flush=True)
