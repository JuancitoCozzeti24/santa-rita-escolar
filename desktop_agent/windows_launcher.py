from __future__ import annotations

from pathlib import Path
from getpass import getpass
import os
import sys

from dotenv import load_dotenv


def _pause() -> None:
    input("\nPresiona Enter para cerrar...")


DEFAULT_BACKEND = "https://santa-rita-escolar-tcpb.onrender.com"


def _configured(app_dir: Path) -> bool:
    if os.getenv("SIEROOM_BACKEND_URL") and os.getenv("SIEROOM_BACKEND_SECRET"):
        return True
    required = {
        "OPENAI_API_KEY": os.getenv("OPENAI_API_KEY"),
        "GOOGLE_CLIENT_ID": os.getenv("GOOGLE_CLIENT_ID"),
        "GOOGLE_CLIENT_SECRET": os.getenv("GOOGLE_CLIENT_SECRET"),
        "GOOGLE_REFRESH_TOKEN": os.getenv("GOOGLE_REFRESH_TOKEN"),
    }
    missing = [name for name, value in required.items() if not value]
    if not missing:
        return True

    print("Conectaremos este EXE con tu SieRoom de Render.")
    backend_url = input(f"Dirección de SieRoom [{DEFAULT_BACKEND}]: ").strip() or DEFAULT_BACKEND
    secret = getpass("Secreto del complemento SieRoom (no se mostrará): ").strip()
    if not secret:
        print("El secreto de conexión no puede estar vacío.")
        return False
    try:
        from desktop_agent.backend import BackendConnection
        from desktop_agent.settings import DesktopSettings
        probe = DesktopSettings(
            data_dir=app_dir / ".sieroom", classroom_url="https://classroom.google.com/",
            cieweb_url="https://santaritadecasia.sieweb.com.pe", model="gpt-5.1",
            openai_api_key="", backend_url=backend_url.rstrip("/"), backend_secret=secret,
        )
        status = BackendConnection(probe).status()
        if not status.get("classroom_configured") or not status.get("openai_configured"):
            print("Render respondió, pero todavía no tiene Google u OpenAI completamente configurado.")
            return False
    except Exception as exc:
        print(f"No se pudo comprobar la conexión con SieRoom: {exc}")
        return False
    env_path = app_dir / ".env"
    env_path.write_text(
        f"SIEROOM_BACKEND_URL={backend_url.rstrip('/')}\nSIEROOM_BACKEND_SECRET={secret}\n",
        encoding="utf-8",
    )
    os.environ["SIEROOM_BACKEND_URL"] = backend_url.rstrip("/")
    os.environ["SIEROOM_BACKEND_SECRET"] = secret
    print("Conexión verificada y guardada únicamente en esta computadora.")
    return True


def main() -> None:
    app_dir = Path(sys.executable).resolve().parent if getattr(sys, "frozen", False) else Path.cwd()
    load_dotenv(app_dir / ".env")
    load_dotenv()
    print("=" * 62)
    print("SIEROOM DESKTOP AGENT — PRUEBA DE CLASSROOM")
    print("=" * 62)
    print("Esta versión primero revisa y NO escribe nada sin tu autorización.")
    if not _configured(app_dir):
        _pause()
        return

    course = input("Curso o sección exacta (ejemplo: 2.º B): ").strip()
    task = input("Título exacto de la tarea: ").strip()
    criteria = input("Ruta del solucionario/criterios TXT (opcional): ").strip().strip('"')
    if not course or not task:
        print("El curso y la tarea son obligatorios.")
        _pause()
        return
    if criteria and not Path(criteria).is_file():
        print(f"No se encontró el archivo de criterios: {criteria}")
        _pause()
        return

    from desktop_agent.classroom_cli import main as classroom_main

    command = ["sieroom-classroom", "--course", course, "--task", task]
    if criteria:
        command.extend(["--criteria-file", criteria])
    try:
        sys.argv = command
        classroom_main()
    except Exception as exc:
        print(f"\nNo se pudo completar la revisión previa: {exc}")
        _pause()
        return

    answer = input("\n¿Publicar ahora comentarios, notas y devoluciones verificadas? [s/N]: ").strip().lower()
    if answer not in {"s", "si", "sí"}:
        print("Prueba terminada sin modificar Classroom.")
        _pause()
        return
    try:
        sys.argv = [*command, "--apply"]
        classroom_main()
    except SystemExit as exc:
        if exc.code not in (None, 0):
            print("El lote se detuvo de forma segura. Puedes volver a abrir el EXE para reanudarlo.")
    except Exception as exc:
        print(f"El lote se detuvo de forma segura: {exc}")
    _pause()


if __name__ == "__main__":
    main()
