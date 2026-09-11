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


def _clean_piece(value: str) -> str:
    text = " ".join(str(value or "").split()).strip()
    if not re.fullmatch(r"[A-Za-zÁÉÍÓÚÜÑáéíóúüñ'’-]{2,24}", text):
        return ""
    return text.title()


def _slug(value: str) -> str:
    text = _norm_name(value).replace(" ", ".")
    text = re.sub(r"[^a-z0-9._-]", "", text)
    return text[:18] or "jugador"


def install(mcp) -> None:
    @mcp.custom_route("/battle/v1/simple-access", methods=["POST", "OPTIONS"])
    async def simple_access(request: Request):
        if request.method == "OPTIONS":
            return ba._json({"ok": True})
        try:
            body = await request.json()
        except Exception:
            body = {}

        first = _clean_piece(body.get("first_name"))
        surname = _clean_piece(body.get("surname"))
        pin = str(body.get("pin") or "").strip()
        if not first or not surname:
            return ba._json({"ok": False, "error": "invalid_name"}, 400)
        if not re.fullmatch(r"\d{6}", pin):
            return ba._json({"ok": False, "error": "invalid_pin"}, 400)

        display_name = f"{first} {surname}"
        simple_key = "SIMPLE:" + _norm_name(display_name)
        accounts = [a for a in ba._accounts() if a["active"] and str(a.get("student_key") or "") == simple_key]

        for account in accounts:
            if ba.hmac.compare_digest(account["pin_hash"], ba._pin_hash(pin, account["pin_salt"])):
                ba._sheet_update(f"CUENTAS!I{account['row']}", [[ba._now()]])
                return ba._json({
                    "ok": True,
                    "created": False,
                    "token": ba._token(account["account_id"], account["username"]),
                    "profile": ba._public(account),
                })

        with ba._lock:
            existing = ba._accounts()
            base = _slug(display_name)
            used = {a["username"] for a in existing}
            username = base
            if username in used:
                for i in range(2, 1000):
                    candidate = (base[:16] + str(i))[:20]
                    if candidate not in used:
                        username = candidate
                        break
                else:
                    username = (base[:12] + secrets.token_hex(3))[:20]

            account_id = str(uuid4())
            salt = ba._b64(secrets.token_bytes(16))
            now = ba._now()
            ba._sheet_append(
                "CUENTAS!A:M",
                [account_id, username, salt, ba._pin_hash(pin, salt), display_name,
                 ba.PUBLIC_SECTION, "⚡", now, now, True, 0, "", simple_key],
            )

        account = next(a for a in ba._accounts() if a["account_id"] == account_id)
        return ba._json({
            "ok": True,
            "created": True,
            "token": ba._token(account["account_id"], account["username"]),
            "profile": ba._public(account),
        })

    print("BATALLA MATEMÁTICA: acceso simple nombre+apellido+PIN activo.", flush=True)
