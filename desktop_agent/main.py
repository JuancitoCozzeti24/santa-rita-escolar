from __future__ import annotations

import json
import os
from datetime import datetime
from pathlib import Path

from browser_controller import ReadOnlyBrowserController
from grade_cell_mapper import map_grade_cells
from gradebook_mapper import map_gradebook
from semantic_inspector import inspect_semantics


APP_NAME = "SIEROOM Desktop Agent"
APP_VERSION = "0.5.0"


def app_data_root() -> Path:
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


def save_json(evidence_dir: Path, filename: str, payload: dict) -> Path:
    evidence_dir.mkdir(parents=True, exist_ok=True)
    path = evidence_dir / filename
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
    return path


def save_semantic_report(evidence_dir: Path, semantic) -> Path:
    stamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    return save_json(
        evidence_dir,
        f"{stamp}_{semantic.site}_{semantic.page_kind}_semantic.json",
        semantic.as_dict(),
    )


def print_semantic_summary(semantic) -> None:
    summary = semantic.summary
    print("\n--- LECTURA SEMÁNTICA ---")
    print(f"Sistema: {semantic.site}")
    print(f"Tipo de pantalla: {semantic.page_kind}")

    if semantic.site == "classroom":
        courses = summary.get("course_links", [])
        assignments = summary.get("assignment_links", [])
        print(f"Cursos/enlaces de curso detectados: {len(courses)}")
        print(f"Actividades/enlaces de actividad detectados: {len(assignments)}")
        if courses:
            print("Cursos visibles (muestra):")
            for item in courses[:12]:
                print(f"  - {item.get('text') or '(sin texto)'}")
        if assignments:
            print("Actividades visibles (muestra):")
            for item in assignments[:12]:
                print(f"  - {item.get('text') or '(sin texto)'}")
        return

    if semantic.site == "sieweb":
        selects = summary.get("selects", [])
        tables = summary.get("tables", [])
        fields = summary.get("fields", [])
        print(f"Selectores detectados: {len(selects)}")
        print(f"Tablas detectadas: {len(tables)}")
        print(f"Campos editables detectados: {len(fields)}")
        if semantic.page_kind == "registro_notas":
            print("OK: pantalla interna de REGISTRO DE NOTAS reconocida.")
        for index, table in enumerate(tables[:6], start=1):
            headers = table.get("headers", [])
            rows = table.get("rows", [])
            print(f"  Tabla {index}: {len(rows)} filas muestreadas")
            if headers:
                print(f"    Encabezados: {' | '.join(headers[:20])}")
        return

    print("Pantalla no reconocida como Classroom o SIEweb.")


def print_gradebook_map(mapped) -> None:
    print("\n--- MAPEO DE REGISTRO DE NOTAS ---")
    print(f"Frames/documentos inspeccionados: {mapped.frame_count}")
    print(f"Tablas DOM totales: {mapped.table_count}")
    print(f"Grillas ARIA totales: {mapped.grid_count}")
    print(f"Filas candidatas DIV/grid: {mapped.candidate_row_count}")
    print(f"ESTUDIANTES IDENTIFICADOS POR CÓDIGO: {mapped.student_row_count}")
    print(f"Controles visibles no secretos: {mapped.control_count}")

    if mapped.student_rows:
        print("\n--- FILAS DE ESTUDIANTES IDENTIFICADAS ---")
        for student in mapped.student_rows[:40]:
            controls = len(student.get("controls", []))
            cells = student.get("cells", [])
            print(
                f"  Orden {student.get('order') or '?':>2} | "
                f"Código {student.get('code', '')} | "
                f"{student.get('name') or '(nombre no aislado)'} | "
                f"celdas={len(cells)} controles={controls}"
            )
    else:
        print("\nNo se aislaron todavía filas de estudiantes por código de 8 dígitos.")


def print_grade_cell_map(cell_map) -> None:
    print("\n--- MAPEO GEOMÉTRICO DE CELDAS DE NOTA ---")
    print(f"Estudiantes base: {cell_map.student_count}")
    print(f"Estudiantes con celdas de nota asociadas: {cell_map.mapped_student_count}")
    print(f"COLUMNAS DE NOTA REPETIDAS DETECTADAS: {cell_map.column_count}")

    if cell_map.columns:
        print("\nColumnas detectadas:")
        for col in cell_map.columns[:30]:
            header = col.get("header") or "(encabezado aún no aislado)"
            print(
                f"  Col {col.get('index', 0) + 1:>2} | x={col.get('x')} | "
                f"ancho≈{col.get('average_width')} | soporte={col.get('support')} | {header[:150]}"
            )
            sample_class = col.get("sample_class") or ""
            if sample_class:
                print(f"       clase muestra: {sample_class[:180]}")

    print("\nMuestra estudiante → celdas de nota:")
    for student in cell_map.students[:12]:
        cells = student.get("grade_cells", [])
        xs = ", ".join(str(cell.get("x")) for cell in cells)
        print(
            f"  Orden {student.get('order') or '?':>2} | {student.get('code')} | "
            f"{student.get('name') or '(sin nombre)'} | celdas_nota={len(cells)} | x=[{xs}]"
        )


def choose_page(controller: ReadOnlyBrowserController, context, choice: str):
    pages = [page for page in context.pages if not page.is_closed()]
    if choice.isdigit():
        index = int(choice) - 1
        if 0 <= index < len(pages):
            return pages[index]
        print("Número de pestaña inválido; usaré la mejor pestaña detectada.")
    return controller.select_target_page(context)


def main() -> None:
    data_root = app_data_root()
    evidence_dir = data_root / "evidence"
    controller = ReadOnlyBrowserController(
        profile_dir=data_root / "browser_profile",
        evidence_dir=evidence_dir,
    )

    print(f"{APP_NAME} v{APP_VERSION} — MAPEO ESTUDIANTE → CELDA (SOLO LECTURA)")
    print("No publica notas, comentarios ni modifica SIEweb/Classroom.")
    print("Relaciona cada fila de estudiante con las celdas visuales de calificación por geometría.")
    print("Nunca lee campos password/hidden y no realiza escrituras.")
    print(f"Datos locales persistentes: {data_root}")
    print("Abriendo navegador dedicado en modo normal...")

    try:
        context = controller.start()
    except Exception as exc:
        print("\nNo se pudo abrir el navegador dedicado.")
        print("El agente busca Google Chrome y, como respaldo, Microsoft Edge.")
        print(f"Detalle técnico: {exc}")
        prompt("\nPresiona ENTER para cerrar...")
        raise SystemExit(2) from exc

    try:
        print(f"\nNavegador detectado: {controller.browser_name}")
        print("Puedes navegar libremente por Classroom y SIEweb.")
        print("El agente permanecerá abierto para inspeccionar varias pantallas.")

        while True:
            pages_info = controller.describe_pages(context)
            print("\nPestañas detectadas:")
            for index, (title, url) in enumerate(pages_info, start=1):
                print(f"  {index}. {title or '(sin título)'}")
                print(f"     {url}")

            choice = prompt(
                "\nENTER = inspeccionar mejor pestaña | número = pestaña específica | Q = salir: "
            )
            if choice.lower() in {"q", "quit", "salir"}:
                break

            page = choose_page(controller, context, choice)
            if page is None:
                print("No se encontró una pestaña inspeccionable.")
                continue

            selected_site = controller.detect_site(page.url)
            if selected_site == "google_classroom_info":
                print("Se detectó la página informativa de Google Classroom.")
                print("Abriendo la aplicación real de Classroom...")
                app_page = context.new_page()
                try:
                    app_page.goto(
                        "https://classroom.google.com/u/0/h",
                        wait_until="domcontentloaded",
                        timeout=30000,
                    )
                except Exception:
                    pass
                page = app_page
                prompt("Espera a que Classroom cargue y presiona ENTER para inspeccionarlo...")

            report = controller.inspect(page)
            semantic = inspect_semantics(page)
            json_path, png_path = controller.save_evidence(page, report)
            semantic_path = save_semantic_report(evidence_dir, semantic)

            print("\n--- REPORTE BÁSICO ---")
            print(f"Sitio detectado: {report.site}")
            print(f"Título: {report.title}")
            print(f"URL: {report.url}")
            print(
                f"Encabezados: {len(report.headings)} | "
                f"Botones: {len(report.buttons)} | Enlaces: {len(report.links)}"
            )
            print(f"Evidencia básica: {json_path}")
            print(f"Captura: {png_path}")
            print_semantic_summary(semantic)
            print(f"Reporte semántico: {semantic_path}")

            if semantic.site == "sieweb" and semantic.page_kind == "registro_notas":
                try:
                    mapped = map_gradebook(page)
                    stamp = datetime.now().strftime("%Y%m%d_%H%M%S")
                    mapped_path = save_json(
                        evidence_dir,
                        f"{stamp}_sieweb_registro_notas_gradebook_map.json",
                        mapped.as_dict(),
                    )
                    print_gradebook_map(mapped)
                    print(f"\nMapa detallado de libreta: {mapped_path}")

                    cell_map = map_grade_cells(page)
                    cell_path = save_json(
                        evidence_dir,
                        f"{stamp}_sieweb_registro_notas_grade_cells.json",
                        cell_map.as_dict(),
                    )
                    print_grade_cell_map(cell_map)
                    print(f"Mapa estudiante→celda: {cell_path}")

                    if mapped.student_row_count and cell_map.mapped_student_count:
                        print(
                            f"OK: {mapped.student_row_count} estudiantes aislados; "
                            f"{cell_map.mapped_student_count} asociados a celdas visuales, sin modificar datos."
                        )
                    else:
                        print("AVISO: aún falta completar la asociación estudiante→celda.")
                except Exception as exc:
                    print(f"AVISO: no se pudo completar el mapeo profundo: {exc}")

            if semantic.site in {"classroom", "sieweb"}:
                print("\nOK: lectura completada sin modificar datos.")
            else:
                print("\nAVISO: esta pantalla todavía no pertenece a Classroom/SIEweb.")

        print("\nCerrando SIEROOM Desktop Agent...")
    finally:
        controller.stop()


if __name__ == "__main__":
    main()
