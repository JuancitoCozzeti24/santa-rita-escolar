from __future__ import annotations

from pathlib import Path
from getpass import getpass
import os
import sys
import json
import shutil

from dotenv import load_dotenv
from desktop_agent.backend import BackendClassroomClient, BackendConnection
from desktop_agent.classroom_cli import main as classroom_main
from desktop_agent.settings import DesktopSettings


def _pause() -> None:
    input("\nPresiona Enter para cerrar...")


DEFAULT_BACKEND = "https://santa-rita-escolar-tcpb.onrender.com"
KEYRING_SERVICE = "SieRoom Desktop Agent"
KEYRING_USER = "backend-secret"


def _windows_config_dir() -> Path:
    root = Path(os.getenv("LOCALAPPDATA") or (Path.home() / "AppData" / "Local"))
    return root / "SieRoom Desktop Agent"


def _load_saved_connection() -> bool:
    try:
        import keyring
        config_path = _windows_config_dir() / "settings.json"
        if not config_path.is_file():
            return False
        data = json.loads(config_path.read_text(encoding="utf-8"))
        backend_url = str(data.get("backend_url") or "").rstrip("/")
        secret = str(keyring.get_password(KEYRING_SERVICE, KEYRING_USER) or "")
        if not backend_url or not secret:
            return False
        os.environ["SIEROOM_BACKEND_URL"] = backend_url
        os.environ["SIEROOM_BACKEND_SECRET"] = secret
        return True
    except Exception:
        return False


def _save_connection(backend_url: str, secret: str) -> None:
    import keyring
    config_dir = _windows_config_dir()
    config_dir.mkdir(parents=True, exist_ok=True)
    (config_dir / "settings.json").write_text(
        json.dumps({"backend_url": backend_url.rstrip("/")}, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )
    keyring.set_password(KEYRING_SERVICE, KEYRING_USER, secret)


def _configure_persistent_data(app_dir: Path) -> None:
    target = _windows_config_dir() / "data"
    target.mkdir(parents=True, exist_ok=True)
    candidates = {Path.cwd() / ".sieroom", app_dir / ".sieroom"}
    for old in candidates:
        try:
            if old.is_dir() and old.resolve() != target.resolve():
                shutil.copytree(old, target, dirs_exist_ok=True)
        except OSError:
            pass
    os.environ["SIEROOM_DESKTOP_DATA"] = str(target)


def _configured(app_dir: Path) -> bool:
    if _load_saved_connection():
        return True
    if os.getenv("SIEROOM_BACKEND_URL") and os.getenv("SIEROOM_BACKEND_SECRET"):
        try:
            _save_connection(os.environ["SIEROOM_BACKEND_URL"], os.environ["SIEROOM_BACKEND_SECRET"])
        except Exception:
            pass
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
    _save_connection(backend_url, secret)
    os.environ["SIEROOM_BACKEND_URL"] = backend_url.rstrip("/")
    os.environ["SIEROOM_BACKEND_SECRET"] = secret
    print("Conexión verificada. El secreto quedó protegido en las credenciales de Windows.")
    return True


def _choose(label: str, rows: list[dict[str, object]], display) -> dict[str, object]:
    if not rows:
        raise RuntimeError(f"No se encontraron opciones para {label}.")
    print(f"\n{label}:")
    for index, row in enumerate(rows, 1):
        print(f"  {index}. {display(row)}")
    while True:
        answer = input("Escribe el número: ").strip()
        if answer.isdigit() and 1 <= int(answer) <= len(rows):
            return rows[int(answer) - 1]
        print(f"Elige un número entre 1 y {len(rows)}.")


def main() -> None:
    app_dir = Path(sys.executable).resolve().parent if getattr(sys, "frozen", False) else Path.cwd()
    load_dotenv(app_dir / ".env")
    load_dotenv()
    print("=" * 62)
    print("SIEROOM DESKTOP AGENT v0.4 — CLASSROOM")
    print("=" * 62)
    print("Esta versión primero revisa y NO escribe nada sin tu autorización.")
    if not _configured(app_dir):
        _pause()
        return
    _configure_persistent_data(app_dir)

    connection = BackendConnection(DesktopSettings.from_env())
    classroom = BackendClassroomClient(connection)
    try:
        course_row = _choose(
            "CURSOS DE CLASSROOM",
            classroom.list_courses(active_only=True),
            lambda row: f"{row.get('name') or '(sin nombre)'} — {row.get('section') or 'sin sección'}",
        )
        course = str(course_row["id"])
        assignments = [
            row for row in classroom.list_coursework(course, include_drafts=False)
            if str(row.get("workType") or "") == "ASSIGNMENT"
        ]
        task_row = _choose(
            "TAREAS PUBLICADAS",
            assignments,
            lambda row: str(row.get("title") or "(sin título)"),
        )
        task = str(task_row["id"])
    except Exception as exc:
        print(f"No se pudieron cargar los cursos y tareas: {exc}")
        _pause()
        return
    command = ["sieroom-classroom", "--course", course, "--task", task]
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
