from __future__ import annotations

import json
import os
from datetime import datetime
from pathlib import Path

from browser_controller import ReadOnlyBrowserController
from gradebook_mapper import map_gradebook
from semantic_inspector import inspect_semantics


APP_NAME = "SIEROOM Desktop Agent"
APP_VERSION = "0.4.0"


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
    if mapped.grade_like_values:
        print(f"Valores con forma de calificación detectados: {', '.join(mapped.grade_like_values[:30])}")
    else:
        print("Valores con forma de calificación detectados: ninguno")

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
            sample = [cell.get("text", "") for cell in cells if cell.get("text", "")][:8]
            if sample:
                print(f"     Muestra celdas: {' | '.join(sample)[:240]}")
    else:
        print("\nNo se aislaron todavía filas de estudiantes por código de 8 dígitos.")

    for frame in mapped.frames:
        print(
            f"\n  Frame {frame.get('frame_index', 0) + 1}: "
            f"accesible={'sí' if frame.get('accessible') else 'no'} | "
            f"tablas={frame.get('table_count', 0)} | "
            f"grillas={frame.get('grid_count', 0)} | "
            f"filas-candidatas={frame.get('candidate_row_count', 0)} | "
            f"estudiantes={frame.get('student_row_count', 0)} | "
            f"controles={frame.get('control_count', 0)}"
        )
        print(f"    URL frame: {frame.get('frame_url', '')}")

        headers = frame.get("header_cells", [])
        if headers:
            print("    Encabezados geométricos (muestra):")
            for header in headers[:12]:
                rect = header.get("rect", {})
                print(
                    f"      x={rect.get('x', '?')} ancho={rect.get('width', '?')} :: "
                    f"{header.get('text', '')[:180]}"
                )

        for table in frame.get("tables", [])[:4]:
            print(
                f"    Tabla {table.get('table_index', 0) + 1}: "
                f"{table.get('total_rows', 0)} filas DOM"
            )
            headers_table = table.get("headers", [])
            if headers_table:
                print(f"      Encabezados: {' | '.join(headers_table[:14])}")


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

    print(f"{APP_NAME} v{APP_VERSION} — IDENTIFICACIÓN DE ESTUDIANTES (SOLO LECTURA)")
    print("No publica notas, comentarios ni modifica SIEweb/Classroom.")
    print("Busca filas reales de estudiantes usando el código SIEweb de 8 dígitos y geometría DOM.")
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
                    if mapped.student_row_count:
                        print(
                            f"OK: {mapped.student_row_count} filas de estudiantes fueron aisladas "
                            "sin modificar datos."
                        )
                    else:
                        print("AVISO: aún no se aislaron filas de estudiantes.")
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
