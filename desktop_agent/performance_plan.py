from __future__ import annotations

import json
import os
import sys
import unicodedata
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import verified_writer_bridge as writer


class PerformancePlanError(RuntimeError):
    pass


def _canon(value: Any) -> str:
    text = unicodedata.normalize("NFKD", str(value or ""))
    text = "".join(ch for ch in text if not unicodedata.combining(ch))
    text = " ".join("".join(ch if ch.isalnum() else " " for ch in text.lower()).split())
    return text


def _clean(value: Any) -> str:
    return " ".join(str(value or "").split()).strip()


def _default_plan_paths() -> list[Path]:
    paths: list[Path] = []
    raw = os.environ.get("SIEROOM_PLAN", "").strip()
    if raw:
        paths.append(Path(raw).expanduser())

    try:
        exe_dir = Path(sys.executable).resolve().parent
        paths.append(exe_dir / "SIEROOM_PLAN.json")
    except Exception:
        pass

    paths.append(Path.cwd() / "SIEROOM_PLAN.json")
    paths.append(Path.home() / "Downloads" / "SIEROOM_PLAN.json")

    out: list[Path] = []
    seen: set[str] = set()
    for path in paths:
        key = str(path).lower()
        if key not in seen:
            out.append(path)
            seen.add(key)
    return out


def find_plan_file() -> Path | None:
    for path in _default_plan_paths():
        try:
            if path.is_file():
                return path
        except Exception:
            continue
    return None


def write_template(path: Path) -> Path:
    template = {
        "schema": "sieroom-evaluation-plan/v1",
        "evidence": {
            "name": "REEMPLAZAR: nombre de la evidencia",
            "abbreviation": "REEMPLAZAR: abreviatura breve"
        },
        "target": {
            "section": "S2A",
            "course_code": "05",
            "period": 3
        },
        "performances": [
            {
                "id": "P1",
                "capacity": "REEMPLAZAR: capacidad exacta de SIEweb",
                "description": "REEMPLAZAR: desempeño precisado redactado por el Skill docente",
                "abbreviation": "REEMPLAZAR: abreviatura breve"
            }
        ],
        "grades": []
    }
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(template, ensure_ascii=False, indent=2), encoding="utf-8")
    return path


def load_plan(path: Path) -> dict[str, Any]:
    try:
        raw = json.loads(path.read_text(encoding="utf-8"))
    except Exception as exc:
        raise PerformancePlanError(f"No se pudo leer {path}: {exc}") from exc
    if not isinstance(raw, dict):
        raise PerformancePlanError("El plan debe ser un objeto JSON.")
    validate_plan(raw)
    return raw


def validate_plan(plan: dict[str, Any]) -> None:
    if _clean(plan.get("schema")) != "sieroom-evaluation-plan/v1":
        raise PerformancePlanError("Schema inválido; se esperaba sieroom-evaluation-plan/v1.")

    evidence = plan.get("evidence") or {}
    target = plan.get("target") or {}
    performances = plan.get("performances") or []

    if not isinstance(evidence, dict) or not _clean(evidence.get("name")):
        raise PerformancePlanError("Falta evidence.name.")
    if "REEMPLAZAR" in _clean(evidence.get("name")).upper():
        raise PerformancePlanError("El plan todavía contiene texto REEMPLAZAR.")

    section = _clean(target.get("section")).upper()
    course_code = _clean(target.get("course_code"))
    try:
        period = int(target.get("period"))
    except Exception as exc:
        raise PerformancePlanError("target.period debe ser 1, 2, 3 o 4.") from exc
    if not section or not course_code or period not in {1, 2, 3, 4}:
        raise PerformancePlanError("target debe incluir section, course_code y period válidos.")

    if not isinstance(performances, list) or not (1 <= len(performances) <= 12):
        raise PerformancePlanError("performances debe contener entre 1 y 12 desempeños.")

    ids: set[str] = set()
    for index, item in enumerate(performances, start=1):
        if not isinstance(item, dict):
            raise PerformancePlanError(f"Desempeño {index}: formato inválido.")
        pid = _clean(item.get("id") or f"P{index}").upper()
        capacity = _clean(item.get("capacity"))
        description = _clean(item.get("description"))
        if not pid or pid in ids:
            raise PerformancePlanError(f"Desempeño {index}: id vacío o duplicado.")
        ids.add(pid)
        if not capacity or not description:
            raise PerformancePlanError(f"Desempeño {pid}: faltan capacity/description.")
        if "REEMPLAZAR" in (capacity + " " + description).upper():
            raise PerformancePlanError(f"Desempeño {pid}: aún contiene texto REEMPLAZAR.")


@dataclass
class PlannedPerformance:
    plan_id: str
    capacity: str
    description: str
    abbreviation: str
    parent_id: int
    existing_id: int | None

    @property
    def exists(self) -> bool:
        return self.existing_id is not None


@dataclass
class PerformancePreview:
    plan: dict[str, Any]
    browser_context: dict[str, Any]
    api_context: dict[str, Any]
    auth_status: dict[str, bool]
    client: Any
    before: dict[str, Any]
    performances: list[PlannedPerformance]

    @property
    def missing(self) -> list[PlannedPerformance]:
        return [item for item in self.performances if not item.exists]


def _find_capacity(summary: dict[str, Any], description: str) -> dict[str, Any]:
    wanted = _canon(description)
    matches = []
    for item in summary.get("criteria") or []:
        if not isinstance(item, dict):
            continue
        try:
            level = int(item.get("nivelEva") or 0)
        except Exception:
            level = 0
        if level != 2:
            continue
        text = item.get("descripcion") or item.get("desc") or item.get("nombre") or ""
        if _canon(text) == wanted:
            matches.append(item)
    if len(matches) != 1:
        raise PerformancePlanError(
            f"La capacidad no se resolvió de forma única en SIEweb: {description!r} (coincidencias={len(matches)})."
        )
    return matches[0]


def _target_matches(plan: dict[str, Any], browser_context: dict[str, Any]) -> None:
    target = plan.get("target") or {}
    expected_section = _clean(target.get("section")).upper()
    expected_course = _clean(target.get("course_code"))
    expected_period = int(target.get("period"))

    actual_section = _clean(browser_context.get("section")).upper()
    actual_course = _clean(browser_context.get("course_code"))
    actual_period = int(browser_context.get("period") or 0)

    if (expected_section, expected_course, expected_period) != (
        actual_section,
        actual_course,
        actual_period,
    ):
        raise PerformancePlanError(
            "El plan NO corresponde a la libreta visible. "
            f"Plan={expected_section}/{expected_course}/P{expected_period}; "
            f"pantalla={actual_section}/{actual_course}/P{actual_period}."
        )


def preview_plan(page, plan: dict[str, Any]) -> PerformancePreview:
    validate_plan(plan)
    browser_context = writer.infer_browser_context(page)
    _target_matches(plan, browser_context)

    client, auth_status = writer._hydrate_client_from_browser(page)
    try:
        api_context = client.resolve_class_context(
            section=browser_context["section"],
            period=int(browser_context["period"]),
            course_code=str(browser_context["course_code"]),
        )
        extra = {"idPeriodoAnt": int(api_context.get("idPeriodoAnt") or 0)}
        before = client.get_gradebook_summary(
            class_period_id=int(api_context["idClasePeriodo"]),
            root_content_id=int(api_context["idContenido"]),
            extra_params=extra,
        )
    except Exception as exc:
        raise PerformancePlanError(f"No se pudo releer la libreta por API: {exc}") from exc

    evidence = plan.get("evidence") or {}
    default_abbr = _clean(evidence.get("abbreviation")) or _clean(evidence.get("name"))[:40]
    planned: list[PlannedPerformance] = []

    for index, raw in enumerate(plan.get("performances") or [], start=1):
        pid = _clean(raw.get("id") or f"P{index}").upper()
        capacity = _clean(raw.get("capacity"))
        description = _clean(raw.get("description"))
        abbreviation = _clean(raw.get("abbreviation")) or default_abbr

        cap = _find_capacity(before, capacity)
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
            PlannedPerformance(
                plan_id=pid,
                capacity=capacity,
                description=description,
                abbreviation=abbreviation,
                parent_id=parent_id,
                existing_id=existing_id,
            )
        )

    return PerformancePreview(
        plan=plan,
        browser_context=browser_context,
        api_context=api_context,
        auth_status=auth_status,
        client=client,
        before=before,
        performances=planned,
    )


def create_missing_performances(preview: PerformancePreview) -> dict[str, Any]:
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
    records = []
    expected = []
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
            id_ambito=int(ctx.get("idAmbito")),
            records=records,
            replica={},
            expected=expected,
            extra_params=extra,
            verification_attempts=3,
        )
    except Exception as exc:
        raise PerformancePlanError(f"SIEweb rechazó la creación de desempeños: {exc}") from exc

    after = preview.client.get_gradebook_summary(
        class_period_id=int(ctx["idClasePeriodo"]),
        root_content_id=int(ctx["idContenido"]),
        extra_params=extra,
    )

    checks = []
    all_ok = True
    for item in preview.performances:
        cap = _find_capacity(after, item.capacity)
        matches = preview.client.find_exact_criterion(
            after,
            description=item.description,
            parent_id=int(cap.get("id")),
            level=3,
        )
        ok = len(matches) == 1
        checks.append({
            "id": item.plan_id,
            "description": item.description,
            "count": len(matches),
            "criterion_id": matches[0].get("id") if ok else None,
            "ok": ok,
        })
        all_ok = all_ok and ok

    if not all_ok:
        raise PerformancePlanError(
            "La creación terminó, pero la verificación posterior no encontró cada desempeño exactamente una vez."
        )

    return {
        "created": len(missing),
        "existing": len(preview.performances) - len(missing),
        "writer_result": write_result,
        "verification": checks,
    }
