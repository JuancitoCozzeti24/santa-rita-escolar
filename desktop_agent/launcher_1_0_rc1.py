from __future__ import annotations

import json
import sys
from datetime import datetime
from pathlib import Path

from browser_controller import ReadOnlyBrowserController
from editor_open_probe import normalize_grade_view
from grade_cell_mapper import map_grade_cells
from grade_cell_probe import probe_grade_cells
from page_context import detect_academic_context
from roster_guard import validate_roster
from verified_writer_bridge import (
    execute_single_cell,
    get_verified_client,
    prepare_single_cell,
)


APP_NAME = "SIEROOM Desktop Agent"
APP_VERSION = "1.0 RC1"
SIEWEB_REGISTRO_URL = "https://santaritadecasia.sieweb.com.pe/sistema/intranet/registroNotas"


def app_data_root() -> Path:
    import os
    if os.name == "nt":
        base = os.environ.get("LOCALAPPDATA") or os.environ.get("APPDATA")
        if base:
            return Path(base) / "SIEROOM" / "DesktopAgent"
    return Path.home() / ".sieroom" / "desktop_agent"


def prompt(message: str) -> str:
    try:
        return input(message).strip()
    except EOFError:
        return "q"


def _save_audit(payload: dict) -> Path:
    root = app_data_root() / "audit"
    root.mkdir(parents=True, exist_ok=True)
    stamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    path = root / f"{stamp}_verified_writer_rc1.json"
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
    return path


def _find_or_open_sieweb(context):
    for page in context.pages:
        if not page.is_closed() and "santaritadecasia.sieweb.com.pe" in str(page.url or ""):
            return page
    page = context.new_page()
    try:
        page.goto(SIEWEB_REGISTRO_URL, wait_until="domcontentloaded", timeout=30000)
    except Exception:
        pass
    return page


def _column_label(probe, index: int) -> str:
    row = probe.columns[index]
    return str(row.get("semantic_header") or row.get("header") or f"Columna {index + 1}").strip()


def _find_student_by_order(cell_map, order: int):
    matches = [row for row in cell_map.students if int(str(row.get("order") or 0)) == int(order)]
    if len(matches) != 1:
        raise RuntimeError(f"No se encontró de forma única el número de orden {order}.")
    return matches[0]


def _print_simple_context(ctx, cell_map, probe, roster_check) -> None:
    pretty = {"S2A": "2.º A", "S2B": "2.º B", "S5A": "5.º A", "S5B": "5.º B"}.get(ctx.section, ctx.section)
    print("\n============================================================")
    print("  PREPARACIÓN VERIFICADA")
    print("============================================================")
    print(f"Sección : {pretty}")
    print(f"Período : {ctx.period}")
    print(f"Curso   : {ctx.course_code} - {ctx.course_name}")
    print(f"Alumnos : {roster_check.observed_count}/{roster_check.expected_count} verificados")
    print(f"Columnas: {probe.column_count}")
    if ctx.id_ambito is None:
        print("Escritura: BLOQUEADA (idAmbito aún no resuelto)")
    else:
        print(f"Contexto : verificado (idAmbito {ctx.id_ambito}, origen {ctx.id_ambito_source})")
    print("\nCompetencias/cabeceras visibles:")
    for idx in range(probe.column_count):
        print(f"  {idx + 1}. {_column_label(probe, idx)}")


def _print_students(cell_map) -> None:
    print("\nAlumnos de la sección:")
    for row in cell_map.students:
        order = str(row.get("order") or "?").rjust(2)
        print(f"  {order}. {row.get('code')} | {row.get('name') or '(nombre no aislado)'}")


def _print_preflight(preflight, auth_mode: str) -> None:
    pretty = {"S2A": "2.º A", "S2B": "2.º B", "S5A": "5.º A", "S5B": "5.º B"}.get(preflight.section, preflight.section)
    print("\n============================================================")
    print("  UNA SOLA CELDA — PREVISUALIZACIÓN")
    print("============================================================")
    print(f"Sección     : {pretty}")
    print(f"Período     : {preflight.period}")
    print(f"Estudiante  : {preflight.student_code} | {preflight.student_name}")
    print(f"Cabecera    : {preflight.header_label}")
    print(f"nivelEva    : {preflight.performance_level}")
    print(f"Nota actual : {preflight.current_grade or '(vacía)'}")
    print(f"Nueva nota  : {preflight.requested_grade}")
    print(f"Autenticación escritor: {auth_mode}")
    print("\nProtecciones activas:")
    print("  ✓ nómina navegador = nómina autorizada 2026")
    print("  ✓ nómina API = nómina autorizada 2026")
    print("  ✓ alumno identificado por código")
    print("  ✓ cabecera resuelta en la libreta real")
    print("  ✓ solo una celda en RC1")
    print("  ✓ notificaciones desactivadas")
    print("  ✓ relectura obligatoria después del PUT")
    if preflight.performance_level == 1:
        print("  ✓ HF12: Nivel de logro explícito, solo A/B/C y verificación de celdas no objetivo")


def main() -> None:
    data_root = app_data_root()
    controller = ReadOnlyBrowserController(
        profile_dir=data_root / "browser_profile",
        evidence_dir=data_root / "evidence",
    )

    print(f"{APP_NAME} {APP_VERSION} — PREVIEW + VERIFIED WRITER")
    print("Esta versión reemplaza las sondas 0.9.x.")
    print("Puede preparar una operación real, pero RC1 limita la escritura a UNA sola celda.")
    print("NUNCA escribe sin la frase exacta de confirmación.")
    print(f"Datos locales: {data_root}")

    try:
        context = controller.start()
    except Exception as exc:
        print(f"\nNo pude abrir el navegador dedicado: {exc}")
        prompt("Presiona ENTER para cerrar...")
        return

    try:
        page = _find_or_open_sieweb(context)
        try:
            page.bring_to_front()
        except Exception:
            pass

        print("\n1) En Edge, inicia sesión en SIEweb si fuera necesario.")
        print("2) Entra a Registro de Notas y selecciona sección, Matemática y período.")
        print("3) Cuando veas la lista completa de alumnos, vuelve aquí.")
        prompt("\nPresiona ENTER para analizar la pantalla (Q para cancelar): ")

        try:
            if "/registroNotas" not in str(page.url or ""):
                page.goto(SIEWEB_REGISTRO_URL, wait_until="domcontentloaded", timeout=30000)
                page.wait_for_timeout(800)
            ctx = detect_academic_context(page)
            changed = normalize_grade_view(page)
            if changed:
                page.wait_for_timeout(250)
            cell_map = map_grade_cells(page)
            probe = probe_grade_cells(page, cell_map)
        except Exception as exc:
            print(f"\n❌ PREPARACIÓN BLOQUEADA: {exc}")
            prompt("Presiona ENTER para cerrar...")
            return

        browser_codes = [str(row.get("code") or "").strip() for row in cell_map.students]
        roster_check = validate_roster(ctx.section, browser_codes)
        if not roster_check.ok:
            print("\n❌ PROTECCIÓN DE NÓMINA: la pantalla no coincide con la lista autorizada.")
            print(roster_check.summary())
            if roster_check.missing:
                print("Faltan: " + ", ".join(roster_check.missing))
            if roster_check.unexpected:
                print("No esperados: " + ", ".join(roster_check.unexpected))
            prompt("Presiona ENTER para cerrar...")
            return
        if cell_map.mapped_student_count != roster_check.expected_count:
            print(
                f"\n❌ MAPEO INCOMPLETO: {cell_map.mapped_student_count}/{roster_check.expected_count} "
                "alumnos tienen celdas asociadas. No se habilita escritura."
            )
            prompt("Presiona ENTER para cerrar...")
            return
        if probe.column_count <= 0:
            print("\n❌ No se detectaron columnas de calificación. No se habilita escritura.")
            prompt("Presiona ENTER para cerrar...")
            return

        _print_simple_context(ctx, cell_map, probe, roster_check)
        print("\nRC1 está en PREVISUALIZACIÓN. Hasta aquí no se ha cambiado nada.")
        choice = prompt("\nP = preparar UNA nota | Q = salir sin escribir: ").lower()
        if choice not in {"p", "preparar"}:
            print("\nSalida sin escrituras.")
            prompt("Presiona ENTER para cerrar...")
            return
        if ctx.id_ambito is None:
            print("\n❌ Escritura bloqueada: idAmbito no fue resuelto de forma segura.")
            prompt("Presiona ENTER para cerrar...")
            return

        _print_students(cell_map)
        raw_order = prompt("\nEscribe el NÚMERO DE ORDEN del alumno (sin ENTER automático): ")
        if not raw_order.isdigit():
            print("Entrada cancelada o inválida. No se escribió nada.")
            prompt("Presiona ENTER para cerrar...")
            return
        student = _find_student_by_order(cell_map, int(raw_order))

        print("\nElige la columna:")
        for idx in range(probe.column_count):
            print(f"  {idx + 1}. {_column_label(probe, idx)}")
        raw_col = prompt("Número de columna: ")
        if not raw_col.isdigit() or not (1 <= int(raw_col) <= probe.column_count):
            print("Columna inválida. No se escribió nada.")
            prompt("Presiona ENTER para cerrar...")
            return
        col_index = int(raw_col) - 1
        label = _column_label(probe, col_index)

        grade = prompt("Nueva nota [A/B/C]: ").upper()
        if grade not in {"A", "B", "C"}:
            print("Nota inválida. RC1 solo admite A/B/C. No se escribió nada.")
            prompt("Presiona ENTER para cerrar...")
            return

        print("\nAutenticando el escritor verificado (preferencia: sesión actual de Edge)...")
        try:
            client, auth_mode = get_verified_client(page, id_ambito=int(ctx.id_ambito))
            preflight = prepare_single_cell(
                client=client,
                browser_codes=browser_codes,
                page_context=ctx,
                student_code=str(student.get("code") or ""),
                visible_column_label=label,
                requested_grade=grade,
            )
        except Exception as exc:
            print(f"\n❌ PREFLIGHT BLOQUEADO: {exc}")
            prompt("Presiona ENTER para cerrar...")
            return

        _print_preflight(preflight, auth_mode)
        if preflight.current_grade == preflight.requested_grade:
            print("\nLa celda ya contiene esa misma nota. No hace falta enviar ningún PUT.")
            audit = _save_audit({
                "version": APP_VERSION,
                "timestamp": datetime.now().isoformat(),
                "status": "VERIFIED_ALREADY_CORRECT",
                "section": preflight.section,
                "period": preflight.period,
                "student_code": preflight.student_code,
                "student_name": preflight.student_name,
                "header_id": preflight.header_id,
                "header_label": preflight.header_label,
                "level": preflight.performance_level,
                "grade": preflight.requested_grade,
                "write_sent": False,
            })
            print("\n✅ VERIFICADO: la nota ya estaba guardada. No se modificó nada.")
            print(f"Auditoría: {audit}")
            prompt("Presiona ENTER para cerrar...")
            return

        print("\nATENCIÓN: el siguiente paso sí puede modificar UNA celda real de SIEweb.")
        print("Para autorizar exactamente esta única operación escribe:")
        print("  ESCRIBIR 1 CELDA")
        confirmation = prompt("Confirmación: ")
        if confirmation != "ESCRIBIR 1 CELDA":
            audit = _save_audit({
                "version": APP_VERSION,
                "timestamp": datetime.now().isoformat(),
                "status": "CANCELLED_BEFORE_WRITE",
                "section": preflight.section,
                "period": preflight.period,
                "student_code": preflight.student_code,
                "header_id": preflight.header_id,
                "requested_grade": preflight.requested_grade,
                "write_sent": False,
            })
            print("\nCancelado. No se envió ninguna escritura.")
            print(f"Auditoría: {audit}")
            prompt("Presiona ENTER para cerrar...")
            return

        print("\nEnviando UNA celda mediante save_grades_verified y releyendo SIEweb...")
        try:
            result = execute_single_cell(client, preflight)
            verification = result.get("verification") or {}
            ok = verification.get("ok") is True
            if not ok:
                raise RuntimeError("La relectura no confirmó la celda.")
            audit = _save_audit({
                "version": APP_VERSION,
                "timestamp": datetime.now().isoformat(),
                "status": "VERIFIED",
                "section": preflight.section,
                "period": preflight.period,
                "student_code": preflight.student_code,
                "student_name": preflight.student_name,
                "header_id": preflight.header_id,
                "header_label": preflight.header_label,
                "level": preflight.performance_level,
                "before": preflight.current_grade,
                "after": preflight.requested_grade,
                "mode": result.get("mode"),
                "write_sent": bool(result.get("saved")),
                "verification": {
                    "ok": verification.get("ok"),
                    "requested_count": verification.get("requested_count"),
                    "verified_count": verification.get("verified_count"),
                    "failed_count": verification.get("failed_count"),
                },
                "non_target_verification": result.get("non_target_verification"),
            })
            print("\n✅ VERIFICADO: SIEweb fue releído y confirmó la única celda autorizada.")
            print(f"   {preflight.student_name}: {preflight.current_grade or '(vacía)'} → {preflight.requested_grade}")
            print(f"Auditoría: {audit}")
        except Exception as exc:
            audit = _save_audit({
                "version": APP_VERSION,
                "timestamp": datetime.now().isoformat(),
                "status": "NO_VERIFICADO",
                "section": preflight.section,
                "period": preflight.period,
                "student_code": preflight.student_code,
                "header_id": preflight.header_id,
                "requested_grade": preflight.requested_grade,
                "error": str(exc),
            })
            print(f"\n❌ NO VERIFICADO: {exc}")
            print("No se intentará ninguna segunda celda.")
            print(f"Auditoría: {audit}")

        prompt("\nPresiona ENTER para cerrar el agente...")
    finally:
        controller.stop()


if __name__ == "__main__":
    main()
