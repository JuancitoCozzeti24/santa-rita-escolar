from pathlib import Path

from browser_controller import ReadOnlyBrowserController


def main() -> None:
    root = Path(__file__).resolve().parent
    controller = ReadOnlyBrowserController(
        profile_dir=root / ".browser_profile",
        evidence_dir=root / "evidence",
    )

    print("SIEROOM Desktop Agent — Fase 1 (SOLO LECTURA)")
    print("No publica notas, comentarios ni modifica SIEweb/Classroom.")
    print("Abriendo navegador dedicado...")

    context = controller.start()
    try:
        page = context.pages[0] if context.pages else context.new_page()
        if page.url == "about:blank":
            page.goto("https://classroom.google.com/", wait_until="domcontentloaded")

        print("\nInicia sesión si el perfil todavía no está autenticado.")
        print("Navega a Classroom o SIEweb y luego vuelve a esta ventana.")
        input("Presiona ENTER para inspeccionar la pestaña activa...")

        pages = context.pages
        page = pages[-1]
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
        input("\nPresiona ENTER para cerrar el agente...")
    finally:
        controller.stop()


if __name__ == "__main__":
    main()
