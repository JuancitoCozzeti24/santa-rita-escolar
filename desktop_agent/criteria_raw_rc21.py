from __future__ import annotations

from typing import Any

import performance_plan as base
import performance_plan_rc18 as rc18


PerformancePlanError = base.PerformancePlanError


def _parent_id(client, row: dict[str, Any]) -> int | None:
    try:
        raw = client._criterion_parent(row)
    except Exception:
        raw = None
    if raw in (None, "", 0, "0"):
        for key in (
            "idpadre", "idPadre", "ID_PADRE",
            "idContenidoPadre", "ID_CONTENIDO_PADRE",
            "ID_CONTENIDO_REF", "idContenidoRef", "id_contenido_ref",
            "parent_id", "parentId",
        ):
            raw = row.get(key)
            if raw not in (None, "", 0, "0"):
                break
    try:
        value = int(raw)
    except Exception:
        return None
    return value if value > 0 else None


def _criteria_rows_combined(client, api_context: dict[str, Any]) -> list[Any]:
    """RC21: combina TODA la respuesta cruda del modal con criteria de la libreta.

    El despliegue actual de SIEweb puede devolver resCriterios aplanado, sin children y
    con NIVEL=1 para nodos de distinta naturaleza. Por eso no inferimos capacidad por
    NIVEL ni por children. Buscamos la descripción real y su ID en todas las estructuras
    que SIEweb ya entrega, incluida la fuente que usó históricamente el complemento.
    """
    extra = {"idPeriodoAnt": int(api_context.get("idPeriodoAnt") or 0)}
    raw = client.get_criteria(
        class_id=int(api_context["idClase"]),
        class_period_id=int(api_context["idClasePeriodo"]),
        root_content_id=int(api_context["idContenido"]),
        id_ambito=int(api_context["idAmbito"]),
        extra_params=extra,
    )

    rows: list[dict[str, Any]] = []
    try:
        rows.extend([row for row in client._walk_dicts(raw) if isinstance(row, dict)])
    except Exception:
        pass

    # Este es el origen probado por los one-shot del complemento para resolver
    # capacidades y desempeños: get_gradebook_summary().criteria.
    try:
        summary = client.get_gradebook_summary(
            class_period_id=int(api_context["idClasePeriodo"]),
            root_content_id=int(api_context["idContenido"]),
            extra_params=extra,
        )
        rows.extend([row for row in (summary.get("criteria") or []) if isinstance(row, dict)])
    except Exception:
        pass

    useful: list[dict[str, Any]] = []
    seen: set[tuple[Any, str, Any]] = set()
    for row in rows:
        text = rc18._criterion_text(client, row)
        cid = rc18._criterion_id(client, row)
        parent = _parent_id(client, row)
        if not text or not cid:
            continue
        key = (cid, base._canon(text), parent)
        if key in seen:
            continue
        seen.add(key)
        useful.append(row)

    if not useful:
        raise PerformancePlanError(
            "SIEweb no expuso filas de criterios identificables ni en la respuesta cruda "
            "ni en el resumen de la libreta. No se modificó nada."
        )
    return useful


def _resolve_capacity_anywhere(client, rows: list[Any], description: str) -> dict[str, Any]:
    wanted = base._canon(description)
    candidates: list[dict[str, Any]] = []
    seen_ids: set[int] = set()

    # Primero exactitud textual. No filtramos NIVEL: el despliegue actual lo reporta
    # de forma inconsistente y esa fue la causa de RC17-RC20.
    for row in rows:
        if not isinstance(row, dict):
            continue
        cid = rc18._criterion_id(client, row)
        text = rc18._criterion_text(client, row)
        if not cid or not text or cid in seen_ids:
            continue
        if base._canon(text) == wanted:
            seen_ids.add(cid)
            candidates.append(row)

    if len(candidates) == 1:
        return candidates[0]
    if len(candidates) > 1:
        ids = [rc18._criterion_id(client, row) for row in candidates]
        raise PerformancePlanError(
            f"La capacidad {description!r} apareció con varios IDs en SIEweb: {ids}. "
            "No se modificó nada."
        )

    # Respaldo conservador para pequeñas diferencias de redacción.
    ranked: list[tuple[float, str, dict[str, Any], str]] = []
    seen_ids.clear()
    for row in rows:
        if not isinstance(row, dict):
            continue
        cid = rc18._criterion_id(client, row)
        text = rc18._criterion_text(client, row)
        if not cid or not text or cid in seen_ids:
            continue
        seen_ids.add(cid)
        score, mode = rc18._score(description, text)
        ranked.append((score, mode, row, text))
    ranked.sort(key=lambda item: item[0], reverse=True)

    if ranked:
        best_score, best_mode, best_row, _ = ranked[0]
        second_score = ranked[1][0] if len(ranked) > 1 else 0.0
        if best_mode in {"prefix", "token-containment"} and best_score >= 0.95:
            tied = [item for item in ranked if abs(item[0] - best_score) < 1e-9]
            if len(tied) == 1:
                return best_row
        if best_score >= 0.86 and (best_score - second_score) >= 0.10:
            return best_row

    top = " | ".join(
        f"{score:.3f}: {text} [id={rc18._criterion_id(client, row)}]"
        for score, _mode, row, text in ranked[:10]
    )
    raise PerformancePlanError(
        "No pude localizar de forma única la capacidad en los datos REALES de SIEweb. "
        f"Solicitada={description!r}. Mejores coincidencias: {top or '(ninguna)'}. "
        "No se modificó nada."
    )


def _find_performance_anywhere(
    client,
    rows: list[Any],
    *,
    description: str,
    parent_id: int,
) -> list[dict[str, Any]]:
    wanted = base._canon(description)
    with_parent: list[dict[str, Any]] = []
    exact_anywhere: list[dict[str, Any]] = []
    seen: set[int] = set()

    for row in rows:
        if not isinstance(row, dict):
            continue
        cid = rc18._criterion_id(client, row)
        text = rc18._criterion_text(client, row)
        if not cid or not text or cid in seen:
            continue
        if base._canon(text) != wanted:
            continue
        seen.add(cid)
        exact_anywhere.append(row)
        if _parent_id(client, row) == int(parent_id):
            with_parent.append(row)

    if with_parent:
        return with_parent
    # Solo aceptamos ausencia de padre cuando el texto exacto es globalmente único.
    # Esto permite leer despliegues donde el resumen omite ID_CONTENIDO_REF, sin
    # arriesgar asociar un desempeño homónimo a otra capacidad.
    if len(exact_anywhere) == 1:
        return exact_anywhere
    return []


def install() -> None:
    rc18._criteria_editor_rows = _criteria_rows_combined
    rc18._resolve_capacity_from_editor = _resolve_capacity_anywhere
    rc18._find_exact_performance = _find_performance_anywhere
