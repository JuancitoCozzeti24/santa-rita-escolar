from __future__ import annotations

import copy
import time
from typing import Any

import launcher_v100rc11 as rc11
import performance_plan as base
import performance_plan_rc16 as rc16
import performance_plan_rc18 as rc18
import verified_writer_bridge as writer


PerformancePlanError = base.PerformancePlanError

# Taxonomía CNEB de Matemática. Se usa SOLO para ubicar la competencia padre de una
# capacidad que el plan ya declara explícitamente. No inventa desempeños ni notas.
_CNEB_CAPACITY_TO_COMPETENCY = {
    base._canon("Traduce cantidades a expresiones numéricas"): "Resuelve problemas de cantidad",
    base._canon("Comunica su comprensión sobre los números y las operaciones"): "Resuelve problemas de cantidad",
    base._canon("Usa estrategias y procedimientos de estimación y cálculo"): "Resuelve problemas de cantidad",
    base._canon("Argumenta afirmaciones sobre las relaciones numéricas y las operaciones"): "Resuelve problemas de cantidad",

    base._canon("Traduce datos y condiciones a expresiones algebraicas y gráficas"): "Resuelve problemas de regularidad, equivalencia y cambio",
    base._canon("Comunica su comprensión sobre las relaciones algebraicas"): "Resuelve problemas de regularidad, equivalencia y cambio",
    base._canon("Usa estrategias y procedimientos para encontrar equivalencias y reglas generales"): "Resuelve problemas de regularidad, equivalencia y cambio",
    base._canon("Argumenta afirmaciones sobre relaciones de cambio y equivalencia"): "Resuelve problemas de regularidad, equivalencia y cambio",

    base._canon("Modela objetos con formas geométricas y sus transformaciones"): "Resuelve problemas de forma, movimiento y localización",
    base._canon("Comunica su comprensión sobre las formas y relaciones geométricas"): "Resuelve problemas de forma, movimiento y localización",
    base._canon("Usa estrategias y procedimientos para medir y orientarse en el espacio"): "Resuelve problemas de forma, movimiento y localización",
    base._canon("Argumenta afirmaciones sobre relaciones geométricas"): "Resuelve problemas de forma, movimiento y localización",

    base._canon("Representa datos con gráficos y medidas estadísticas o probabilísticas"): "Resuelve problemas de gestión de datos e incertidumbre",
    base._canon("Comunica su comprensión de los conceptos estadísticos y probabilísticos"): "Resuelve problemas de gestión de datos e incertidumbre",
    base._canon("Usa estrategias y procedimientos para recopilar y procesar datos"): "Resuelve problemas de gestión de datos e incertidumbre",
    base._canon("Sustenta conclusiones o decisiones en base a la información obtenida"): "Resuelve problemas de gestión de datos e incertidumbre",
    base._canon("Sustenta conclusiones o decisiones con base en la información obtenida"): "Resuelve problemas de gestión de datos e incertidumbre",
}


def _canon(value: Any) -> str:
    return base._canon(value)


def _desc(client: Any, row: dict[str, Any]) -> str:
    try:
        return str(client._criterion_description(row) or "").strip()
    except Exception:
        return str(row.get("DESCRIPCION") or row.get("descripcion") or row.get("desc") or "").strip()


def _content_id(client: Any, row: dict[str, Any]) -> int | None:
    try:
        raw = client._criterion_content_id(row)
    except Exception:
        raw = row.get("ID_CONTENIDO") or row.get("idContenido") or row.get("id")
    try:
        value = int(raw)
    except Exception:
        return None
    return value if value > 0 else None


def _parent_id(client: Any, row: dict[str, Any]) -> int | None:
    try:
        raw = client._criterion_parent(row)
    except Exception:
        raw = None
    if raw in (None, "", 0, "0"):
        for key in ("ID_CONTENIDO_REF", "idContenidoRef", "idpadre", "idPadre", "ID_PADRE"):
            if row.get(key) not in (None, "", 0, "0"):
                raw = row.get(key)
                break
    try:
        value = int(raw)
    except Exception:
        return None
    return value if value > 0 else None


def _program_id(row: dict[str, Any]) -> int | None:
    raw = row.get("ID_PROGRAMA", row.get("idPrograma"))
    try:
        value = int(raw)
    except Exception:
        return None
    return value if value > 0 else None


def _all_rows(client: Any, raw: dict[str, Any]) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    seen: set[tuple[Any, str, Any, Any]] = set()
    for row in client._walk_dicts(raw):
        if not isinstance(row, dict):
            continue
        text = _desc(client, row)
        cid = _content_id(client, row)
        if not text or not cid:
            continue
        key = (cid, _canon(text), _parent_id(client, row), _program_id(row))
        if key in seen:
            continue
        seen.add(key)
        rows.append(row)
    return rows


def _find_exact_node(
    client: Any,
    rows: list[dict[str, Any]],
    *,
    description: str,
    parent_id: int | None = None,
    program_id: int | None = None,
) -> dict[str, Any] | None:
    wanted = _canon(description)
    matches: list[dict[str, Any]] = []
    for row in rows:
        if _canon(_desc(client, row)) != wanted:
            continue
        if parent_id is not None and _parent_id(client, row) != int(parent_id):
            continue
        row_program = _program_id(row)
        if program_id is not None and row_program not in (None, int(program_id)):
            continue
        matches.append(row)
    if len(matches) > 1:
        ids = [_content_id(client, row) for row in matches]
        raise PerformancePlanError(
            f"SIEweb devolvió más de un criterio {description!r} para el mismo padre/programa: {ids}."
        )
    return matches[0] if matches else None


def _competency_for_performance(raw: dict[str, Any]) -> str:
    explicit = base._clean(raw.get("competency"))
    if explicit:
        return explicit
    capacity = base._clean(raw.get("capacity"))
    competency = _CNEB_CAPACITY_TO_COMPETENCY.get(_canon(capacity))
    if not competency:
        raise PerformancePlanError(
            f"No puedo inferir de forma segura la competencia padre de la capacidad {capacity!r}. "
            "Agrega competency a ese desempeño en SIEROOM_PLAN.json."
        )
    return competency


def _resolve_context(page: Any, plan: dict[str, Any]):
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
        raise PerformancePlanError(f"No se pudo releer la libreta visible: {exc}") from exc

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
        "context_source": "live_obtRegistroNotas_stable_bootstrap",
    }
    return browser_context, client, auth_status, before, api_context


def _read_raw(client: Any, ctx: dict[str, Any]) -> tuple[dict[str, Any], list[dict[str, Any]]]:
    raw = client.get_criteria(
        class_id=int(ctx["idClase"]),
        class_period_id=int(ctx["idClasePeriodo"]),
        root_content_id=int(ctx["idContenido"]),
        id_ambito=int(ctx["idAmbito"]),
        extra_params={"idPeriodoAnt": int(ctx.get("idPeriodoAnt") or 0)},
    )
    return raw, _all_rows(client, raw)


def _find_program_choices(client: Any, raw: dict[str, Any], parent: dict[str, Any]) -> list[dict[str, Any]]:
    data_program = client._find_named_value(raw, {"dataPrograma"})
    if not isinstance(data_program, dict):
        return []
    obj = data_program.get("objProgramas")
    if not isinstance(obj, dict):
        return []
    parent_program = _program_id(parent)
    if parent_program is None:
        # Programa CNEB observado en SIEweb: 3=Competencia, 4=Capacidad, 5=Desempeño.
        parent_program = 3 if _parent_id(client, parent) is None else 4
    choices = obj.get(str(parent_program))
    if choices is None:
        choices = obj.get(parent_program)
    return [x for x in (choices or []) if isinstance(x, dict)]


def _child_program(
    client: Any,
    raw: dict[str, Any],
    parent: dict[str, Any],
    desired_program: int,
) -> dict[str, Any]:
    matches = [
        copy.deepcopy(item)
        for item in _find_program_choices(client, raw, parent)
        if str(item.get("ID_PROGRAMA")) == str(desired_program)
    ]
    if len(matches) != 1:
        raise PerformancePlanError(
            f"SIEweb no expuso exactamente un programa hijo ID_PROGRAMA={desired_program} "
            f"para {_desc(client, parent)!r}; coincidencias={len(matches)}."
        )
    return matches[0]


def _next_index(
    client: Any,
    rows: list[dict[str, Any]],
    *,
    parent_id: int,
    program_id: int,
    limit: int,
    reserved: set[int],
) -> int:
    used = set(reserved)
    for row in rows:
        if _parent_id(client, row) != int(parent_id) or _program_id(row) != int(program_id):
            continue
        try:
            used.add(int(row.get("INDICE", row.get("indice"))))
        except Exception:
            pass
    index = next((i for i in range(1, limit + 1) if i not in used), None)
    if index is None:
        raise PerformancePlanError(
            f"El criterio padre ID_CONTENIDO={parent_id} alcanzó el límite de {limit} hijos del programa {program_id}."
        )
    reserved.add(index)
    return index


def _build_native_child(
    client: Any,
    raw: dict[str, Any],
    rows: list[dict[str, Any]],
    *,
    ctx: dict[str, Any],
    parent: dict[str, Any],
    description: str,
    program_id: int,
    abbreviation: str,
    reserved: set[int],
) -> dict[str, Any]:
    parent_id = _content_id(client, parent)
    parent_key = str(parent.get("LLAVE") or parent.get("llave") or "").strip()
    if not parent_id or not parent_key:
        raise PerformancePlanError(
            f"El padre {_desc(client, parent)!r} no expone ID_CONTENIDO/LLAVE persistidos."
        )
    program = _child_program(client, raw, parent, program_id)
    limit = int(program.get("LIMITE") or (4 if program_id == 4 else 6))
    if limit <= 0:
        raise PerformancePlanError(f"El programa {program_id} no permite altas nuevas.")
    index = _next_index(
        client,
        rows,
        parent_id=parent_id,
        program_id=program_id,
        limit=limit,
        reserved=reserved,
    )
    parent_level = 1 if program_id == 4 else 2
    return {
        "ID_CLASE_CONTENIDO": 0,
        "ID_CLASE": int(ctx["idClase"]),
        "ID_CLASE_PERIODO": int(ctx["idClasePeriodo"]),
        "EXCLUIR": 0,
        "SUMATIVO": 0,
        "PESO": 1,
        "ID_CONTENIDO": 0,
        "DESCRIPCION": str(description),
        "ID_PROGRAMA": int(program_id),
        "ID_CONTENIDO_REF": int(parent_id),
        "ABREVIATURA": str(abbreviation or ""),
        "INCLUSIVO": 0,
        "ORDEN": 1,
        "BASE": 0,
        "INDICE": int(index),
        "replicar": False,
        "TRADUCCION": None,
        "NIVEL_PADRE": int(parent_level),
        "LLAVE": f"{program_id}-{index}_{parent_key}",
        "COLORP": program.get("COLOR") or "#ffffff",
        "DESCP": program.get("DESCRIPCION") or ("Capacidad" if program_id == 4 else "Desempeño"),
        "ICONOP": program.get("ICONO") or ("simbolo4" if program_id == 4 else "simbolo5"),
    }


def _post_native_records(
    client: Any,
    ctx: dict[str, Any],
    raw: dict[str, Any],
    parents: list[dict[str, Any]],
    records: list[dict[str, Any]],
) -> dict[str, Any]:
    if not records:
        return {"estado": 1, "skipped": True}
    before = client.get_gradebook_summary(
        class_period_id=int(ctx["idClasePeriodo"]),
        root_content_id=int(ctx["idContenido"]),
        extra_params={"idPeriodoAnt": int(ctx.get("idPeriodoAnt") or 0)},
    )
    class_info = before.get("class") or {}
    criteria_context = dict(getattr(client, "_last_criteria_context", {}) or {})
    replicas = [
        client.build_native_replica_context(
            raw=raw,
            class_info=class_info,
            parent=parent,
            criteria_context=criteria_context,
            supplied={},
        )
        for parent in parents
    ]
    replica = replicas[0]
    if any(item != replica for item in replicas[1:]):
        raise PerformancePlanError("Los criterios nuevos no comparten el mismo contexto nativo de réplica.")
    result = client._request(
        "POST",
        "/lms/api/HyoClaseContenido/insertar",
        json={"registros": copy.deepcopy(records), "idClase": int(ctx["idClase"]), "datosReplica": replica},
    )
    body = (result.get("json") or {}) if isinstance(result, dict) else {}
    if body.get("estado") != 1:
        raise PerformancePlanError(
            f"SIEweb rechazó el alta de criterios (estado={body.get('estado')!r}, "
            f"codigo={body.get('codigo') or body.get('code') or body.get('mensaje')!r})."
        )
    return result


def preview_plan(page: Any, plan: dict[str, Any]) -> base.PerformancePreview:
    browser_context, client, auth_status, before, ctx = _resolve_context(page, plan)
    raw, rows = _read_raw(client, ctx)
    evidence = plan.get("evidence") or {}
    default_abbr = base._clean(evidence.get("abbreviation")) or base._clean(evidence.get("name"))[:40]

    planned: list[base.PlannedPerformance] = []
    bootstrap: dict[str, dict[str, Any]] = {}
    for index, item in enumerate(plan.get("performances") or [], start=1):
        pid = base._clean(item.get("id") or f"P{index}").upper()
        capacity = base._clean(item.get("capacity"))
        description = base._clean(item.get("description"))
        abbreviation = base._clean(item.get("abbreviation")) or default_abbr
        competency = _competency_for_performance(item)

        root = _find_exact_node(client, rows, description=competency, program_id=3)
        if root is None:
            # Algunos payloads omiten ID_PROGRAMA en raíces; el texto exacto sigue siendo obligatorio.
            root = _find_exact_node(client, rows, description=competency)
        if root is None:
            raise PerformancePlanError(f"SIEweb no expuso la competencia padre {competency!r}.")
        root_id = _content_id(client, root)
        if not root_id:
            raise PerformancePlanError(f"La competencia {competency!r} no expuso ID_CONTENIDO.")

        cap = _find_exact_node(client, rows, description=capacity, parent_id=root_id, program_id=4)
        cap_id = _content_id(client, cap) if cap else None
        existing = None
        if cap_id:
            perf = _find_exact_node(
                client,
                rows,
                description=description,
                parent_id=cap_id,
                program_id=5,
            )
            existing = _content_id(client, perf) if perf else None

        planned.append(
            base.PlannedPerformance(
                plan_id=pid,
                capacity=capacity,
                description=description,
                abbreviation=abbreviation,
                parent_id=int(cap_id or 0),
                existing_id=existing,
            )
        )
        bootstrap[pid] = {
            "competency": competency,
            "root_id": root_id,
            "capacity": capacity,
            "capacity_id": cap_id,
        }

    preview = base.PerformancePreview(
        plan=plan,
        browser_context=browser_context,
        api_context=ctx,
        auth_status=auth_status,
        client=client,
        before=before,
        performances=planned,
    )
    preview._sieroom_bootstrap = bootstrap
    return preview


def create_missing_performances(preview: base.PerformancePreview) -> dict[str, Any]:
    client = preview.client
    ctx = preview.api_context
    bootstrap = getattr(preview, "_sieroom_bootstrap", {}) or {}

    # Etapa 1: asegurar las capacidades CNEB base que SIEweb todavía no materializó.
    raw, rows = _read_raw(client, ctx)
    capacity_records: list[dict[str, Any]] = []
    capacity_parents: list[dict[str, Any]] = []
    reserved_by_root: dict[int, set[int]] = {}
    capacities_to_verify: dict[tuple[int, str], str] = {}

    for index, perf_raw in enumerate(preview.plan.get("performances") or [], start=1):
        pid = base._clean(perf_raw.get("id") or f"P{index}").upper()
        meta = bootstrap.get(pid) or {}
        root_id = int(meta.get("root_id") or 0)
        capacity = str(meta.get("capacity") or "").strip()
        if not root_id or not capacity:
            raise PerformancePlanError(f"Falta metadato seguro para {pid}.")
        capacities_to_verify[(root_id, _canon(capacity))] = capacity

    for (root_id, _key), capacity in capacities_to_verify.items():
        existing = _find_exact_node(client, rows, description=capacity, parent_id=root_id, program_id=4)
        if existing:
            continue
        root = next((r for r in rows if _content_id(client, r) == root_id), None)
        if root is None:
            raise PerformancePlanError(f"No se volvió a localizar la competencia ID_CONTENIDO={root_id}.")
        record = _build_native_child(
            client,
            raw,
            rows,
            ctx=ctx,
            parent=root,
            description=capacity,
            program_id=4,
            abbreviation="",
            reserved=reserved_by_root.setdefault(root_id, set()),
        )
        capacity_records.append(record)
        capacity_parents.append(root)

    if capacity_records:
        _post_native_records(client, ctx, raw, capacity_parents, capacity_records)
        for attempt in range(1, 4):
            time.sleep(0.55 * attempt)
            raw, rows = _read_raw(client, ctx)
            missing = [
                capacity
                for (root_id, _key), capacity in capacities_to_verify.items()
                if _find_exact_node(client, rows, description=capacity, parent_id=root_id, program_id=4) is None
            ]
            if not missing:
                break
        if missing:
            raise PerformancePlanError(
                "SIEweb aceptó el alta de capacidades, pero la relectura no confirmó: " + " | ".join(missing)
            )

    # Etapa 2: crear únicamente los desempeños que faltan, ya con capacidad padre real.
    raw, rows = _read_raw(client, ctx)
    performance_records: list[dict[str, Any]] = []
    performance_parents: list[dict[str, Any]] = []
    reserved_by_capacity: dict[int, set[int]] = {}
    expected: list[tuple[base.PlannedPerformance, int]] = []

    for item in preview.performances:
        meta = bootstrap.get(item.plan_id) or {}
        root_id = int(meta.get("root_id") or 0)
        cap = _find_exact_node(
            client,
            rows,
            description=item.capacity,
            parent_id=root_id,
            program_id=4,
        )
        cap_id = _content_id(client, cap) if cap else None
        if not cap or not cap_id:
            raise PerformancePlanError(f"La capacidad {item.capacity!r} no quedó disponible para {item.plan_id}.")
        item.parent_id = int(cap_id)
        existing = _find_exact_node(
            client,
            rows,
            description=item.description,
            parent_id=cap_id,
            program_id=5,
        )
        if existing:
            item.existing_id = _content_id(client, existing)
            expected.append((item, cap_id))
            continue
        record = _build_native_child(
            client,
            raw,
            rows,
            ctx=ctx,
            parent=cap,
            description=item.description,
            program_id=5,
            abbreviation=item.abbreviation,
            reserved=reserved_by_capacity.setdefault(cap_id, set()),
        )
        performance_records.append(record)
        performance_parents.append(cap)
        expected.append((item, cap_id))

    created = len(performance_records)
    if performance_records:
        _post_native_records(client, ctx, raw, performance_parents, performance_records)

    checks: list[dict[str, Any]] = []
    final_rows: list[dict[str, Any]] = []
    for attempt in range(1, 4):
        if performance_records:
            time.sleep(0.55 * attempt)
        _raw_after, final_rows = _read_raw(client, ctx)
        checks = []
        for item, cap_id in expected:
            found = _find_exact_node(
                client,
                final_rows,
                description=item.description,
                parent_id=cap_id,
                program_id=5,
            )
            criterion_id = _content_id(client, found) if found else None
            if criterion_id:
                item.existing_id = criterion_id
            checks.append(
                {
                    "id": item.plan_id,
                    "description": item.description,
                    "parent_id": cap_id,
                    "criterion_id": criterion_id,
                    "ok": bool(criterion_id),
                }
            )
        if all(row["ok"] for row in checks):
            break

    if not checks or not all(row["ok"] for row in checks):
        raise PerformancePlanError(
            "La creación terminó, pero la relectura de SIEweb no confirmó cada desempeño exactamente una vez."
        )

    return {
        "created": created,
        "existing": len(preview.performances) - created,
        "capacities_created": len(capacity_records),
        "verification": checks,
        "mode": "stable-cneb-bootstrap-program-id",
    }
