from __future__ import annotations

import os
from pathlib import Path

from browser_controller import ReadOnlyBrowserController


APP_NAME = "SIEROOM Desktop Agent"
APP_VERSION = "0.1.2"


def app_data_root() -> Path:
    if os.name == "nt":
        base = os.environ.get("LOCALAPPDATA") or os.environ.get("APPDATA")
        if base:
            return Path(base) / "SIEROOM" / "DesktopAgent"
    return Path.home() / ".sieroom" / "desktop_agent"


def pause(message: str) -> None:
    try:
        input(message)
    except EOFError:
        pass


def main() -> None:
    data_root = app_data_root()
    controller = ReadOnlyBrowserController(
        profile_dir=data_root / "browser_profile",
        evidence_dir=data_root / "evidence",
    )

    print(f"{APP_NAME} v{APP_VERSION} — Fase 1 (SOLO LECTURA)")
    print("No publica notas, comentarios ni modifica SIEweb/Classroom.")
    print(f"Datos locales persistentes: {data_root}")
    print("Abriendo navegador dedicado en modo normal...")

    try:
        context = controller.start()
    except Exception as exc:
        print("\nNo se pudo abrir el navegador dedicado.")
        print("El agente busca Google Chrome y, como respaldo, Microsoft Edge.")
        print(f"Detalle técnico: {exc}")
        pause("\nPresiona ENTER para cerrar...")
        raise SystemExit(2) from exc

    try:
        print(f"\nNavegador detectado: {controller.browser_name}")
        print("Classroom se abrió en una sesión persistente exclusiva para SIEROOM.")
        print("Si es la primera vez, inicia sesión normalmente en Google.")
        print("Cuando Classroom o SIEweb ya haya terminado de cargar, vuelve a esta ventana.")
        pause("Presiona ENTER para inspeccionar Classroom/SIEweb...")

        pages = controller.describe_pages(context)
        if not pages:
            print("No hay ninguna pestaña abierta para inspeccionar.")
            pause("Presiona ENTER para cerrar...")
            return

        print("\nPestañas detectadas:")
        for index, (title, url) in enumerate(pages, start=1):
            print(f"  {index}. {title or '(sin título)'}")
            print(f"     {url}")

        page = controller.select_target_page(context)
        if page is None:
            print("No se encontró una pestaña inspeccionable.")
            pause("Presiona ENTER para cerrar...")
            return

        selected_site = controller.detect_site(page.url)
        if selected_site == "google_classroom_info":
            print("\nSe detectó la página informativa de Google Classroom, no la aplicación.")
            print("Abriendo la aplicación real de Classroom en una pestaña nueva...")
            app_page = context.new_page()
            try:
                app_page.goto(
                    "https://classroom.google.com/u/0/h",
                    wait_until="domcontentloaded",
                    timeout=30000,
                )
            except Exception:
                pass
            pause("Espera a que Classroom cargue y presiona ENTER para continuar...")
            page = controller.select_target_page(context) or app_page

        report = controller.inspect(page)
        json_path, png_path = controller.save_evidence(page, report)

        print("\n--- REPORTE ---")
        print(f"Sitio detectado: {report.site}")
        print(f"Título: {report.title}")
        print(f"URL: {report.url}")
        print(f"Encabezados detectados: {len(report.headings)}")
        print(f"Botones detectados: {len(report.buttons)}")
        print(f"Enlaces detectados: {len(report.links)}")
        print(f"Campos detectados: {len(report.inputs)}")
        print(f"Reporte JSON: {json_path}")
        print(f"Captura: {png_path}")

        if report.site == "classroom":
            print("\nOK: Classroom real fue detectado correctamente.")
        elif report.site == "sieweb":
            print("\nOK: SIEweb fue detectado correctamente.")
        else:
            print("\nAVISO: todavía no se está inspeccionando Classroom ni SIEweb.")

        pause("\nPresiona ENTER para cerrar el agente...")
    finally:
        controller.stop()


if __name__ == "__main__":
    main()
