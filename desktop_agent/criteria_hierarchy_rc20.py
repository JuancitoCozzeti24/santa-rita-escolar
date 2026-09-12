from __future__ import annotations

from typing import Any

import performance_plan as base
import performance_plan_rc18 as rc18


PerformancePlanError = base.PerformancePlanError


def _children(row: dict[str, Any]) -> list[dict[str, Any]]:
    value = row.get("children")
    if not isinstance(value, list):
        return []
    return [item for item in value if isinstance(item, dict)]


def _parent_id(row: dict[str, Any]) -> int | None:
    for key in (
        "ID_PADRE",
        "idPadre",
        "idpadre",
        "ID_CONTENIDO_PADRE",
        "idContenidoPadre",
        "id_contenido_padre",
        "parent_id",
        "parentId",
    ):
        raw = row.get(key)
        if raw in (None, "", 0, "0"):
            continue
        try:
            value = int(raw)
        except Exception:
            continue
        if value > 0:
            return value
    return None


def _capacity_candidates(client, rows: list[Any]) -> list[dict[str, Any]]:
    """Obtiene capacidades por JERARQUÍA, no por el NIVEL defectuoso de SIEweb.

    En el despliegue observado, resCriterios puede devolver NIVEL=1 tanto para
    competencias como para sus hijos. Sin embargo, la estructura children conserva
    el contrato real Competencia -> Capacidad -> Desempeño.
    """
    candidates: list[dict[str, Any]] = []
    seen: set[int] = set()

    # Camino principal: los hijos directos de cada nodo raíz son capacidades.
    for root in rows:
        if not isinstance(root, dict):
            continue
        for child in _children(root):
            cid = rc18._criterion_id(client, child)
            text = rc18._criterion_text(client, child)
            if cid and text and cid not in seen:
                seen.add(cid)
                candidates.append(child)

    if candidates:
        return candidates

    # Respaldo: algunos payloads pueden venir aplanados. En ese caso, considera
    # capacidades los nodos cuyo padre coincide con un ID de nodo raíz.
    root_ids = {
        cid
        for row in rows
        if isinstance(row, dict)
        for cid in [rc18._criterion_id(client, row)]
        if cid
    }
    for _path, row in client._walk_criterion_tree(rows):
        if not isinstance(row, dict):
            continue
        cid = rc18._criterion_id(client, row)
        text = rc18._criterion_text(client, row)
        if not cid or not text or cid in root_ids or cid in seen:
            continue
        if _parent_id(row) in root_ids:
            seen.add(cid)
            candidates.append(row)

    return candidates


def resolve_capacity_structural(client, rows: list[Any], description: str) -> dict[str, Any]:
    candidates = _capacity_candidates(client, rows)
    if not candidates:
        roots = []
        for row in rows[:12]:
            if isinstance(row, dict):
                roots.append(
                    f"{rc18._criterion_text(client, row)} (hijos={len(_children(row))})"
                )
        raise PerformancePlanError(
            "El árbol resCriterios no expuso capacidades por jerarquía. "
            f"Raíces observadas: {' | '.join(roots) or '(ninguna)'}"
        )

    ranked: list[tuple[float, str, dict[str, Any], str]] = []
    for row in candidates:
        text = rc18._criterion_text(client, row)
        score, mode = rc18._score(description, text)
        ranked.append((score, mode, row, text))
    ranked.sort(key=lambda item: item[0], reverse=True)

    best_score, best_mode, best_row, _ = ranked[0]
    second_score = ranked[1][0] if len(ranked) > 1 else 0.0
    if best_mode in {"exact", "prefix", "token-containment"}:
        tied = [item for item in ranked if abs(item[0] - best_score) < 1e-9]
        if len(tied) == 1:
            return best_row
    elif best_score >= 0.82 and best_score - second_score >= 0.08:
        return best_row

    available = " | ".join(
        f"{idx + 1}. {rc18._criterion_text(client, row)}"
        for idx, row in enumerate(candidates[:16])
    )
    top = " | ".join(
        f"{score:.3f}: {text}" for score, _mode, _row, text in ranked[:6]
    )
    raise PerformancePlanError(
        "La capacidad del plan no pudo asociarse de forma única por la jerarquía real. "
        f"Solicitada={description!r}. Mejores coincidencias: {top}. "
        f"Capacidades estructurales disponibles: {available}"
    )


def find_exact_performance_structural(
    client,
    rows: list[Any],
    *,
    description: str,
    parent_id: int,
) -> list[dict[str, Any]]:
    """Busca un desempeño debajo de la capacidad por relación padre/hijo.

    No usa level=3 porque el mismo payload observado puede etiquetar todos los nodos
    con NIVEL=1 aun cuando su jerarquía children sea correcta.
    """
    wanted = base._canon(description)
    matches: list[dict[str, Any]] = []
    seen: set[int] = set()

    capacity_node: dict[str, Any] | None = None
    for _path, row in client._walk_criterion_tree(rows):
        if not isinstance(row, dict):
            continue
        if rc18._criterion_id(client, row) == int(parent_id):
            capacity_node = row
            break

    if capacity_node is not None:
        for child in _children(capacity_node):
            if base._canon(rc18._criterion_text(client, child)) != wanted:
                continue
            cid = rc18._criterion_id(client, child) or id(child)
            if cid not in seen:
                seen.add(cid)
                matches.append(child)

    # Respaldo para payload aplanado.
    for _path, row in client._walk_criterion_tree(rows):
        if not isinstance(row, dict):
            continue
        if _parent_id(row) != int(parent_id):
            continue
        if base._canon(rc18._criterion_text(client, row)) != wanted:
            continue
        cid = rc18._criterion_id(client, row) or id(row)
        if cid not in seen:
            seen.add(cid)
            matches.append(row)

    return matches


def install() -> None:
    # El resto del motor RC18 (contexto dinámico, creación verificada y lote masivo)
    # permanece intacto. Solo corregimos cómo se interpreta la jerarquía de criterios.
    rc18._resolve_capacity_from_editor = resolve_capacity_structural
    rc18._find_exact_performance = find_exact_performance_structural
