from __future__ import annotations

import builtins
import difflib
import re
import unicodedata
from datetime import datetime
from pathlib import Path

import main as legacy
import launcher_v100rc1 as rc1
import launcher_v100rc3 as rc3
import launcher_v100rc9 as rc9
import launcher_v100rc13 as rc13
import launcher_v100rc14 as rc14

from performance_plan import (
    PerformancePlanError,
    create_missing_performances,
    find_plan_file,
    load_plan,
    preview_plan,
    write_template,
)


APP_VERSION = "1.0.0-rc15"
MAX_BATCH = 112
_original_print = builtins.print


def _print_rc15(*args, **kwargs):
    patched = []
    for arg in args:
        if isinstance(arg, str):
            patched.append(
                arg.replace("RC14", "RC15")
                .replace("RC13", "RC15")
                .replace("RC12", "RC15")
            )
        else:
            patched.append(arg)
    _original_print(*patched, **kwargs)


rc14.print = _print_rc15
rc13.print = _print_rc15
rc9.print = _print_rc15
rc9.MAX_BATCH = MAX_BATCH
rc13.APP_VERSION = APP_VERSION
rc14.APP_VERSION = APP_VERSION


def _canon(value) -> str:
    text = unicodedata.normalize("NFKD", str(value or ""))
    text = "".join(ch for ch in text if not unicodedata.combining(ch))
    return " ".join("".join(ch if ch.isalnum() else " " for ch in text.lower()).split())


def _score(a: str, b: str) -> float:
    ca, cb = _canon(a), _canon(b)
    if not ca or not cb:
        return 0.0
    if ca == cb:
        return 1.0
    if ca.startswith(cb) or cb.startswith(ca):
        return 0.94 if min(len(ca), len(cb)) >= 12 else 0.72
    return difflib.SequenceMatcher(None, ca, cb).ratio()


def _plan_template_destination() -> Path:
    return Path.home() / "Downloads" / "SIEROOM_PLAN.json"


def _public_preview(preview) -> dict:
    return {
        "browser_context": preview.browser_context,
        "api_context": {
            "section": preview.api_context.get("section"),
            "idAmbito": preview.api_context.get("idAmbito"),
            "idClase": preview.api_context.get("idClase"),
            "idClasePeriodo": preview.api_context.get("idClasePeriodo"),
            "idContenido": preview.api_context.get("idContenido"),
            "periodo": preview.api_context.get("periodo"),
        },
        "performances": [
            {
                "id": item.plan_id,
                "capacity": item.capacity,
                "description": item.description,
                "abbreviation": item.abbreviation,
                "parent_id": item.parent_id,
                "existing_id": item.existing_id,
                "exists": item.exists,
            }
            for item in preview.performances
        ],
    }


def _find_plan_column(probe, perf: dict) -> int:
    targets = [
        str(perf.get("description") or ""),
        str(perf.get("abbreviation") or ""),
    ]
    ranked = []
    for col in probe.columns:
        idx = int(col.get("index") or 0) + 1
        label = str(col.get("semantic_header") or col.get("header") or "")
        score = max(_score(label, target) for target in targets if target)
        ranked.append((score, idx, label))
    ranked.sort(reverse=True, key=lambda x: x[0])
    if not ranked or ranked[0][0] < 0.72:
        raise PerformancePlanError(
            f"No se pudo asociar el desempeño {perf.get('id')} a una columna visible de la libreta."
        )
    if len(ranked) > 1 and ranked[0][0] < 0.999 and ranked[0][0] - ranked[1][0] < 0.08:
        raise PerformancePlanError(
            f"La columna del desempeño {perf.get('id')} es ambigua; escritura bloqueada."
        )
    return ranked[0][1]


def _find_student(cell_map, row: dict):
    code = str(row.get("student_code") or "").strip()
    if code:
        matches = [s for s in cell_map.students if str(s.get("code") or "").strip() == code]
    elif row.get("student_order") not in (None, ""):
        try:
            order = int(row.get("student_order"))
        except Exception as exc:
            raise PerformancePlanError("student_order inválido en el plan.") from exc
        matches = [s for s in cell_map.students if int(s.get("order") or 0) == order]
    else:
        wanted = _canon(row.get("student_name"))
        if not wanted:
            raise PerformancePlanError(
                "Cada fila de grades necesita student_code, student_order o student_name."
            )
        matches = [s for s in cell_map.students if _canon(s.get("name")) == wanted]

    if len(matches) != 1:
        raise PerformancePlanError(
            f"Un alumno del plan no se resolvió exactamente una vez en la libreta (coincidencias={len(matches)})."
        )
    return matches[0]


def _collect_plan_items(probe, plan: dict) -> list[dict]:
    grade_rows = plan.get("grades") or []
    if not grade_rows:
        return []
    if not isinstance(grade_rows, list):
        raise PerformancePlanError("grades debe ser una lista.")

    perf_by_id = {}
    column_by_id = {}
    for index, perf in enumerate(plan.get("performances") or [], start=1):
        pid = str(perf.get("id") or f"P{index}").strip().upper()
        perf_by_id[pid] = perf
        column_by_id[pid] = _find_plan_column(probe, perf)

    items = []
    seen = set()
    for row in grade_rows:
        if not isinstance(row, dict):
            raise PerformancePlanError("Una fila de grades tiene formato inválido.")
        student = _find_student(probe._cell_map, row)
        values = row.get("values") or {}
        if not isinstance(values, dict) or not values:
            raise PerformancePlanError("Cada fila de grades necesita un objeto values con P1/P2/... -> A/B/C.")

        for raw_pid, raw_grade in values.items():
            pid = str(raw_pid or "").strip().upper()
            grade = str(raw_grade or "").strip().upper()
            if pid not in perf_by_id:
                raise PerformancePlanError(f"grades referencia un desempeño desconocido: {pid}.")
            if grade not in {"A", "B", "C"}:
                raise PerformancePlanError(f"Calificación inválida para {pid}: {grade!r}.")

            column = column_by_id[pid]
            code = str(student.get("code") or "").strip()
            key = (code, column)
            if key in seen:
                raise PerformancePlanError(f"La celda {code}/columna {column} aparece duplicada en el plan.")
            seen.add(key)

            cell = rc1._target_cell(student, column - 1)
            if not cell:
                raise PerformancePlanError(f"No se localizó la celda DOM de {code}, columna {column}.")
            current = str(cell.get("text") or "").strip().upper()
            state = str(cell.get("value_state") or "unreadable")
            confident = bool(cell.get("value_confident"))
            if not confident or state not in {"blank", "grade"}:
                raise PerformancePlanError(
                    f"La celda {code}/columna {column} no tiene lectura DOM confiable."
                )

            label = str(
                probe.columns[column - 1].get("semantic_header")
                or probe.columns[column - 1].get("header")
                or ""
            )
            items.append({
                "order": int(student.get("order") or 0),
                "column": column,
                "grade": grade,
                "code": code,
                "name": str(student.get("name") or "").strip(),
                "dom_current": current,
                "label": label,
            })

    if len(items) > MAX_BATCH:
        raise PerformancePlanError(
            f"El plan contiene {len(items)} celdas y RC15 admite como máximo {MAX_BATCH}."
        )
    return items


def _apply_plan(probe, plan_path: Path) -> None:
    page = probe._page
    plan = load_plan(plan_path)
    preview = preview_plan(page, plan)
    evidence = plan.get("evidence") or {}

    print("\n============================================================")
    print(" RC15 — PLAN DOCENTE: DESEMPEÑOS ANTES DE LAS NOTAS")
    print("============================================================")
    print(f"Plan: {plan_path}")
    print(f"Evidencia: {evidence.get('name')}")
    print(
        f"Destino confirmado: {preview.browser_context['section']} | "
        f"curso {preview.browser_context['course_code']} | "
        f"período {preview.browser_context['period']}"
    )
    print("\nDesempeños precisados:")
    for item in preview.performances:
        status = "YA EXISTE" if item.exists else "CREAR"
        print(f"  {item.plan_id}. {item.description} [{status}]")
        print(f"     Capacidad: {item.capacity}")

    evidence_dir = legacy.app_data_root() / "evidence"
    stamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    preflight_path = legacy.save_json(
        evidence_dir,
        f"{stamp}_rc15_performance_plan_preflight.json",
        {
            "plan_file": str(plan_path),
            "evidence": evidence,
            **_public_preview(preview),
        },
    )
    print(f"\nEvidencia preflight: {preflight_path}")

    missing = preview.missing
    if missing:
        phrase = f"CREAR DESEMPENOS {len(missing)}"
        typed = legacy.prompt(
            f"\nPara crear SOLO estos {len(missing)} desempeños escribe exactamente: {phrase}\n> "
        ).strip().upper()
        if typed != phrase:
            print("\nCANCELADO: no se creó ningún desempeño ni se escribió ninguna nota.")
            return
        result = create_missing_performances(preview)
        result_path = legacy.save_json(
            evidence_dir,
            f"{stamp}_rc15_performance_plan_result.json",
            {
                "plan_file": str(plan_path),
                "evidence": evidence,
                "created": result.get("created"),
                "existing": result.get("existing"),
                "verification": result.get("verification"),
            },
        )
        print(f"\n✅ DESEMPEÑOS VERIFICADOS: creados={result.get('created')} existentes={result.get('existing')}")
        print(f"Evidencia: {result_path}")
    else:
        print("\n✅ Todos los desempeños del plan ya existen exactamente una vez. No se creó nada.")

    print("\nActualizando UNA sola vez la misma libreta para mostrar los desempeños...")
    refresh = rc13._refresh_same_gradebook_once(page)
    if not refresh.get("ok"):
        raise PerformancePlanError(
            f"Los desempeños quedaron preparados, pero no se pudo actualizar la vista: {refresh.get('error')}"
        )
    page.wait_for_timeout(1200)

    cell_map = rc3.map_grade_cells_normalized_rc3(page)
    new_probe = rc1.probe_grade_cells_preview(page, cell_map)

    plan_items = _collect_plan_items(new_probe, plan)
    if plan_items:
        print("\n============================================================")
        print(" RC15 — CALIFICACIONES DEL PLAN LISTAS PARA ESCRITURA MASIVA")
        print("============================================================")
        print(f"Celdas preparadas desde el plan: {len(plan_items)}")
        print("El agente hará un único preflight y guardará agrupando por desempeño, sin recargar por alumno.")
        original_collect = rc9._collect_batch
        rc9._collect_batch = lambda _probe: list(plan_items)
        try:
            rc13._fast_persisted_batch(new_probe)
        finally:
            rc9._collect_batch = original_collect
        return

    print("\nEl plan no contiene calificaciones todavía.")
    print("Los desempeños ya están listos; puedes probar ahora el lote manual rápido.")
    rc9._batch_preflight_and_execute(new_probe)


def print_grade_cell_probe_rc15(probe) -> None:
    print("\n--- PRECHECK RC15 DE LIBRETA ---")
    print(f"Estudiantes: {probe._cell_map.student_count}")
    print(f"Estudiantes con celdas asociadas: {probe._cell_map.mapped_student_count}")
    print(f"Columnas visibles actuales: {probe.column_count}")

    plan_path = find_plan_file()
    if plan_path:
        try:
            plan = load_plan(plan_path)
            evidence = plan.get("evidence") or {}
            print(f"\nPlan docente detectado: {plan_path}")
            print(f"Evidencia: {evidence.get('name')}")
        except Exception as exc:
            print(f"\n⚠️ Se encontró SIEROOM_PLAN.json pero no es válido: {exc}")
            plan = None
    else:
        plan = None
        print("\nNo hay SIEROOM_PLAN.json todavía.")

    print("\nOpciones:")
    print("  P = aplicar PLAN DOCENTE: crear/verificar desempeños y luego cargar notas")
    print("  B = usar el lote rápido manual de notas (sin crear desempeños)")
    print("  ENTER = terminar sin modificar nada")
    choice = legacy.prompt("\nElige P, B o ENTER: ").strip().lower()

    if choice in {"b", "batch", "lote"}:
        rc9._batch_preflight_and_execute(probe)
        return
    if choice not in {"p", "plan"}:
        return

    if plan_path is None:
        dest = write_template(_plan_template_destination())
        print(f"\nSe creó una plantilla segura, SIN ejecutar escrituras: {dest}")
        print("En el flujo final este archivo lo generará ChatGPT/Skill docente; no tendrás que redactarlo manualmente.")
        return

    try:
        _apply_plan(probe, plan_path)
    except PerformancePlanError as exc:
        print(f"\n❌ PLAN BLOQUEADO: {exc}")
        print("No se continuará con calificaciones hasta corregir el plan/contexto.")
        legacy.prompt("Presiona ENTER cuando quieras cerrar el agente...")
        raise SystemExit(0)


legacy.APP_VERSION = APP_VERSION
legacy.map_grade_cells = rc3.map_grade_cells_normalized_rc3
legacy.probe_grade_cells = rc1.probe_grade_cells_preview
legacy.print_grade_cell_probe = print_grade_cell_probe_rc15


if __name__ == "__main__":
    legacy.main()
