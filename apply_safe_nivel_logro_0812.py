from pathlib import Path
import ast
import re
import subprocess
import sys

ROOT = Path(__file__).resolve().parent
SIEWEB = ROOT / "sieweb.py"
SERVER = ROOT / "server_core.py"
VERSION = ROOT / "VERSION.txt"

version = VERSION.read_text(encoding="utf-8").strip()
if version not in {"0.8.10", "0.8.12"}:
    raise SystemExit(f"Unexpected VERSION.txt={version!r}; refusing blind patch")

s = SIEWEB.read_text(encoding="utf-8")
server = SERVER.read_text(encoding="utf-8")

save_start = s.find("    def save_grades_verified(\n")
save_end = s.find("    def save_grades_multi_verified(\n", save_start)
if save_start < 0 or save_end < 0:
    raise SystemExit("Could not locate save_grades_verified block")

new_save = r'''    def save_grades_verified(
        self,
        *,
        year: str,
        course_code: str,
        class_period_id: int,
        root_content_id: int,
        period: int,
        section_ng: list[dict[str, str]],
        header_id: int,
        grades_by_student_code: dict[str, str],
        class_name: str | None = None,
        extra_params: dict[str, Any] | None = None,
        notify: bool = True,
        verification_attempts: int = 3,
        protect_achievement_level: bool = True,
        performance_level: int = 3,
        allow_achievement_level: bool = False,
    ) -> dict[str, Any]:
        """Guarda notas con preflight y verificación posterior obligatoria.

        Por defecto conserva el flujo histórico de desempeños nivelEva=3. Nivel de
        logro solo se habilita cuando ``allow_achievement_level`` es True y el
        llamador, además, desactiva explícitamente la protección histórica. Esa
        vía acepta exclusivamente una cabecera Competencia nivelEva=1 y A/B/C.
        """
        if type(allow_achievement_level) is not bool:
            raise SieWebError("allow_achievement_level debe ser booleano explícito.")
        achievement_mode = allow_achievement_level is True
        if achievement_mode:
            if protect_achievement_level is not False or int(performance_level) != 1:
                raise SieWebError(
                    "PROTECCIÓN NIVEL DE LOGRO HF12: el modo explícito requiere "
                    "protect_achievement_level=False y performance_level=1. No se envió nada."
                )
        else:
            if protect_achievement_level is not True or int(performance_level) != 3:
                raise SieWebError(
                    "PROTECCIÓN DE NOTAS: sin allow_achievement_level=true, "
                    "save_grades_verified solo admite desempeños nivelEva=3. No se envió nada."
                )

        requested = {
            str(code).strip(): str(grade).strip().upper()
            for code, grade in (grades_by_student_code or {}).items()
            if str(code).strip()
        }
        if not requested:
            raise SieWebError("No hay calificaciones para guardar.")
        if achievement_mode:
            invalid = {code: grade for code, grade in requested.items() if grade not in {"A", "B", "C"}}
            if invalid:
                raise SieWebError(
                    "PROTECCIÓN NIVEL DE LOGRO HF12: solo se permiten A, B o C. No se envió nada: "
                    + json.dumps(invalid, ensure_ascii=False)
                )

        before = self.get_gradebook_summary(
            class_period_id=class_period_id,
            root_content_id=root_content_id,
            extra_params=extra_params,
        )
        expected_level = 1 if achievement_mode else 3
        target = self.assert_performance_target(
            before, header_id=header_id, performance_level=expected_level
        )

        if achievement_mode:
            program = str(target.get("programa") or "").strip().casefold()
            parent_id = target.get("idpadre")
            class_content_id = target.get("idClaseContenido")
            is_grouper = target.get("esAgrupador")
            if program != "competencia":
                raise SieWebError(
                    f"PROTECCIÓN NIVEL DE LOGRO HF12: la cabecera {header_id} no es Competencia "
                    f"(programa={target.get('programa')!r}). No se envió nada."
                )
            if str(parent_id) != str(root_content_id):
                raise SieWebError(
                    f"PROTECCIÓN NIVEL DE LOGRO HF12: la cabecera {header_id} no pertenece al "
                    f"contenido raíz {root_content_id}. No se envió nada."
                )
            if class_content_id in (None, "", 0, "0"):
                raise SieWebError(
                    f"PROTECCIÓN NIVEL DE LOGRO HF12: la Competencia {header_id} no tiene "
                    "idClaseContenido persistido. No se envió nada."
                )
            if is_grouper is True or str(is_grouper).strip().lower() in {"1", "true", "si", "sí"}:
                raise SieWebError(
                    f"PROTECCIÓN NIVEL DE LOGRO HF12: la cabecera {header_id} es agrupadora, "
                    "no una celda final de Nivel de logro. No se envió nada."
                )

        native_obj_ng = self.resolve_grade_write_scope(before, section_ng)
        records = self.build_grade_records(
            before,
            header_id=header_id,
            grades_by_student_code=requested,
        )
        if len(records) != len(requested):
            raise SieWebError(
                f"Preflight incompleto: se solicitaron {len(requested)} celdas y se prepararon "
                f"{len(records)}. No se envió nada."
            )

        if achievement_mode:
            expected_ccid = str(target.get("idClaseContenido"))
            for rec in records:
                rec_level = self._dict_get_ci(rec, "nivelEva", "NIVEL", "nivel")
                rec_header = self._dict_get_ci(rec, "idCabecera", "ID_CABECERA", "header_id")
                rec_grade = str(self._dict_get_ci(rec, "notaNue", "NOTANUE", "nota", "grade") or "").strip().upper()
                rec_note_id = self._dict_get_ci(rec, "idNota", "ID_NOTA")
                if str(rec_level) != "1":
                    raise SieWebError(
                        f"PROTECCIÓN NIVEL DE LOGRO HF12: registro con nivelEva={rec_level!r}; no se envió nada."
                    )
                if str(rec_header) != str(header_id):
                    raise SieWebError(
                        f"PROTECCIÓN NIVEL DE LOGRO HF12: registro con cabecera {rec_header!r} distinta "
                        f"de {header_id}. No se envió nada."
                    )
                if rec_grade not in {"A", "B", "C"}:
                    raise SieWebError(
                        f"PROTECCIÓN NIVEL DE LOGRO HF12: nota {rec_grade!r} inválida; no se envió nada."
                    )
                if str(rec_note_id) != expected_ccid:
                    raise SieWebError(
                        f"PROTECCIÓN NIVEL DE LOGRO HF12: idNota {rec_note_id!r} no coincide con "
                        f"idClaseContenido {expected_ccid}. No se envió nada."
                    )

        def snapshot_non_target(summary: dict[str, Any]) -> dict[str, dict[str, Any]]:
            by_code = {
                str(student.get("alucod") or "").strip(): student
                for student in (summary.get("students") or [])
                if str(student.get("alucod") or "").strip()
            }
            snap: dict[str, dict[str, Any]] = {}
            for code in requested:
                student = by_code.get(code)
                if student is None:
                    raise SieWebError(
                        f"PROTECCIÓN HF12: el alumno {code} desapareció de la relectura; verificación abortada."
                    )
                notes = student.get("notas") or {}
                if not isinstance(notes, dict):
                    raise SieWebError(
                        f"PROTECCIÓN HF12: notas inválidas para {code}; verificación abortada."
                    )
                for note_key, note in notes.items():
                    if not isinstance(note, dict):
                        continue
                    note_header = self._dict_get_ci(note, "idCabecera", "ID_CABECERA")
                    if note_header in (None, ""):
                        note_header = note_key
                    if str(note_header) == str(header_id):
                        continue
                    snap[f"{code}:{note_header}"] = {
                        "idNota": self._dict_get_ci(note, "idNota", "ID_NOTA"),
                        "notaIni": self._dict_get_ci(note, "notaIni", "NOTAINI"),
                        "notaReg": self._dict_get_ci(note, "notaReg", "NOTAREG"),
                        "notaPeAnt": self._dict_get_ci(note, "notaPeAnt", "NOTAPEANT"),
                        "nivelEva": self._dict_get_ci(note, "nivelEva", "NIVEL", "nivel"),
                        "llave": self._dict_get_ci(note, "llave", "LLAVE"),
                    }
            return snap

        non_target_before = snapshot_non_target(before) if achievement_mode else {}

        update_result = self.update_grades(
            year=year,
            course_code=course_code,
            class_period_id=class_period_id,
            period=period,
            section_ng=native_obj_ng,
            records=records,
            class_name=class_name,
            notify=notify,
        )

        attempts: list[dict[str, Any]] = []
        verification: dict[str, Any] = {
            "ok": False,
            "requested_count": len(requested),
            "verified_count": 0,
            "failed_count": len(requested),
            "verified": [],
            "failed": [],
        }
        non_target_verification: dict[str, Any] = {
            "checked": achievement_mode,
            "ok": not achievement_mode,
            "verified_count": 0,
            "changed": [],
        }
        max_attempts = max(1, min(int(verification_attempts or 1), 5))
        for attempt in range(1, max_attempts + 1):
            after = self.get_gradebook_summary(
                class_period_id=class_period_id,
                root_content_id=root_content_id,
                extra_params=extra_params,
            )
            verification = self.verify_grade_changes(
                after,
                header_id=header_id,
                grades_by_student_code=requested,
            )
            attempts.append({
                "attempt": attempt,
                "ok": verification["ok"],
                "verified_count": verification["verified_count"],
                "failed_count": verification["failed_count"],
            })
            if verification["ok"]:
                if achievement_mode:
                    non_target_after = snapshot_non_target(after)
                    all_keys = sorted(set(non_target_before) | set(non_target_after))
                    changed = [
                        {
                            "cell": key,
                            "before": non_target_before.get(key),
                            "after": non_target_after.get(key),
                        }
                        for key in all_keys
                        if non_target_before.get(key) != non_target_after.get(key)
                    ]
                    non_target_verification = {
                        "checked": True,
                        "ok": not changed,
                        "verified_count": len(all_keys) - len(changed),
                        "changed": changed,
                    }
                    if changed:
                        raise SieWebError(
                            "PROTECCIÓN HF12: la relectura detectó cambios fuera de la cabecera autorizada. "
                            "Se detiene el flujo: " + json.dumps(changed[:20], ensure_ascii=False)
                        )
                break
            if attempt < max_attempts:
                time.sleep(0.4 * attempt)

        if not verification["ok"]:
            raise SieWebError(
                "SieWeb respondió a la actualización, pero la relectura no confirmó todas las notas. "
                "No se declarará éxito. Verificación: "
                + json.dumps(verification, ensure_ascii=False)
            )

        return {
            "saved": True,
            "mode": "achievement_level" if achievement_mode else "performance_level_3",
            "target": target,
            "requested_count": len(requested),
            "prepared_count": len(records),
            "update": update_result,
            "verification": verification,
            "verification_attempts": attempts,
            "non_target_verification": non_target_verification,
            "objNG": native_obj_ng,
        }

'''
s = s[:save_start] + new_save + s[save_end:]

helper_start = server.find("def sieweb_save_grades_verified(\n")
helper_end = server.find("def sieweb_update_grades(\n", helper_start)
if helper_start < 0 or helper_end < 0:
    raise SystemExit("Could not locate server_core sieweb_save_grades_verified block")

new_helper = r'''def sieweb_save_grades_verified(
    year: str,
    course_code: str,
    class_period_id: int,
    root_content_id: int,
    period: int,
    section_ng_json: str,
    header_id: int,
    grades_by_student_code_json: str,
    class_name: str = "",
    extra_params_json: str = "{}",
    confirmed: bool = False,
    allow_achievement_level: bool = False,
) -> str:
    """Guarda notas SIEweb desde la matrícula real y verifica persistencia.

    Nivel de logro permanece bloqueado salvo ``allow_achievement_level=True``.
    Requiere confirmed=true para cualquier escritura.
    """
    if type(allow_achievement_level) is not bool:
        raise ValueError("allow_achievement_level debe ser booleano JSON true/false.")
    section_ng = json.loads(section_ng_json or "[]")
    grade_map = {
        str(k).strip(): str(v).strip().upper()
        for k, v in json.loads(grades_by_student_code_json or "{}").items()
        if str(k).strip()
    }
    extra = json.loads(extra_params_json or "{}")
    if not grade_map:
        raise ValueError("grades_by_student_code no puede estar vacío.")
    invalid_grades = {code: grade for code, grade in grade_map.items() if grade not in {"A", "B", "C"}}
    if invalid_grades:
        raise ValueError(
            "Este flujo cualitativo solo admite A, B o C. Valores inválidos: "
            + json.dumps(invalid_grades, ensure_ascii=False)
        )

    summary = sieweb.get_gradebook_summary(
        class_period_id=class_period_id,
        root_content_id=root_content_id,
        extra_params=extra,
    )
    expected_level = 1 if allow_achievement_level else 3
    target = sieweb.assert_performance_target(
        summary, header_id=header_id, performance_level=expected_level
    )
    records = sieweb.build_grade_records(
        summary,
        header_id=header_id,
        grades_by_student_code=grade_map,
    )
    preview = {
        "year": year,
        "course_code": course_code,
        "class_period_id": class_period_id,
        "root_content_id": root_content_id,
        "period": period,
        "header_id": header_id,
        "target": target,
        "allow_achievement_level": allow_achievement_level,
        "section_ng": section_ng,
        "class_name": class_name,
        "requested_count": len(grade_map),
        "prepared_count": len(records),
        "changes": [
            {
                "alucod": str(record.get("alucod") or ""),
                "idPersona": record.get("idPersona"),
                "idCabecera": record.get("idCabecera"),
                "idNota": record.get("idNota"),
                "nivelEva": record.get("nivelEva"),
                "notaNue": record.get("notaNue"),
                "preserved_fields": sorted(record.keys()),
            }
            for record in records
        ],
    }
    if not confirmed:
        return _ok({
            "requires_confirmation": True,
            "safe_mode": "save_grades_verified",
            "preview": preview,
        })

    return _ok(
        sieweb.save_grades_verified(
            year=year,
            course_code=course_code,
            class_period_id=class_period_id,
            root_content_id=root_content_id,
            period=period,
            section_ng=section_ng,
            header_id=header_id,
            grades_by_student_code=grade_map,
            class_name=class_name or None,
            extra_params=extra,
            notify=bool(class_name),
            protect_achievement_level=not allow_achievement_level,
            performance_level=expected_level,
            allow_achievement_level=allow_achievement_level,
        )
    )


'''
server = server[:helper_start] + new_helper + server[helper_end:]

old_dispatch = '    if action == "save_grades_verified": return sieweb_save_grades_verified(str(p["year"]), str(p["course_code"]), int(p["class_period_id"]), int(p["root_content_id"]), int(p["period"]), json.dumps(p["section_ng"], ensure_ascii=False), int(p["header_id"]), json.dumps(p.get("grades_by_student_code", {}), ensure_ascii=False), str(p.get("class_name", "")), json.dumps(p.get("extra_params", {}), ensure_ascii=False), confirmed)'
new_dispatch = '''    if action == "save_grades_verified":
        allow_achievement_level = p.get("allow_achievement_level", False)
        if type(allow_achievement_level) is not bool:
            raise ValueError("allow_achievement_level debe ser booleano JSON true/false.")
        return sieweb_save_grades_verified(
            str(p["year"]), str(p["course_code"]), int(p["class_period_id"]),
            int(p["root_content_id"]), int(p["period"]),
            json.dumps(p["section_ng"], ensure_ascii=False), int(p["header_id"]),
            json.dumps(p.get("grades_by_student_code", {}), ensure_ascii=False),
            str(p.get("class_name", "")),
            json.dumps(p.get("extra_params", {}), ensure_ascii=False),
            confirmed=confirmed,
            allow_achievement_level=allow_achievement_level,
        )'''
if old_dispatch not in server:
    if 'allow_achievement_level = p.get("allow_achievement_level", False)' not in server:
        raise SystemExit("Could not locate exact sieweb_academics save_grades_verified dispatcher")
else:
    server = server.replace(old_dispatch, new_dispatch, 1)

old_doc = "Para notas nuevas prefiere save_grades_verified. v0.8.10 permite"
new_doc = "Para notas nuevas prefiere save_grades_verified; Nivel de logro exige allow_achievement_level=true y conserva verificación estricta. v0.8.12 permite"
if old_doc in server:
    server = server.replace(old_doc, new_doc, 1)

SIEWEB.write_text(s, encoding="utf-8")
SERVER.write_text(server, encoding="utf-8")
VERSION.write_text("0.8.12\n", encoding="utf-8")

# Syntax compilation plus source-level safety assertions.
subprocess.run([sys.executable, "-m", "py_compile", str(SIEWEB), str(SERVER), str(ROOT / "server.py")], check=True)
for path in (SIEWEB, SERVER):
    ast.parse(path.read_text(encoding="utf-8"), filename=str(path))

s2 = SIEWEB.read_text(encoding="utf-8")
server2 = SERVER.read_text(encoding="utf-8")
assert "allow_achievement_level: bool = False" in s2
assert 'program != "competencia"' in s2
assert 'str(parent_id) != str(root_content_id)' in s2
assert 'rec_grade not in {"A", "B", "C"}' in s2
assert "snapshot_non_target" in s2
assert '"non_target_verification": non_target_verification' in s2
assert 'protect_achievement_level=not allow_achievement_level' in server2
assert 'allow_achievement_level = p.get("allow_achievement_level", False)' in server2
assert 'if action == "update_grades":' in server2 and '"blocked": True' in server2
print("SAFE_NIVEL_LOGRO_PATCH_OK version=0.8.12")
