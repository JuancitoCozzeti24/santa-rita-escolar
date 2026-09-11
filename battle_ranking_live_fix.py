from __future__ import annotations

from typing import Any


def install(_mcp=None) -> None:
    import battle_accounts as battle

    def _verified_result_bests() -> dict[str, dict[str, Any]]:
        bests: dict[str, dict[str, Any]] = {}
        try:
            rows = battle._sheet_get("RESULTADOS!A2:L10000")
        except Exception:
            return bests

        for raw in rows:
            row = list(raw) + [""] * (12 - len(raw))
            account_id = str(row[1] or "").strip()
            if not account_id:
                continue
            verified = str(row[11] or "").strip().lower()
            if verified in {"false", "0", "no"}:
                continue
            try:
                score = int(float(row[5] or 0))
            except Exception:
                continue
            if score <= 0:
                continue
            played_at = str(row[8] or "")
            current = bests.get(account_id)
            if current is None or score > current["score"] or (
                score == current["score"] and played_at and played_at < current["at"]
            ):
                bests[account_id] = {"score": score, "at": played_at or "9999"}
        return bests

    def _leaderboard(section: str = "", limit: int = 100) -> list[dict[str, Any]]:
        result_bests = _verified_result_bests()
        accounts: list[dict[str, Any]] = []
        for original in battle._accounts():
            if not original["active"]:
                continue
            if section and original["section"] != section:
                continue
            account = dict(original)
            result_best = result_bests.get(account["account_id"])
            if result_best and int(result_best["score"]) > int(account.get("best_score") or 0):
                account["best_score"] = int(result_best["score"])
                account["best_score_at"] = str(result_best["at"] or account.get("best_score_at") or "")
            if int(account.get("best_score") or 0) > 0:
                accounts.append(account)

        accounts.sort(
            key=lambda account: (
                -int(account.get("best_score") or 0),
                str(account.get("best_score_at") or "9999"),
            )
        )
        return [
            {"rank": i + 1, **battle._public(account)}
            for i, account in enumerate(accounts[:limit])
        ]

    battle._leaderboard = _leaderboard
    print(
        "BATALLA MATEMÁTICA: ranking live fix activo; usa el máximo real entre CUENTAS y RESULTADOS.",
        flush=True,
    )
