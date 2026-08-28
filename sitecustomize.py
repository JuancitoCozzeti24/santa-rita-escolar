from __future__ import annotations

import functools
import json
import re
import sys


def _patch_fastmcp_run() -> None:
    """Reactiva las rutas de asistencia sin modificar el servidor principal."""
    try:
        from mcp.server.fastmcp import FastMCP
    except Exception:
        return

    original_run = FastMCP.run
    if getattr(original_run, "_sieroom_attendance_bootstrap", False):
        return

    @functools.wraps(original_run)
    def run_with_attendance(self, *args, **kwargs):
        if not getattr(self, "_sieroom_attendance_installed", False):
            main = sys.modules.get("__main__")
            namespace = vars(main) if main is not None else {}
            if namespace.get("mcp") is self:
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


def _patch_sieweb_grade_contract() -> None:
    """Corrige objNG: SIEweb espera arrNivelGrado, no arrNGS."""
    try:
        from sieweb import SieWebClient, SieWebError
    except Exception:
        return

    original_update = SieWebClient.update_grades
    if getattr(original_update, "_sieroom_arr_nivel_grado_hotfix", False):
        return

    def normalize(value):
        raw = value
        if isinstance(raw, str):
            text = raw.strip()
            if not text:
                raise SieWebError("objNG/arrNivelGrado está vacío; no se enviaron notas.")
            if text.startswith("[") or text.startswith("{"):
                try:
                    raw = json.loads(text)
                except ValueError as exc:
                    raise SieWebError("objNG/arrNivelGrado contiene JSON inválido.") from exc
            else:
                raw = [text]

        if isinstance(raw, dict):
            for key in ("arrNivelGrado", "ARR_NIVEL_GRADO", "nivelGrado"):
                if key in raw:
                    raw = raw[key]
                    break
            else:
                if raw.get("n") not in (None, "") and raw.get("g") not in (None, ""):
                    raw = [raw]

        if not isinstance(raw, list) or not raw:
            raise SieWebError("objNG debe ser un Array nativo arrNivelGrado no vacío.")

        normalized = []
        seen = set()
        for index, item in enumerate(raw):
            if isinstance(item, dict):
                level = str(item.get("n") or item.get("nivel") or "").strip().upper()
                grade = str(item.get("g") or item.get("grado") or "").strip()
            elif isinstance(item, str):
                ngs = item.strip().upper()
                match = re.fullmatch(r"([A-Z]+)(\d+)(?:[A-Z])?", ngs)
                if not match:
                    raise SieWebError(
                        f"arrNGS[{index}]={item!r} no puede convertirse a n/g."
                    )
                level, grade = match.group(1), match.group(2)
            else:
                raise SieWebError(f"objNG[{index}] tiene tipo incompatible.")

            if not level or not grade:
                raise SieWebError(f"objNG[{index}] no contiene n/g válidos.")
            key = (level, grade)
            if key not in seen:
                normalized.append({"n": level, "g": grade})
                seen.add(key)
        return normalized

    @functools.wraps(original_update)
    def update_grades_native_contract(self, *args, **kwargs):
        if "section_ng" not in kwargs:
            raise SieWebError("Falta el contexto nivel/grado; no se envió nada.")
        native = normalize(kwargs.get("section_ng"))
        safe_kwargs = dict(kwargs)
        safe_kwargs["section_ng"] = native
        result = original_update(self, *args, **safe_kwargs)
        if isinstance(result, dict):
            result = dict(result)
            result["native_arrNivelGrado"] = native
            result["grade_contract_hotfix"] = "0.8.7-arrNivelGrado-v1"
        return result

    setattr(update_grades_native_contract, "_sieroom_arr_nivel_grado_hotfix", True)
    SieWebClient.update_grades = update_grades_native_contract


_patch_fastmcp_run()
_patch_sieweb_grade_contract()
