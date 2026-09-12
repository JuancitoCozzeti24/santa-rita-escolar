from __future__ import annotations

import difflib
from typing import Any

import launcher_v100rc11 as rc11
import performance_plan as base
import performance_plan_rc16 as rc16
import verified_writer_bridge as writer


PerformancePlanError = base.PerformancePlanError


def _criterion_text(client, row: dict[str, Any]) -> str:
    try:
        return str(client._criterion_description(row) or "").strip()
    except Exception:
        return str(
            row.get("DESCRIPCION")
            or row.get("descripcion")
            or row.get("desc")
            or row.get("nombre")
            or ""
        ).strip()


def _criterion_id(client, row: dict[str, Any]) -> int | None:
    try:
        raw = client._criterion_content_id(row)
    except Exception:
        raw = (
            row.get("ID_CONTENIDO")
            or row.get("idContenido")
            or row.get("id")
            or row.get("ID")
        )
    try:
        value = int(raw)
    except Exception:
        return None
    return value if value > 0 else None


def _criterion_level(client, row: dict[str, Any]) -> int:
    try:
        raw = client._criterion_level(row)
    except Exception:
        raw = row.get("nivelEva") or row.get("NIVEL") or row.get("nivel") or 0
    try:
        return int(raw or 0)
    except Exception:
        return 0


def _tokens(value: str) -> set[str]:
    return {token for token in base._canon(value).split() if token}


def _score(wanted: str, candidate: str) -> tuple[float, str]:
    a = base._canon(wanted)
    b = base._canon(candidate)
    if not a or not b:
        return 0.0, "empty"
    if a == b:
        return 1.0, "exact"

    ta, tb = _tokens(a), _tokens(b)
    common = ta & tb
    union = ta | tb
    containment = len(common) / max(1, min(len(ta), len(tb))) if ta and tb else 0.0
    jaccard = len(common) / max(1, len(union)) if union else 0.0

    if len(ta) >= 4 and len(tb) >= 4 and (ta <= tb or tb <= ta):
        return 0.985, "token-containment"
    if min(len(a), len(b)) >= 18 and (a.startswith(b) or b.startswith(a)):
        return 0.975, "prefix"

    seq = difflib.SequenceMatcher(None, a, b).ratio()
    return 0.52 * seq + 0.30 * containment + 0.18 * jaccard, "fuzzy"


def _resolve_capacity_from_editor(client, rows: list[Any], description: str) -> dict[str, Any]:
    """Resuelve una capacidad desde el árbol REAL del modal de criterios.

    SIEweb expone Competencia -> Capacidad -> Desempeño en
    dataInicialPesosCriterios/json.resCriterios. El resumen de la libreta puede no
    incluir capacidades todavía; por eso RC18 deja de buscarlas en summary.criteria.
    """
    candidates: list[dict[str, Any]] = []
    for _path, row in client._walk_criterion_tree(rows):
        if not isinstance(row, dict):
            continue
        if _criterion_level(client, row) != 2:
            continue
        text = _criterion_text(client, row)
        cid = _criterion_id(client, row)
        if text and cid:
            candidates.append(row)

    if not candidates:
        levels: dict[int, int] = {}
        samples: list[str] = []
        for _path, row in client._walk_criterion_tree(rows):
            if not isinstance(row, dict):
                continue
            level = _criterion_level(client, row)
            levels[level] = levels.get(level, 0) + 1
            text = _criterion_text(client, row)
            if text and len(samples) < 12:
                samples.append(f"N{level}: {text}")
        detail = " | ".join(samples) if samples else "(sin descripciones)"
        raise PerformancePlanError(
            "El árbol real de criterios no contiene capacidades identificables en nivel 2. "
            f"Niveles observados={levels}. Muestra: {detail}"
        )

    ranked: list[tuple[float, str, dict[str, Any], str]] = []
    for row in candidates:
        text = _criterion_text(client, row)
        score, mode = _score(description, text)
        ranked.append((score, mode, row, text))
    ranked.sort(key=lambda item: item[0], reverse=True)

    best_score, best_mode, best_row, _best_text = ranked[0]
    second_score = ranked[1][0] if len(ranked) > 1 else 0.0

    if best_mode in {"exact", "prefix", "token-containment"}:
        tied = [row for row in ranked if abs(row[0] - best_score) < 1e-9]
        if len(tied) == 1:
            return best_row
    elif best_score >= 0.82 and (best_score - second_score) >= 0.08:
        return best_row

    top = " | ".join(f"{score:.3f}: {text}" for score, _mode, _row, text in ranked[:6])
    available = " | ".join(
        f"{idx + 1}. {_criterion_text(client, row)}"
        for idx, row in enumerate(candidates[:12])
    )
    raise PerformancePlanError(
        "La capacidad del plan no pudo asociarse de forma única al árbol real de criterios. "
        f"Solicitada={description!r}. Mejores coincidencias: {top}. "
        f"Capacidades disponibles: {available}"
    )


def _criteria_editor_rows(client, api_context: dict[str, Any]) -> list[Any]:
    extra = {"idPeriodoAnt": int(api_context.get("idPeriodoAnt") or 0)}
    raw = client.get_criteria(
        class_id=int(api_context["idClase"]),
        class_period_id=int(api_context["idClasePeriodo"]),
        root_content_id=int(api_context["idContenido"]),
        id_ambito=int(api_context["idAmbito"]),
        extra_params=extra,
    )
    model = client.extract_criteria_editor_model(raw)
    rows = model.get("rows") or []
    if not isinstance(rows, list) or not rows:
        raise PerformancePlanError("SIEweb devolvió el editor de criterios, pero sin árbol resCriterios utilizable.")
    return rows


def _find_exact_performance(client, rows: list[Any], *, description: str, parent_id: int) -> list[dict[str, Any]]:
    matches = client._find_tree_nodes(
        rows,
        description=description,
        parent_id=parent_id,
        level=3,
    )
    return [row for _path, row in matches]


def preview_plan(page, plan: dict[str, Any]) -> base.PerformancePreview:
    base.validate_plan(plan)
    browser_context = writer.infer_browser_context(page)
    base._target_matches(plan, browser_context)

    client, auth_status = writer._hydrate_client_from_browser(page)
    try:
        live = rc11._capture_current_gradebook_context(page)
        extra = {"idPeriodoAnt": int(live.get("idPeriodoAnt") or 0)}
        before = client.get_gradebook_summary(
            class_period_id=int(live["idClasePeriodo"]),
            root_content_id=int(live["idContenido"]),
            extra_params=extra,
        )
    except Exception as exc:
        raise PerformancePlanError(
            f"No se pudo releer la libreta visible usando sus IDs reales del navegador: {exc}"
        ) from exc

    class_info = before.get("class") or {}
    api_period = int(rc16._ci_get(class_info, "periodo") or browser_context["period"] or 0)
    api_course = str(rc16._ci_get(class_info, "cursocod") or "").strip()
    if api_period != int(browser_context["period"]):
        raise PerformancePlanError(
            f"El período visible/API no coincide ({browser_context['period']} vs {api_period})."
        )
    if api_course and api_course != str(browser_context["course_code"]).strip():
        raise PerformancePlanError(
            f"El curso visible/API no coincide ({browser_context['course_code']} vs {api_course})."
        )

    class_id_raw = rc16._ci_get(class_info, "idClase")
    if class_id_raw in (None, ""):
        class_id_raw = rc16._recursive_ci_get(before, "idClase")
    ambito_raw = rc16._ci_get(class_info, "idAmbito")
    if ambito_raw in (None, ""):
        ambito_raw = rc16._recursive_ci_get(before, "idAmbito")

    api_context = {
        "section": browser_context.get("section"),
        "idAmbito": rc16._as_int(ambito_raw, "idAmbito"),
        "idClase": rc16._as_int(class_id_raw, "idClase"),
        "idClasePeriodo": int(live["idClasePeriodo"]),
        "idContenido": int(live["idContenido"]),
        "periodo": api_period,
        "idPeriodoAnt": int(live.get("idPeriodoAnt") or 0),
        "course": {
            "NOMCLASE": rc16._ci_get(class_info, "cursonom") or "",
            "NOMBRE": rc16._ci_get(class_info, "cursonom") or "",
        },
        "context_source": "live_obtRegistroNotas_plus_criteria_tree_rc18",
    }

    try:
        rows = _criteria_editor_rows(client, api_context)
    except Exception as exc:
        if isinstance(exc, PerformancePlanError):
            raise
        raise PerformancePlanError(f"No se pudo leer el árbol real de criterios de SIEweb: {exc}") from exc

    evidence = plan.get("evidence") or {}
    default_abbr = base._clean(evidence.get("abbreviation")) or base._clean(evidence.get("name"))[:40]
    planned: list[base.PlannedPerformance] = []

    for index, raw in enumerate(plan.get("performances") or [], start=1):
        pid = base._clean(raw.get("id") or f"P{index}").upper()
        capacity = base._clean(raw.get("capacity"))
        description = base._clean(raw.get("description"))
        abbreviation = base._clean(raw.get("abbreviation")) or default_abbr

        cap = _resolve_capacity_from_editor(client, rows, capacity)
        parent_id = _criterion_id(client, cap)
        if not parent_id:
            raise PerformancePlanError(f"La capacidad {capacity!r} no expuso un ID de contenido válido.")

        matches = _find_exact_performance(
            client,
            rows,
            description=description,
            parent_id=parent_id,
        )
        if len(matches) > 1:
            raise PerformancePlanError(
                f"El desempeño {pid} ya aparece duplicado en SIEweb ({len(matches)} coincidencias)."
            )
        existing_id = _criterion_id(client, matches[0]) if len(matches) == 1 else None
        planned.append(
            base.PlannedPerformance(
                plan_id=pid,
                capacity=capacity,
                description=description,
                abbreviation=abbreviation,
                parent_id=parent_id,
                existing_id=existing_id,
            )
        )

    return base.PerformancePreview(
        plan=plan,
        browser_context=browser_context,
        api_context=api_context,
        auth_status=auth_status,
        client=client,
        before=before,
        performances=planned,
    )


def create_missing_performances(preview: base.PerformancePreview) -> dict[str, Any]:
    missing = preview.missing
    if not missing:
        return {
            "created": 0,
            "existing": len(preview.performances),
            "verification": [
                {"id": item.plan_id, "criterion_id": item.existing_id, "ok": True}
                for item in preview.performances
            ],
        }

    ctx = preview.api_context
    extra = {"idPeriodoAnt": int(ctx.get("idPeriodoAnt") or 0)}
    records: list[dict[str, Any]] = []
    expected: list[dict[str, Any]] = []
    for item in missing:
        records.append({
            "ABREVIATURA": item.abbreviation,
            "PESO": 1,
            "SUMATIVO": 0,
            "EXCLUIR": 0,
        })
        expected.append({
            "description": item.description,
            "parent_id": item.parent_id,
            "level": 3,
        })

    try:
        write_result = preview.client.upsert_criteria_verified(
            class_id=int(ctx["idClase"]),
            class_period_id=int(ctx["idClasePeriodo"]),
            root_content_id=int(ctx["idContenido"]),
            id_ambito=int(ctx["idAmbito"]),
            records=records,
            replica={},
            expected=expected,
            extra_params=extra,
            verification_attempts=3,
        )
    except Exception as exc:
        raise PerformancePlanError(f"SIEweb rechazó la creación de desempeños: {exc}") from exc

    # RC18 verifica en el MISMO árbol que edita el modal de criterios. El resumen de
    # la libreta puede omitir capacidades aunque la creación haya sido correcta.
    rows_after = _criteria_editor_rows(preview.client, ctx)
    checks: list[dict[str, Any]] = []
    all_ok = True
    for item in preview.performances:
        cap = _resolve_capacity_from_editor(preview.client, rows_after, item.capacity)
        parent_id = _criterion_id(preview.client, cap)
        matches = _find_exact_performance(
            preview.client,
            rows_after,
            description=item.description,
            parent_id=int(parent_id or 0),
        )
        ok = len(matches) == 1
        checks.append({
            "id": item.plan_id,
            "description": item.description,
            "count": len(matches),
            "criterion_id": _criterion_id(preview.client, matches[0]) if ok else None,
            "ok": ok,
        })
        all_ok = all_ok and ok

    if not all_ok:
        raise PerformancePlanError(
            "La creación terminó, pero el árbol real de criterios no confirmó cada desempeño exactamente una vez."
        )

    return {
        "created": len(missing),
        "existing": len(preview.performances) - len(missing),
        "writer_result": write_result,
        "verification": checks,
    }
