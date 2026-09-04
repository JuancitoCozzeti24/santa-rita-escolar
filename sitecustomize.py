from __future__ import annotations

import functools
import sys


def _patch_bridge_policy() -> None:
    """Instala el contrato comentario -> nota -> devolución del Bridge."""
    try:
        from bridge_policy_hotfix import install as install_bridge_policy

        install_bridge_policy()
        print("SieRoom Bridge: contrato triple R6.2 activo.", flush=True)
    except Exception as exc:
        print(f"SieRoom Bridge: no se pudo instalar contrato triple R6.2: {exc}", flush=True)


def _patch_fastmcp_init_for_download() -> None:
    """Registra la descarga ZIP en cada instancia FastMCP desde su creación."""
    try:
        from mcp.server.fastmcp import FastMCP
    except Exception:
        return

    original_init = FastMCP.__init__
    if getattr(original_init, "_sieroom_bridge_download_bootstrap", False):
        return

    @functools.wraps(original_init)
    def init_with_bridge_download(self, *args, **kwargs):
        original_init(self, *args, **kwargs)
        try:
            from bridge_download import install as install_bridge_download

            install_bridge_download(self)
            print("SieRoom Bridge: descarga ZIP R6.2 habilitada en FastMCP init.", flush=True)
        except Exception as exc:
            print(f"SieRoom Bridge: no se pudo habilitar descarga ZIP en init: {exc}", flush=True)

    setattr(init_with_bridge_download, "_sieroom_bridge_download_bootstrap", True)
    FastMCP.__init__ = init_with_bridge_download


def _patch_fastmcp_run() -> None:
    """Reactiva las rutas auxiliares justo antes de levantar FastMCP."""
    try:
        from mcp.server.fastmcp import FastMCP
    except Exception:
        return

    original_run = FastMCP.run
    if getattr(original_run, "_sieroom_attendance_bootstrap", False):
        return

    @functools.wraps(original_run)
    def run_with_attendance(self, *args, **kwargs):
        main = sys.modules.get("__main__")
        namespace = vars(main) if main is not None else {}

        if namespace.get("mcp") is self and not getattr(self, "_sieroom_attendance_installed", False):
            sieweb = namespace.get("sieweb")
            settings = namespace.get("settings")
            classroom = namespace.get("classroom")
            if sieweb is not None and settings is not None:
                from attendance import install as install_attendance

                install_attendance(self, sieweb, settings, classroom)
                setattr(self, "_sieroom_attendance_installed", True)
                print("SieRoom Asistencia: rutas /asesoria restauradas.", flush=True)

        return original_run(self, *args, **kwargs)

    setattr(run_with_attendance, "_sieroom_attendance_bootstrap", True)
    FastMCP.run = run_with_attendance


_patch_bridge_policy()
_patch_fastmcp_init_for_download()
_patch_fastmcp_run()
