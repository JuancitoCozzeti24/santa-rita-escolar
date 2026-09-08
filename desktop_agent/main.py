from __future__ import annotations

import json
import os
from datetime import datetime
from pathlib import Path

from browser_controller import ReadOnlyBrowserController
from semantic_inspector import inspect_semantics


APP_NAME = "SIEROOM Desktop Agent"
APP_VERSION = "0.2.0"


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


def save_semantic_report(evidence_dir: Path, semantic) -> Path:
    evidence_dir.mkdir(parents=True, exist_ok=True)
    stamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    path = evidence_dir / f"{stamp}_{semantic.site}_{semantic.page_kind}_semantic.json"
    path.write_text(
        json.dumps(semantic.as_dict(), ensure_ascii=False, indent=2),
        encoding="utf-8",
    )
    return path


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
                name = item.get("text") or "(sin texto)"
                print(f"  - {name}")
        if assignments:
            print("Actividades visibles (muestra):")
            for item in assignments[:12]:
                name = item.get("text") or "(sin texto)"
                print(f"  - {name}")
        return

    if semantic.site == "sieweb":
        selects = summary.get("selects", [])
        tables = summary.get("tables", [])
        fields = summary.get("fields", [])
        print(f"Selectores detectados: {len(selects)}")
        print(f"Tablas detectadas: {len(tables)}")
        print(f"Campos editables detectados (sin leer valores): {len(fields)}")

        if semantic.page_kind == "registro_notas":
            print("OK: pantalla interna de REGISTRO DE NOTAS reconocida.")

        for index, select in enumerate(selects[:10], start=1):
            label = select.get("aria_label") or select.get("name") or select.get("id") or f"selector {index}"
            selected = [o.get("text") for o in select.get("options", []) if o.get("selected")]
            sample = [o.get("text") for o in select.get("options", []) if o.get("text")][:10]
            print(f"  Selector {index}: {label}")
            if selected:
                print(f"    Seleccionado: {', '.join(selected)}")
            if sample:
                print(f"    Opciones visibles: {', '.join(sample)}")

        for index, table in enumerate(tables[:6], start=1):
            headers = table.get("headers", [])
            rows = table.get("rows", [])
            print(f"  Tabla {index}: {len(rows)} filas muestreadas")
            if headers:
                print(f"    Encabezados: {' | '.join(headers[:20])}")
        return

    print("Pantalla no reconocida como Classroom o SIEweb.")


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

    print(f"{APP_NAME} v{APP_VERSION} — EXPLORADOR SEMÁNTICO (SOLO LECTURA)")
    print("No publica notas, comentarios ni modifica SIEweb/Classroom.")
    print("No lee contraseñas ni guarda valores de campos editables.")
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
        print("El agente permanecerá abierto y podrás inspeccionar varias pantallas.")

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
            print(f"Encabezados: {len(report.headings)} | Botones: {len(report.buttons)} | Enlaces: {len(report.links)}")
            print(f"Evidencia básica: {json_path}")
            print(f"Captura: {png_path}")
            print_semantic_summary(semantic)
            print(f"Reporte semántico: {semantic_path}")

            if semantic.site in {"classroom", "sieweb"}:
                print("\nOK: lectura semántica completada sin modificar datos.")
            else:
                print("\nAVISO: esta pantalla todavía no pertenece a Classroom/SIEweb.")

        print("\nCerrando SIEROOM Desktop Agent...")
    finally:
        controller.stop()


if __name__ == "__main__":
    main()
