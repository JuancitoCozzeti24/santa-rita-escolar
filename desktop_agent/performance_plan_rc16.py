from __future__ import annotations

from typing import Any

import launcher_v100rc11 as rc11
import performance_plan as base
import verified_writer_bridge as writer


PerformancePlanError = base.PerformancePlanError


def _ci_get(mapping: dict[str, Any], key: str, default: Any = None) -> Any:
    if not isinstance(mapping, dict):
        return default
    wanted = key.lower()
    for k, value in mapping.items():
        if str(k).lower() == wanted:
            return value
    return default


def _recursive_ci_get(value: Any, key: str) -> Any:
    wanted = key.lower()
    if isinstance(value, dict):
        for k, item in value.items():
            if str(k).lower() == wanted and item not in (None, "", [], {}):
                return item
        for item in value.values():
            found = _recursive_ci_get(item, key)
            if found not in (None, "", [], {}):
                return found
    elif isinstance(value, list):
        for item in value:
            found = _recursive_ci_get(item, key)
            if found not in (None, "", [], {}):
                return found
    return None


def _as_int(value: Any, name: str) -> int:
    try:
        out = int(value)
    except Exception as exc:
        raise PerformancePlanError(f"SIEweb no expuso un {name} válido para la libreta visible.") from exc
    if out <= 0:
        raise PerformancePlanError(f"SIEweb no expuso un {name} válido para la libreta visible.")
    return out


def preview_plan(page, plan: dict[str, Any]) -> base.PerformancePreview:
    """RC16: resuelve el contexto desde la petición REAL obtRegistroNotas.

    Evita la tabla histórica S2A/S5A de resolve_class_context y por tanto funciona
    también con S2B, S5B y otras secciones que la pestaña autorizada abra realmente.
    No escribe nada: solo captura IDs, relee la libreta y prepara el plan.
    """
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

    summary_cp = _ci_get(class_info, "idClasePeriodo")
    if summary_cp not in (None, "") and str(summary_cp) != str(live["idClasePeriodo"]):
        raise PerformancePlanError(
            "La API devolvió un idClasePeriodo distinto al de la libreta visible."
        )
    summary_root = _ci_get(class_info, "idContenidoPrin")
    if summary_root not in (None, "") and str(summary_root) != str(live["idContenido"]):
        raise PerformancePlanError(
            "La API devolvió un contenido raíz distinto al de la libreta visible."
        )

    api_period = int(_ci_get(class_info, "periodo") or browser_context["period"] or 0)
    if api_period != int(browser_context["period"]):
        raise PerformancePlanError(
            f"El período visible/API no coincide ({browser_context['period']} vs {api_period})."
        )
    api_course = str(_ci_get(class_info, "cursocod") or "").strip()
    if api_course and api_course != str(browser_context["course_code"]).strip():
        raise PerformancePlanError(
            f"El curso visible/API no coincide ({browser_context['course_code']} vs {api_course})."
        )

    class_id_raw = _ci_get(class_info, "idClase")
    if class_id_raw in (None, ""):
        class_id_raw = _recursive_ci_get(before, "idClase")
    ambito_raw = _ci_get(class_info, "idAmbito")
    if ambito_raw in (None, ""):
        ambito_raw = _recursive_ci_get(before, "idAmbito")

    class_id = _as_int(class_id_raw, "idClase")
    id_ambito = _as_int(ambito_raw, "idAmbito")

    api_context = {
        "section": browser_context.get("section"),
        "idAmbito": id_ambito,
        "idClase": class_id,
        "idClasePeriodo": int(live["idClasePeriodo"]),
        "idContenido": int(live["idContenido"]),
        "periodo": api_period,
        "idPeriodoAnt": int(live.get("idPeriodoAnt") or 0),
        "course": {
            "NOMCLASE": _ci_get(class_info, "cursonom") or "",
            "NOMBRE": _ci_get(class_info, "cursonom") or "",
        },
        "context_source": "live_obtRegistroNotas_request_rc16",
    }

    evidence = plan.get("evidence") or {}
    default_abbr = base._clean(evidence.get("abbreviation")) or base._clean(evidence.get("name"))[:40]
    planned: list[base.PlannedPerformance] = []

    for index, raw in enumerate(plan.get("performances") or [], start=1):
        pid = base._clean(raw.get("id") or f"P{index}").upper()
        capacity = base._clean(raw.get("capacity"))
        description = base._clean(raw.get("description"))
        abbreviation = base._clean(raw.get("abbreviation")) or default_abbr

        cap = base._find_capacity(before, capacity)
        parent_id = int(cap.get("id"))
        matches = client.find_exact_criterion(
            before,
            description=description,
            parent_id=parent_id,
            level=3,
        )
        if len(matches) > 1:
            raise PerformancePlanError(
                f"El desempeño {pid} ya aparece duplicado en SIEweb ({len(matches)} coincidencias)."
            )
        existing_id = int(matches[0].get("id")) if len(matches) == 1 else None
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
