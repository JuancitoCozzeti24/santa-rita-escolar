from __future__ import annotations

import builtins
import re
from datetime import datetime
from pathlib import Path

import main as legacy
import launcher_v100rc1 as rc1
import launcher_v100rc3 as rc3
import launcher_v100rc15 as rc15
import browser_startup_rc19 as startup19
import performance_plan_stable as stable_plan


APP_VERSION = "1.0.0-stable"
_original_print = builtins.print


def _stable_print(*args, **kwargs):
    patched = []
    for arg in args:
        if isinstance(arg, str):
            text = re.sub(r"\bRC\d+\b", "SIEROOM", arg, flags=re.IGNORECASE)
            patched.append(text)
        else:
            patched.append(arg)
    _original_print(*patched, **kwargs)


def _missing_capacity_count(preview) -> int:
    bootstrap = getattr(preview, "_sieroom_bootstrap", {}) or {}
    unique = set()
    for meta in bootstrap.values():
        if meta.get("capacity_id"):
            continue
        key = (int(meta.get("root_id") or 0), stable_plan._canon(meta.get("capacity")))
        if key[0] and key[1]:
            unique.add(key)
    return len(unique)


def _apply_plan_stable(probe, plan_path: Path) -> None:
    page = probe._page
    plan = rc15.load_plan(plan_path)
    preview = stable_plan.preview_plan(page, plan)
    evidence = plan.get("evidence") or {}

    print("\n============================================================")
    print(" SIEROOM — PLAN DOCENTE: CRITERIOS ANTES DE LAS NOTAS")
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
        status = "YA EXISTE" if item.exists else "PREPARAR"
        print(f"  {item.plan_id}. {item.description} [{status}]")
        print(f"     Capacidad: {item.capacity}")

    evidence_dir = legacy.app_data_root() / "evidence"
    stamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    capacity_count = _missing_capacity_count(preview)
    preflight_path = legacy.save_json(
        evidence_dir,
        f"{stamp}_sieroom_stable_plan_preflight.json",
        {
            "plan_file": str(plan_path),
            "evidence": evidence,
            "missing_capacities": capacity_count,
            **rc15._public_preview(preview),
        },
    )
    print(f"\nEvidencia preflight: {preflight_path}")

    missing = preview.missing
    if missing:
        total = capacity_count + len(missing)
        print(
            f"\nEl plan requiere preparar {capacity_count} capacidad(es) CNEB base y "
            f"{len(missing)} desempeño(s)."
        )
        print("No se escribirá ninguna nota antes de verificar que todos los criterios quedaron persistidos.")
        phrase = f"PREPARAR CRITERIOS {total}"
        typed = legacy.prompt(
            f"Para autorizar SOLO estos criterios escribe exactamente: {phrase}\n> "
        ).strip().upper()
        if typed != phrase:
            print("\nCANCELADO: no se creó ningún criterio ni se escribió ninguna nota.")
            return

        result = stable_plan.create_missing_performances(preview)
        result_path = legacy.save_json(
            evidence_dir,
            f"{stamp}_sieroom_stable_plan_result.json",
            {
                "plan_file": str(plan_path),
                "evidence": evidence,
                "capacities_created": result.get("capacities_created"),
                "performances_created": result.get("created"),
                "existing": result.get("existing"),
                "verification": result.get("verification"),
                "mode": result.get("mode"),
            },
        )
        print(
            "\n✅ CRITERIOS VERIFICADOS: "
            f"capacidades creadas={result.get('capacities_created')} | "
            f"desempeños creados={result.get('created')} | existentes={result.get('existing')}"
        )
        print(f"Evidencia: {result_path}")
    else:
        print("\n✅ Todos los desempeños del plan ya existen exactamente una vez. No se creó nada.")

    print("\nActualizando UNA sola vez la misma libreta para mostrar los criterios...")
    refresh = rc15.rc13._refresh_same_gradebook_once(page)
    if not refresh.get("ok"):
        raise stable_plan.PerformancePlanError(
            f"Los criterios quedaron preparados, pero no se pudo actualizar la vista: {refresh.get('error')}"
        )
    page.wait_for_timeout(1200)

    cell_map = rc3.map_grade_cells_normalized_rc3(page)
    new_probe = rc1.probe_grade_cells_preview(page, cell_map)
    plan_items = rc15._collect_plan_items(new_probe, plan)

    if plan_items:
        print("\n============================================================")
        print(" SIEROOM — CALIFICACIONES DEL PLAN LISTAS PARA ESCRITURA")
        print("============================================================")
        print(f"Celdas preparadas desde el plan: {len(plan_items)}")
        print("Se hará un preflight antes del guardado y se verificará el resultado.")
        original_collect = rc15.rc9._collect_batch
        rc15.rc9._collect_batch = lambda _probe: list(plan_items)
        try:
            rc15.rc13._fast_persisted_batch(new_probe)
        finally:
            rc15.rc9._collect_batch = original_collect
        return

    print("\n✅ FASE DE CRITERIOS TERMINADA.")
    print("El plan actual no contiene calificaciones, por lo que SIEROOM no abrirá un lote manual.")
    print("Esto evita escribir por accidente sobre las 4 columnas generales de competencia.")
    print("Puedes cerrar esta ventana. Cuando el plan incluya notas, SIEROOM exigirá primero asociarlas a los desempeños precisados.")


# Mantener el arranque automático con dos pestañas: Classroom + SIEweb.
startup19.install()

# Reutilizamos la interfaz madura de SIEROOM, pero sustituimos el motor de plan por el
# estable: primero capacidades CNEB faltantes, luego desempeños, siempre verificados.
rc15._apply_plan = _apply_plan_stable
rc15.preview_plan = stable_plan.preview_plan
rc15.create_missing_performances = stable_plan.create_missing_performances
rc15.print = _stable_print
rc15.APP_VERSION = APP_VERSION

# El canal estable no debe volver a mostrar nombres internos RC al usuario.
for _module in (rc15.rc9, rc15.rc13, rc1, rc3):
    try:
        _module.print = _stable_print
    except Exception:
        pass

legacy.APP_VERSION = APP_VERSION
legacy.map_grade_cells = rc3.map_grade_cells_normalized_rc3
legacy.probe_grade_cells = rc1.probe_grade_cells_preview
legacy.print_grade_cell_probe = rc15.print_grade_cell_probe_rc15


if __name__ == "__main__":
    legacy.main()
