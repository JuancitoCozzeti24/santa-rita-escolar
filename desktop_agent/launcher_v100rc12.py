from __future__ import annotations

from datetime import datetime
import builtins
import time
import uuid

import main as legacy
import launcher_v100rc1 as rc1
import launcher_v100rc3 as rc3
import launcher_v100rc9 as rc9
import launcher_v100rc11 as rc11
import verified_writer_bridge as writer
from verified_writer_bridge import VerifiedWriterBridgeError


APP_VERSION = "1.0.0-rc12"
MAX_BATCH = 28
_original_print = builtins.print


def _print_rc12(*args, **kwargs):
    patched = []
    for arg in args:
        if isinstance(arg, str):
            patched.append(arg.replace("RC11", "RC12").replace("RC10", "RC12").replace("RC9", "RC12"))
        else:
            patched.append(arg)
    _original_print(*patched, **kwargs)


rc9.print = _print_rc12
rc9.APP_VERSION = APP_VERSION
rc9.MAX_BATCH = MAX_BATCH


def _fmt(value: str) -> str:
    return value if value else "(vacío)"


def _preflight_batch_once(page, cell_map, items):
    """Valida todo el lote con una sola lectura API de la libreta."""
    if not items:
        raise VerifiedWriterBridgeError("El lote está vacío.")

    dom_codes = [str(s.get("code") or "").strip() for s in (cell_map.students or [])]
    first = items[0]
    base = rc11._prepare_one_cell_write_rc11(
        page,
        dom_student_codes=dom_codes,
        student_code=first["code"],
        student_name=first["name"],
        column_number=int(first["column"]),
        column_label=first["label"],
        dom_current=first["dom_current"],
        proposed=first["grade"],
    )

    client = base.client
    before = base.before
    api_codes = {
        str(s.get("alucod") or "").strip()
        for s in (before.get("students") or [])
        if str(s.get("alucod") or "").strip()
    }
    if set(dom_codes) != api_codes:
        raise VerifiedWriterBridgeError(
            f"La matrícula DOM/API no coincide (DOM={len(set(dom_codes))}, API={len(api_codes)})."
        )

    rows = []
    for item in items:
        if item["code"] not in api_codes:
            raise VerifiedWriterBridgeError(
                f"El alumno {item['code']} no existe en la matrícula API revalidada."
            )
        criterion = writer._match_criterion(client, before, item["label"])
        try:
            header_id = int(criterion.get("id"))
            level = int(criterion.get("nivelEva"))
        except Exception as exc:
            raise VerifiedWriterBridgeError(
                f"La cabecera de {item['code']} no expone id/nivelEva válidos."
            ) from exc
        if level not in {1, 3}:
            raise VerifiedWriterBridgeError(
                f"RC12 bloquea nivelEva={level}; solo admite 1 o 3."
            )
        api_current = writer._student_grade(before, item["code"], header_id)
        dom_current = str(item["dom_current"] or "").strip().upper()
        proposed = str(item["grade"] or "").strip().upper()
        if api_current not in {"", "A", "B", "C"}:
            raise VerifiedWriterBridgeError(
                f"{item['code']}: la API devolvió {api_current!r}, valor no admitido."
            )
        if api_current != dom_current:
            raise VerifiedWriterBridgeError(
                f"{item['code']}: DOM/API discrepan antes del lote "
                f"(DOM={_fmt(dom_current)}, API={_fmt(api_current)})."
            )
        if api_current and api_current != proposed:
            raise VerifiedWriterBridgeError(
                f"{item['code']}: no se sobrescribe {api_current} -> {proposed}."
            )
        rows.append({
            **item,
            "header_id": header_id,
            "criterion_level": level,
            "target_kind": "NIVEL DE LOGRO" if level == 1 else "DESEMPEÑO",
            "api_current": api_current,
            "would_write": api_current != proposed,
        })
    return base, rows


def _scroll_student_into_view(page, code: str) -> None:
    try:
        loc = page.get_by_text(str(code), exact=True)
        if loc.count() >= 1:
            loc.first.scroll_into_view_if_needed(timeout=1500)
            page.wait_for_timeout(55)
    except Exception:
        pass


def _live_target_cell(page, code: str, column: int):
    _scroll_student_into_view(page, code)
    mapped = rc3.map_grade_cells_normalized_rc3(page)
    matches = [
        s for s in (mapped.students or [])
        if str(s.get("code") or "").strip() == str(code).strip()
    ]
    if len(matches) != 1:
        raise VerifiedWriterBridgeError(
            f"El alumno {code} aparece {len(matches)} veces en el DOM actual."
        )
    cell = rc1._target_cell(matches[0], int(column) - 1)
    if not cell:
        raise VerifiedWriterBridgeError(
            f"No se localizó la celda {code}/columna {column} en el DOM actual."
        )
    return cell


def _active_editor_status(page) -> dict:
    try:
        return page.evaluate(
            r"""
            () => {
              const e = document.activeElement;
              if (!e) return {ok:false, tag:'', inCell:false};
              const tag = String(e.tagName || '').toLowerCase();
              const inCell = !!(e.closest && e.closest('.td.bgprograma_3'));
              return {
                ok: ['input','textarea','select'].includes(tag) && inCell,
                tag,
                inCell,
                value: String(e.value || '')
              };
            }
            """
        ) or {}
    except Exception:
        return {}


def _read_live_value(page, code: str, column: int) -> str:
    cell = _live_target_cell(page, code, column)
    confident = bool(cell.get("value_confident"))
    state = str(cell.get("value_state") or "unreadable")
    if not confident or state not in {"blank", "grade"}:
        raise VerifiedWriterBridgeError(
            f"Lectura DOM no confiable para {code}/col {column} "
            f"(estado={state}, confiable={confident})."
        )
    return str(cell.get("text") or "").strip().upper()


def _write_one_via_browser(page, *, code: str, column: int, grade: str) -> dict:
    """Escribe como usuario: click -> teclado -> Tab, sin recargar ni re-seleccionar."""
    current = _read_live_value(page, code, column)
    if current == grade:
        return {"ok": True, "already_present": True, "observed_dom": current, "editor": "no-op"}
    if current and current != grade:
        raise VerifiedWriterBridgeError(
            f"{code}/col {column}: la UI contiene {current}; RC12 no la reemplaza por {grade}."
        )

    cell = _live_target_cell(page, code, column)
    x = float(cell.get("x") or 0) + float(cell.get("width") or 0) / 2
    y = float(cell.get("y") or 0) + float(cell.get("height") or 0) / 2
    if x <= 0 or y <= 0:
        raise VerifiedWriterBridgeError("La celda no expone coordenadas válidas.")

    editor = {}
    for _ in range(2):
        page.mouse.click(x, y)
        page.wait_for_timeout(45)
        editor = _active_editor_status(page)
        if editor.get("ok"):
            break
    if not editor.get("ok"):
        raise VerifiedWriterBridgeError(
            f"{code}/col {column}: SIEweb no abrió el editor nativo de la celda."
        )

    page.keyboard.press("Control+A")
    page.keyboard.type(grade, delay=8)
    page.keyboard.press("Tab")

    for wait_ms in (110, 180, 320, 520):
        page.wait_for_timeout(wait_ms)
        try:
            observed = _read_live_value(page, code, column)
        except VerifiedWriterBridgeError:
            continue
        if observed == grade:
            return {
                "ok": True,
                "already_present": False,
                "observed_dom": observed,
                "editor": "native-click-keyboard-tab",
            }

    observed = ""
    try:
        observed = _read_live_value(page, code, column)
    except Exception:
        pass
    raise VerifiedWriterBridgeError(
        f"{code}/col {column}: la UI no confirmó {grade} después de editar "
        f"(observado={_fmt(observed)})."
    )


def _api_verify_batch(base, rows):
    ctx = base.api_context
    extra = {"idPeriodoAnt": int(ctx.get("idPeriodoAnt") or 0)}
    client = base.client
    last = None
    for attempt in range(1, 4):
        if attempt > 1:
            time.sleep(0.35 * attempt)
        after = client.get_gradebook_summary(
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
                "header_id": int(row["header_id"]),
                "expected": row["grade"],
                "observed": observed,
                "ok": ok,
            })
            all_ok = all_ok and ok
        last = (after, checks, all_ok)
        if all_ok:
            break
    return last


def _fast_batch_preflight_and_execute(probe) -> None:
    page = probe._page
    cell_map = probe._cell_map
    items = rc9._collect_batch(probe)
    if not items:
        return

    batch_id = f"SIEWEB-RC12-{datetime.now().strftime('%Y%m%d-%H%M%S')}-{uuid.uuid4().hex[:8]}"
    evidence_dir = legacy.app_data_root() / "evidence"

    print("\nRC12: preflight único de la libreta (una sola lectura API)...")
    try:
        base, rows = _preflight_batch_once(page, cell_map, items)
    except VerifiedWriterBridgeError as exc:
        print(f"\n❌ LOTE BLOQUEADO: {exc}")
        legacy.prompt("Presiona ENTER para cerrar el agente...")
        raise SystemExit(0)

    preflight_payload = {
        "batch_id": batch_id,
        "created_at": datetime.now().isoformat(timespec="seconds"),
        "mode": "FAST_NATIVE_BROWSER_BATCH_RC12",
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
        evidence_dir, f"{batch_id}_fast_batch_preflight.json", preflight_payload
    )

    print("\n============================================================")
    print(" PREFLIGHT FINAL RC12 — MODO RÁPIDO DE PESTAÑA")
    print("============================================================")
    for idx, row in enumerate(rows, start=1):
        action = "ESCRIBIR EN PESTAÑA" if row["would_write"] else "YA PRESENTE"
        print(
            f"{idx}. {row['code']} | {row['name']} | col {row['column']} | "
            f"{row['target_kind']} | DOM {_fmt(row['dom_current'])} | "
            f"API {_fmt(row['api_current'])} | nuevo {row['grade']} | {action}"
        )
    print(f"\nEvidencia preflight: {preflight_path}")
    print("\nRC12 NO recargará SIEweb entre alumnos.")
    print("Controlará la pestaña: click en celda -> escribe -> Tab -> siguiente alumno.")
    print("Al terminar hará UNA verificación API global del lote.")

    phrase = f"ESCRIBIR RAPIDO {len(rows)}"
    typed = legacy.prompt(
        f"Para autorizar el lote rápido escribe exactamente: {phrase}\n> "
    ).strip().upper()
    if typed != phrase:
        print("\nCANCELADO: no se escribió ninguna nota.")
        legacy.prompt("Presiona ENTER para cerrar el agente...")
        raise SystemExit(0)

    network_events = []

    def on_response(resp):
        try:
            url = str(resp.url or "")
            method = str(resp.request.method or "").upper()
            if "/lms/api/hyoclasenota/actualizar" in url.lower() and method in {"PUT", "POST", "PATCH"}:
                network_events.append({
                    "status": int(resp.status),
                    "method": method,
                    "url": url.split("?")[0],
                })
        except Exception:
            pass

    page.on("response", on_response)
    execution = []
    stopped = False
    stop_reason = ""

    print("\n============================================================")
    print(" RC12 — AGENTE CONTROLANDO LA PESTAÑA")
    print("============================================================")
    try:
        for idx, row in enumerate(rows, start=1):
            print(
                f"[{idx}/{len(rows)}] {row['code']} | {row['name']} | "
                f"col {row['column']} | {row['grade']} ...",
                end=" ", flush=True,
            )
            before_network = len(network_events)
            try:
                result = _write_one_via_browser(
                    page,
                    code=row["code"],
                    column=int(row["column"]),
                    grade=row["grade"],
                )
                page.wait_for_timeout(90)
                execution.append({
                    "index": idx,
                    "student_code": row["code"],
                    "student_name": row["name"],
                    "column": int(row["column"]),
                    "header_id": int(row["header_id"]),
                    "proposed": row["grade"],
                    "observed_dom": result.get("observed_dom"),
                    "already_present": bool(result.get("already_present")),
                    "network_save_events_delta": len(network_events) - before_network,
                    "ui_ok": True,
                })
                print("✅")
            except VerifiedWriterBridgeError as exc:
                stopped = True
                stop_reason = str(exc)
                execution.append({
                    "index": idx,
                    "student_code": row["code"],
                    "student_name": row["name"],
                    "column": int(row["column"]),
                    "proposed": row["grade"],
                    "ui_ok": False,
                    "error": str(exc),
                })
                print(f"❌ {exc}")
                break
    finally:
        try:
            page.remove_listener("response", on_response)
        except Exception:
            pass

    verification = []
    api_ok = False
    unexpected = []
    if not stopped:
        print("\nVerificación API global del lote, sin recargar la pestaña...")
        try:
            after, verification, api_ok = _api_verify_batch(base, rows)
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

    final_ok = bool(not stopped and api_ok and not unexpected)
    final_payload = {
        "batch_id": batch_id,
        "finished_at": datetime.now().isoformat(timespec="seconds"),
        "mode": "FAST_NATIVE_BROWSER_BATCH_RC12",
        "requested_count": len(rows),
        "ui_completed_count": sum(1 for x in execution if x.get("ui_ok")),
        "network_save_events": network_events,
        "verification": verification,
        "unexpected_grade_changes": unexpected,
        "verified": final_ok,
        "stopped": bool(stopped),
        "stop_reason": stop_reason,
        "execution": execution,
    }
    final_path = legacy.save_json(
        evidence_dir, f"{batch_id}_fast_batch_result.json", final_payload
    )

    print("\n============================================================")
    print(" RESULTADO FINAL RC12")
    print("============================================================")
    if final_ok:
        print(f"✅ LOTE RÁPIDO VERIFICADO: {len(rows)}/{len(rows)} celdas.")
        print("La pestaña no fue recargada ni se reeligió Salón/Curso/Período entre notas.")
    else:
        print("⚠️ LOTE RÁPIDO NO QUEDÓ TOTALMENTE VERIFICADO.")
        if stop_reason:
            print(f"Motivo: {stop_reason}")
        print("No se ejecutarán más celdas automáticamente.")
    print(f"Eventos de guardado observados en la pestaña: {len(network_events)}")
    print(f"Evidencia final: {final_path}")
    legacy.prompt("Presiona ENTER cuando quieras cerrar el agente...")
    raise SystemExit(0)


rc9._batch_preflight_and_execute = _fast_batch_preflight_and_execute

legacy.APP_VERSION = APP_VERSION
legacy.map_grade_cells = rc3.map_grade_cells_normalized_rc3
legacy.probe_grade_cells = rc1.probe_grade_cells_preview
legacy.print_grade_cell_probe = rc9.print_grade_cell_probe_rc9


if __name__ == "__main__":
    legacy.main()
