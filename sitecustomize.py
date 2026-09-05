from __future__ import annotations

import functools
import sys
from pathlib import Path


R62_BUILD = "0.8.7-HF4-GRADE-TARGET-DEDUP-SINGLE-PASS-R6.2"
R68_BUILD = "0.8.7-HF4-R6.8-CLAIM-CAPABILITY-RESTORE"
R69_BUILD = "0.8.7-HF4-R6.9-DETAILED-FEEDBACK-CORE"
R696_CONTENT_BUILD = "0.8.7-HF4-R6.9.6-EXISTING-FEEDBACK-SEND"


def _patch_bridge_claim_compat_source() -> None:
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
            '"0.8.7-HF4-R6.9-DETAILED-FEEDBACK-CORE", '
            '"0.8.7-HF4-R6.9.6-EXISTING-FEEDBACK-SEND"}'
        )
        if old_builds in text:
            text = text.replace(old_builds, new_builds, 1)
            changed = True
        elif new_builds not in text:
            raise RuntimeError("No se encontró la definición esperada de HF4_CONTENT_BUILDS.")
        old_claim = f'and bridge_build == "{R62_BUILD}"'
        new_claim = 'and bridge_build in {' + f'"{R62_BUILD}", "{R68_BUILD}", "{R69_BUILD}"' + '}'
        occurrences = text.count(old_claim)
        if occurrences:
            if occurrences != 2:
                raise RuntimeError(f"Se esperaban 2 filtros R6.2 de claim y se encontraron {occurrences}.")
            text = text.replace(old_claim, new_claim)
            changed = True
        elif text.count(new_claim) != 2:
            raise RuntimeError("No se encontró el filtro de claim esperado ni su versión parcheada.")
        if changed:
            path.write_text(text, encoding="utf-8")
            print("SieRoom Bridge: CLAIM COMPAT servidor activo para R6.2/R6.8/R6.9/R6.9.6; lectura/post habilitados.", flush=True)
        else:
            print("SieRoom Bridge: CLAIM COMPAT servidor ya estaba aplicado.", flush=True)
    except Exception as exc:
        print(f"SieRoom Bridge: ERROR aplicando CLAIM COMPAT servidor: {exc}", flush=True)
        raise


def _patch_feedback_policy_source() -> None:
    path = Path(__file__).with_name("server.py")
    try:
        text = path.read_text(encoding="utf-8")
        changed = False
        old_rule = (
            "1. Antes de publicar un comentario privado, SieRoom debe comprobar la entrega. "
            "Si ya existe cualquier comentario privado, queda prohibido publicar otro, aunque el texto sea distinto. "
            "La escritura solo puede continuar cuando la lectura verificada devuelve exactamente cero comentarios existentes."
        )
        new_rule = (
            "1. Antes de publicar un comentario privado, SieRoom debe comprobar la entrega exacta y auditar el panel privado. "
            "Los comentarios escritos por el estudiante y los comentarios docentes breves o administrativos NO bloquean la retroalimentación académica. "
            "Si ya existe una retroalimentación perteneciente a la cuenta docente con los bloques LO QUE HICISTE BIEN, LO QUE DEBES CORREGIR/MEJORAR y SUGERENCIAS, no se publica una segunda retroalimentación estructurada; se conserva la existente y se continúa con la nota/devolución si corresponde."
        )
        if old_rule in text:
            text = text.replace(old_rule, new_rule, 1)
            changed = True
        elif new_rule not in text:
            raise RuntimeError("No se encontró la regla histórica de comentarios privados.")
        old_dict = (
            '        "private_comment_existing_guard": "strict",\n'
            '        "write_allowed_only_when_existing_comment_count": 0,\n'
            '        "duplicate_or_second_comment_allowed": False,\n'
        )
        new_dict = (
            '        "private_comment_existing_guard": "teacher_owned_structured_feedback",\n'
            '        "student_comments_block_new_feedback": False,\n'
            '        "administrative_teacher_comments_block_new_feedback": False,\n'
            '        "duplicate_structured_teacher_feedback_allowed": False,\n'
            '        "continue_grade_return_when_structured_feedback_exists": True,\n'
        )
        if old_dict in text:
            text = text.replace(old_dict, new_dict, 1)
            changed = True
        elif new_dict not in text:
            raise RuntimeError("No se encontró el diccionario histórico de classroom_feedback_policy.")
        old_rule_item = (
            '            "No inventar aciertos ni errores no verificados en la entrega.",\n'
            '            "Explicar cada error con suficiente detalle para enseñar el procedimiento correcto.",\n'
        )
        new_rule_item = (
            '            "No inventar aciertos ni errores no verificados en la entrega.",\n'
            '            "Los comentarios del alumno no bloquean la retroalimentación docente estructurada.",\n'
            '            "Explicar cada error con suficiente detalle para enseñar el procedimiento correcto.",\n'
        )
        if old_rule_item in text:
            text = text.replace(old_rule_item, new_rule_item, 1)
            changed = True
        elif new_rule_item not in text:
            raise RuntimeError("No se encontró la lista de reglas de classroom_feedback_policy.")
        if changed:
            path.write_text(text, encoding="utf-8")
            print("SieRoom Bridge: política de feedback R6.9 alineada con autor docente + estructura.", flush=True)
        else:
            print("SieRoom Bridge: política de feedback R6.9 ya estaba alineada.", flush=True)
    except Exception as exc:
        print(f"SieRoom Bridge: ERROR alineando política de feedback R6.9: {exc}", flush=True)
        raise


def _patch_bridge_policy() -> None:
    try:
        from bridge_policy_hotfix import install as install_bridge_policy
        install_bridge_policy()
        print("SieRoom Bridge: contrato triple R6.2 activo.", flush=True)
    except Exception as exc:
        print(f"SieRoom Bridge: no se pudo instalar contrato triple R6.2: {exc}", flush=True)


def _patch_fastmcp_init_for_download() -> None:
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
    """Reactiva rutas auxiliares y encola la revisión masiva ya verificada de C1 Midiendo Nuestro Avance."""
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
        if namespace.get("mcp") is self and not getattr(self, "_sieroom_c1_midiendo_mass_enqueued", False):
            classroom = namespace.get("classroom")
            bridge_queue = namespace.get("bridge_queue")
            if classroom is not None and bridge_queue is not None:
                try:
                    from one_shot_c1_midiendo_mass import enqueue_mass
                    result = enqueue_mass(classroom, bridge_queue)
                    setattr(self, "_sieroom_c1_midiendo_mass_enqueued", True)
                    print(f"C1_MIDIENDO_MASS_STARTUP: queued={result.get('queued')} count={result.get('count')} work={result.get('work')}", flush=True)
                except Exception as exc:
                    print(f"C1_MIDIENDO_MASS_ERROR: {exc}", flush=True)
        return original_run(self, *args, **kwargs)
    setattr(run_with_attendance, "_sieroom_attendance_bootstrap", True)
    FastMCP.run = run_with_attendance


_patch_bridge_claim_compat_source()
_patch_feedback_policy_source()
_patch_bridge_policy()
_patch_fastmcp_init_for_download()
_patch_fastmcp_run()
