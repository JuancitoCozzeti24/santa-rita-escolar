from __future__ import annotations

import difflib
from typing import Any

import performance_plan as base


PerformancePlanError = base.PerformancePlanError


def _criterion_text(item: dict[str, Any]) -> str:
    return str(
        item.get("descripcion")
        or item.get("desc")
        or item.get("nombre")
        or item.get("DESCRIPCION")
        or ""
    ).strip()


def _tokens(value: str) -> set[str]:
    return {token for token in base._canon(value).split() if token}


def _capacity_candidates(summary: dict[str, Any]) -> list[dict[str, Any]]:
    out: list[dict[str, Any]] = []
    for item in summary.get("criteria") or []:
        if not isinstance(item, dict):
            continue
        try:
            level = int(item.get("nivelEva") or 0)
        except Exception:
            level = 0
        if level != 2:
            continue
        text = _criterion_text(item)
        if text:
            out.append(item)
    return out


def _score(wanted: str, candidate: str) -> tuple[float, str]:
    a = base._canon(wanted)
    b = base._canon(candidate)
    if not a or not b:
        return 0.0, "empty"
    if a == b:
        return 1.0, "exact"

    ta, tb = _tokens(a), _tokens(b)
    if ta and tb:
        common = ta & tb
        union = ta | tb
        jaccard = len(common) / max(1, len(union))
        containment = len(common) / max(1, min(len(ta), len(tb)))
    else:
        jaccard = 0.0
        containment = 0.0

    if len(ta) >= 4 and len(tb) >= 4 and (ta <= tb or tb <= ta):
        return 0.985, "token-containment"
    if min(len(a), len(b)) >= 18 and (a.startswith(b) or b.startswith(a)):
        return 0.975, "prefix"

    seq = difflib.SequenceMatcher(None, a, b).ratio()
    score = 0.52 * seq + 0.30 * containment + 0.18 * jaccard
    return score, "fuzzy"


def find_capacity_robust(summary: dict[str, Any], description: str) -> dict[str, Any]:
    candidates = _capacity_candidates(summary)
    if not candidates:
        raise PerformancePlanError("SIEweb no devolvió capacidades (nivelEva=2) en la libreta actual.")

    ranked: list[tuple[float, str, dict[str, Any], str]] = []
    for item in candidates:
        text = _criterion_text(item)
        score, mode = _score(description, text)
        ranked.append((score, mode, item, text))
    ranked.sort(key=lambda row: row[0], reverse=True)

    best_score, best_mode, best_item, best_text = ranked[0]
    second_score = ranked[1][0] if len(ranked) > 1 else 0.0

    # Exact/prefix/token containment are safe enough if unique. Fuzzy matches require
    # a high score and a clear margin to avoid attaching a desempeño to the wrong capacity.
    if best_mode in {"exact", "prefix", "token-containment"}:
        same_strength = [row for row in ranked if abs(row[0] - best_score) < 1e-9]
        if len(same_strength) == 1:
            return best_item
    elif best_score >= 0.82 and (best_score - second_score) >= 0.08:
        return best_item

    available = " | ".join(
        f"{idx+1}. {_criterion_text(item)}"
        for idx, item in enumerate(candidates[:12])
    )
    top = " | ".join(
        f"{score:.3f}: {text}"
        for score, _mode, _item, text in ranked[:4]
    )
    raise PerformancePlanError(
        "La capacidad del plan no pudo asociarse con suficiente seguridad a SIEweb. "
        f"Solicitada={description!r}. Mejores coincidencias: {top}. "
        f"Capacidades disponibles: {available}"
    )
