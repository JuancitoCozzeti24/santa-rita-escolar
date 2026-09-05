from __future__ import annotations

import functools
import sys
from pathlib import Path


R62_BUILD = "0.8.7-HF4-GRADE-TARGET-DEDUP-SINGLE-PASS-R6.2"
R68_BUILD = "0.8.7-HF4-R6.8-CLAIM-CAPABILITY-RESTORE"
R69_BUILD = "0.8.7-HF4-R6.9-DETAILED-FEEDBACK-CORE"


def _patch_bridge_claim_compat_source() -> None:
    """Compatibiliza el servidor 0.8.7 con Bridge R6.8/R6.9 antes de importar server_core.

    El servidor histórico reclamaba trabajos solo si el header Build era exactamente
    R6.2. R6.9.2 anuncia el build R6.9, por lo que /bridge/v1/next respondía 200 pero
    nunca entregaba el job. Este bootstrap conserva todas las capacidades/guardas
    existentes y amplía únicamente la lista de builds admitidos para lectura/post.
    """
    path = Path(__file__).with_name("server_core.py")
    try:
        text = path.read_text(encoding="utf-8")
        changed = False

        old_builds = (
            'HF4_CONTENT_BUILDS = {HF4_CONTENT_BUILD, '
            '"0.8.7-HF4-GRADE-TARGET-DEDUP-R4", '
            '"0.8.7-HF4-GRADE-TARGET-DEDUP-R4-DEDUP-R4", '
            '"0.8.7-HF4-GRADE-TARGET-DEDUP-R5", '
            '"0.8.7-HF4-GRADE-TARGET-DEDUP-SINGLE-PASS-R6", '
            '"0.8.7-HF4-GRADE-TARGET-DEDUP-SINGLE-PASS-R6.1", '
            '"0.8.7-HF4-GRADE-TARGET-DEDUP-SINGLE-PASS-R6.2"}'
        )
        new_builds = (
            'HF4_CONTENT_BUILDS = {HF4_CONTENT_BUILD, '
            '"0.8.7-HF4-GRADE-TARGET-DEDUP-R4", '
            '"0.8.7-HF4-GRADE-TARGET-DEDUP-R4-DEDUP-R4", '
            '"0.8.7-HF4-GRADE-TARGET-DEDUP-R5", '
            '"0.8.7-HF4-GRADE-TARGET-DEDUP-SINGLE-PASS-R6", '
            '"0.8.7-HF4-GRADE-TARGET-DEDUP-SINGLE-PASS-R6.1", '
            '"0.8.7-HF4-GRADE-TARGET-DEDUP-SINGLE-PASS-R6.2", '
            '"0.8.7-HF4-R6.8-CLAIM-CAPABILITY-RESTORE", '
            '"0.8.7-HF4-R6.9-DETAILED-FEEDBACK-CORE"}'
        )
        if old_builds in text:
            text = text.replace(old_builds, new_builds, 1)
            changed = True
        elif new_builds not in text:
            raise RuntimeError("No se encontró la definición esperada de HF4_CONTENT_BUILDS.")

        old_claim = f'and bridge_build == "{R62_BUILD}"'
        new_claim = (
            'and bridge_build in {'
            f'"{R62_BUILD}", "{R68_BUILD}", "{R69_BUILD}"'
            '}'
        )
        occurrences = text.count(old_claim)
        if occurrences:
            # Deben ser post_capable y read_capable. No se relaja cleanup, que
            # conserva su contrato/método específico R6.2.
            if occurrences != 2:
                raise RuntimeError(
                    f"Se esperaban 2 filtros R6.2 de claim y se encontraron {occurrences}."
                )
            text = text.replace(old_claim, new_claim)
            changed = True
        elif text.count(new_claim) != 2:
            raise RuntimeError("No se encontró el filtro de claim esperado ni su versión parcheada.")

        if changed:
            path.write_text(text, encoding="utf-8")
            print(
                "SieRoom Bridge: CLAIM COMPAT servidor activo para R6.2/R6.8/R6.9; "
                "lectura/post R6.9 habilitados.",
                flush=True,
            )
        else:
            print("SieRoom Bridge: CLAIM COMPAT servidor ya estaba aplicado.", flush=True)
    except Exception as exc:
        # Fail loud: si este hotfix no se aplica, el servicio puede arrancar pero
        # volvería a aceptar /next sin entregar trabajos, que es precisamente el
        # fallo que queremos evitar diagnosticar a ciegas.
        print(f"SieRoom Bridge: ERROR aplicando CLAIM COMPAT servidor: {exc}", flush=True)
        raise


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


_patch_bridge_claim_compat_source()
_patch_bridge_policy()
_patch_fastmcp_init_for_download()
_patch_fastmcp_run()
