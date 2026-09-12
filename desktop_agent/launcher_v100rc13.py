from __future__ import annotations

from collections import defaultdict
from datetime import datetime
import builtins
import uuid

import main as legacy
import launcher_v100rc1 as rc1
import launcher_v100rc3 as rc3
import launcher_v100rc7 as rc7
import launcher_v100rc9 as rc9
import launcher_v100rc12 as rc12
import verified_writer_bridge as writer
from verified_writer_bridge import VerifiedWriterBridgeError


APP_VERSION = "1.0.0-rc13"
MAX_BATCH = 28
_original_print = builtins.print


def _print_rc13(*args, **kwargs):
    patched = []
    for arg in args:
        if isinstance(arg, str):
            patched.append(
                arg.replace("RC12", "RC13")
                .replace("RC11", "RC13")
                .replace("RC10", "RC13")
                .replace("RC9", "RC13")
            )
        else:
            patched.append(arg)
    _original_print(*patched, **kwargs)


rc9.print = _print_rc13
rc9.APP_VERSION = APP_VERSION
rc9.MAX_BATCH = MAX_BATCH


def _fmt(value: str) -> str:
    return value if value else "(vacío)"


def _group_rows(rows):
    groups = defaultdict(list)
    for row in rows:
        groups[(int(row["header_id"]), int(row["criterion_level"]))].append(row)
    return list(groups.items())


def _save_group(base, *, header_id: int, criterion_level: int, rows: list[dict]):
    """Persiste varias notas de UNA misma cabecera en una sola operación verificada.

    No toca el DOM ni recarga la pestaña. Usa exactamente la sesión autenticada
    tomada del navegador durante el preflight de RC12/RC11.
    """
    if not rows:
        return {"saved": True, "already_present": True, "requested": 0}

    to_write = {
        str(row["code"]): str(row["grade"]).strip().upper()
        for row in rows
        if bool(row.get("would_write"))
    }
    if not to_write:
        return {
            "saved": True,
            "already_present": True,
            "requested": len(rows),
            "written": 0,
        }

    ctx = base.api_context
    class_info = base.before.get("class") or {}
    scope = class_info.get("arrNivelGrado") or class_info.get("objNG")
    class_name = str(
        (ctx.get("course") or {}).get("NOMCLASE")
        or (ctx.get("course") or {}).get("NOMBRE")
        or ctx.get("section")
        or ""
    )
    extra = {"idPeriodoAnt": int(ctx.get("idPeriodoAnt") or 0)}

    kwargs = {
        "year": str(base.browser_context["year"]),
        "course_code": str(base.browser_context["course_code"]),
        "class_period_id": int(ctx["idClasePeriodo"]),
        "root_content_id": int(ctx["idContenido"]),
        "period": int(ctx["periodo"]),
        "section_ng": scope,
        "header_id": int(header_id),
        "grades_by_student_code": to_write,
        "class_name": class_name,
        "extra_params": extra,
        "notify": False,
        "verification_attempts": 3,
    }
    if int(criterion_level) == 1:
        kwargs.update(
            protect_achievement_level=False,
            performance_level=1,
            allow_achievement_level=True,
        )
    elif int(criterion_level) == 3:
        kwargs.update(
            protect_achievement_level=True,
            performance_level=3,
            allow_achievement_level=False,
        )
    else:
        raise VerifiedWriterBridgeError(
            f"RC13 bloquea nivelEva={criterion_level}; solo admite 1 o 3."
        )

    try:
        result = base.client.save_grades_verified(**kwargs)
    except Exception as exc:
        raise VerifiedWriterBridgeError(
            f"No se pudo persistir la cabecera {header_id}: {exc}"
        ) from exc

    if not bool(result.get("saved")):
        raise VerifiedWriterBridgeError(
            f"SIEweb no confirmó el guardado de la cabecera {header_id}."
        )

    return {
        "saved": True,
        "already_present": False,
        "requested": len(rows),
        "written": len(to_write),
        "writer_mode": result.get("mode"),
        "verification": result.get("verification"),
        "verification_attempts": result.get("verification_attempts"),
        "non_target_verification": result.get("non_target_verification"),
    }


def _verify_api_all(base, rows):
    ctx = base.api_context
    extra = {"idPeriodoAnt": int(ctx.get("idPeriodoAnt") or 0)}
    after = base.client.get_gradebook_summary(
        class_period_id=int(ctx["idClasePeriodo"]),
        root_content_id=int(ctx["idContenido"]),
        extra_params=extra,
    )

    checks = []
    all_ok = True
    for row in rows:
        observed = writer._student_grade(after, row["code"], int(row["header_id"]))
        ok = observed == row["grade"]
        checks.append({
            "student_code": row["code"],
            "student_name": row["name"],
            "header_id": int(row["header_id"]),
            "column": int(row["column"]),
            "expected": row["grade"],
            "observed": observed,
            "ok": ok,
        })
        all_ok = all_ok and ok
    return after, checks, all_ok


def _refresh_same_gradebook_once(page) -> dict:
    """Actualiza SOLO la libreta una vez conservando Salón/Curso/Período.

    Evita page.reload(), porque SIEweb puede perder el contexto de la SPA.
    """
    try:
        before = rc7._selector_snapshot(page)
        period = rc7._find_snapshot(before, "periodo") or rc7._find_snapshot(before, "período")
        if not period:
            return {"ok": False, "error": "No se localizó el selector de período."}

        rc7._select_same_value(page, period)
        page.wait_for_timeout(1250)

        after = rc7._selector_snapshot(page)
        # Comprobación defensiva: salón, curso y período deben seguir presentes.
        for name in ("salón", "salon", "curso", "periodo", "período"):
            old = rc7._find_snapshot(before, name)
            new = rc7._find_snapshot(after, name)
            if old and new:
                old_text = str(old.get("text") or old.get("value") or "").strip()
                new_text = str(new.get("text") or new.get("value") or "").strip()
                if old_text and new_text and old_text != new_text:
                    return {
                        "ok": False,
                        "error": f"El selector {name} cambió durante la actualización ({old_text!r} -> {new_text!r}).",
                    }
        return {"ok": True}
    except Exception as exc:
        return {"ok": False, "error": str(exc)}


def _verify_dom_rows(page, rows) -> tuple[list[dict], bool]:
    checks = []
    all_ok = True
    for row in rows:
        observed = ""
        error = ""
        try:
            observed = rc12._read_live_value(page, row["code"], int(row["column"]))
            ok = observed == row["grade"]
        except Exception as exc:
            ok = False
            error = str(exc)
        checks.append({
            "student_code": row["code"],
            "student_name": row["name"],
            "column": int(row["column"]),
            "expected": row["grade"],
            "observed": observed,
            "ok": ok,
            "error": error,
        })
        all_ok = all_ok and ok
    return checks, all_ok


def _fast_persisted_batch(probe) -> None:
    page = probe._page
    cell_map = probe._cell_map
    items = rc9._collect_batch(probe)
    if not items:
        return

    batch_id = f"SIEWEB-RC13-{datetime.now().strftime('%Y%m%d-%H%M%S')}-{uuid.uuid4().hex[:8]}"
    evidence_dir = legacy.app_data_root() / "evidence"

    print("\nRC13: preflight único de la libreta (solo lectura)...")
    try:
        base, rows = rc12._preflight_batch_once(page, cell_map, items)
    except VerifiedWriterBridgeError as exc:
        print(f"\n❌ LOTE BLOQUEADO: {exc}")
        legacy.prompt("Presiona ENTER para cerrar el agente...")
        raise SystemExit(0)

    preflight_payload = {
        "batch_id": batch_id,
        "created_at": datetime.now().isoformat(timespec="seconds"),
        "mode": "FAST_PERSISTED_BATCH_RC13",
        "write_enabled": True,
        "requested_count": len(rows),
        "items": [{
            "student_order": r["order"],
            "student_code": r["code"],
            "student_name": r["name"],
            "column": r["column"],
            "column_label": r["label"],
            "header_id": r["header_id"],
            "criterion_level": r["criterion_level"],
            "target_kind": r["target_kind"],
            "dom_current": r["dom_current"],
            "api_current": r["api_current"],
            "proposed": r["grade"],
            "would_write": r["would_write"],
        } for r in rows],
    }
    preflight_path = legacy.save_json(
        evidence_dir, f"{batch_id}_fast_persisted_preflight.json", preflight_payload
    )

    print("\n============================================================")
    print(" PREFLIGHT FINAL RC13 — GUARDADO RÁPIDO REAL")
    print("============================================================")
    for idx, row in enumerate(rows, start=1):
        action = "GUARDAR" if row["would_write"] else "YA PRESENTE"
        print(
            f"{idx}. {row['code']} | {row['name']} | col {row['column']} | "
            f"{row['target_kind']} | API {_fmt(row['api_current'])} -> {row['grade']} | {action}"
        )
    print(f"\nEvidencia preflight: {preflight_path}")
    print("\nRC13 NO escribirá valores temporales en el DOM.")
    print("Persistirá el lote usando la sesión autenticada del navegador,")
    print("agrupando por competencia y SIN recargar entre alumnos.")
    print("Al final actualizará la MISMA libreta una sola vez y verificará API + pantalla.")

    phrase = f"GUARDAR RAPIDO {len(rows)}"
    typed = legacy.prompt(
        f"Para autorizar el lote escribe exactamente: {phrase}\n> "
    ).strip().upper()
    if typed != phrase:
        print("\nCANCELADO: no se escribió ninguna nota.")
        legacy.prompt("Presiona ENTER para cerrar el agente...")
        raise SystemExit(0)

    group_results = []
    stopped = False
    stop_reason = ""

    print("\n============================================================")
    print(" RC13 — PERSISTENCIA RÁPIDA SIN RECARGAS POR ALUMNO")
    print("============================================================")

    groups = _group_rows(rows)
    for index, ((header_id, level), group_rows) in enumerate(groups, start=1):
        pending = sum(1 for row in group_rows if row.get("would_write"))
        print(
            f"[{index}/{len(groups)}] Cabecera {header_id} | nivelEva={level} | "
            f"{pending} nueva(s) de {len(group_rows)} ...",
            end=" ", flush=True,
        )
        try:
            result = _save_group(
                base,
                header_id=header_id,
                criterion_level=level,
                rows=group_rows,
            )
            group_results.append({
                "header_id": header_id,
                "criterion_level": level,
                "student_codes": [r["code"] for r in group_rows],
                **result,
            })
            print("✅")
        except VerifiedWriterBridgeError as exc:
            stopped = True
            stop_reason = str(exc)
            group_results.append({
                "header_id": header_id,
                "criterion_level": level,
                "student_codes": [r["code"] for r in group_rows],
                "saved": False,
                "error": str(exc),
            })
            print(f"❌ {exc}")
            break

    api_checks = []
    api_ok = False
    unexpected = []
    after = None

    if not stopped:
        print("\nVerificación API global del lote...")
        try:
            after, api_checks, api_ok = _verify_api_all(base, rows)
            before_snap = writer._grade_snapshot(base.before)
            after_snap = writer._grade_snapshot(after)
            target_keys = {f"{r['code']}:{r['header_id']}" for r in rows}
            for key in sorted(set(before_snap) | set(after_snap)):
                if key in target_keys:
                    continue
                if before_snap.get(key, "") != after_snap.get(key, ""):
                    unexpected.append({
                        "cell": key,
                        "before": before_snap.get(key, ""),
                        "after": after_snap.get(key, ""),
                    })
            if unexpected:
                api_ok = False
                stop_reason = f"Se detectaron {len(unexpected)} cambios inesperados fuera del lote."
        except Exception as exc:
            api_ok = False
            stop_reason = f"La verificación API final falló: {exc}"

    refresh = {"ok": False, "error": "No ejecutado."}
    dom_checks = []
    dom_ok = False
    if not stopped and api_ok:
        print("API confirmada. Actualizando la misma libreta UNA sola vez...")
        refresh = _refresh_same_gradebook_once(page)
        if refresh.get("ok"):
            dom_checks, dom_ok = _verify_dom_rows(page, rows)
        else:
            dom_ok = False

    server_verified = bool(not stopped and api_ok and not unexpected)
    fully_verified = bool(server_verified and refresh.get("ok") and dom_ok)

    final_payload = {
        "batch_id": batch_id,
        "finished_at": datetime.now().isoformat(timespec="seconds"),
        "mode": "FAST_PERSISTED_BATCH_RC13",
        "requested_count": len(rows),
        "group_count": len(groups),
        "group_results": group_results,
        "api_verification": api_checks,
        "unexpected_grade_changes": unexpected,
        "server_verified": server_verified,
        "refresh": refresh,
        "dom_verification": dom_checks,
        "fully_verified": fully_verified,
        "stopped": stopped,
        "stop_reason": stop_reason,
    }
    final_path = legacy.save_json(
        evidence_dir, f"{batch_id}_fast_persisted_result.json", final_payload
    )

    print("\n============================================================")
    print(" RESULTADO FINAL RC13")
    print("============================================================")
    if fully_verified:
        print(f"✅ LOTE GUARDADO Y VERIFICADO: {len(rows)}/{len(rows)} celdas.")
        print("No hubo recarga ni reselección entre alumnos; solo una actualización final de la libreta.")
    elif server_verified:
        print(f"✅ SIEWEB CONFIRMÓ EL GUARDADO DEL LOTE: {len(rows)}/{len(rows)} celdas.")
        print("⚠️ La comprobación visual final no pudo completarse totalmente.")
        print("Las notas SÍ quedaron confirmadas por API; no se reintentará para evitar duplicar acciones.")
        if not refresh.get("ok"):
            print(f"Detalle actualización visual: {refresh.get('error')}")
    else:
        print("❌ EL LOTE NO QUEDÓ VERIFICADO EN SIEWEB.")
        if stop_reason:
            print(f"Motivo: {stop_reason}")
        print("No se continuará automáticamente.")

    print(f"Evidencia final: {final_path}")
    legacy.prompt("Presiona ENTER cuando quieras cerrar el agente...")
    raise SystemExit(0)


rc9._batch_preflight_and_execute = _fast_persisted_batch

legacy.APP_VERSION = APP_VERSION
legacy.map_grade_cells = rc3.map_grade_cells_normalized_rc3
legacy.probe_grade_cells = rc1.probe_grade_cells_preview
legacy.print_grade_cell_probe = rc9.print_grade_cell_probe_rc9


if __name__ == "__main__":
    legacy.main()
