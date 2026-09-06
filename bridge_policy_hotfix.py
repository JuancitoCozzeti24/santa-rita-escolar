from __future__ import annotations

import functools
import json
import sys
from typing import Any


def install() -> None:
    """Endurece el contrato del Bridge sin reescribir la cola histórica.

    Reglas:
    - Toda nota cuantitativa enviada al Bridge exige comentario privado.
    - Toda nota cuantitativa fuerza devolución de la entrega.
    - Una lectura-guardia válida ya no bloquea una retroalimentación nueva solo
      porque existan comentarios privados anteriores. La deduplicación exacta la
      realiza el content script antes de pulsar Enviar/Publicar.
    - Los fallos del navegador se registran con su mensaje exacto para no volver
      a diagnosticar a ciegas cuando Classroom cambie su DOM.
    """
    try:
        from bridge import ClassroomBridgeQueue
    except Exception:
        return

    if getattr(ClassroomBridgeQueue, "_sieroom_triple_contract_r62", False):
        return

    original_enqueue = ClassroomBridgeQueue.enqueue
    original_mark_completed = ClassroomBridgeQueue.mark_completed
    original_mark_failed = ClassroomBridgeQueue.mark_failed

    def enqueue_hardened(self: Any, *args: Any, **kwargs: Any):
        operation = str(kwargs.get("operation") or "post_private_comment").strip().lower()
        grade = kwargs.get("grade")
        comment = str(kwargs.get("comment") or "").strip()

        if operation == "post_private_comment" and grade is not None:
            if not comment:
                raise ValueError(
                    "Contrato SieRoom: toda nota cuantitativa requiere comentario privado; "
                    "el trabajo no fue encolado."
                )
            kwargs["return_after_comment"] = True

        return original_enqueue(self, *args, **kwargs)

    def mark_completed_hardened(
        self: Any,
        job_id: str,
        classroom_result: dict[str, Any] | None = None,
        bridge_result: dict[str, Any] | None = None,
    ):
        before = self.get(job_id)
        guard_for_job_id = getattr(before, "guard_for_job_id", None) if before else None

        result = original_mark_completed(
            self,
            job_id,
            classroom_result=classroom_result,
            bridge_result=bridge_result,
        )

        # El servidor ya validó que la lectura corresponde al alumno/entrega.
        # Si había comentarios previos, permitimos continuar: puede tratarse de
        # una reentrega corregida. El content script evita publicar dos veces el
        # MISMO comentario mediante comparación normalizada/fingerprints.
        if guard_for_job_id:
            with self._lock:
                target = self._jobs.get(guard_for_job_id)
                if target and target.status == "blocked_existing_comment":
                    target.status = "queued"
                    target.error = None
                    target.guard_result = bridge_result or {}
                    target.updated_at = result.updated_at

        return result

    def mark_failed_hardened(
        self: Any,
        job_id: str,
        error: str,
        bridge_result: dict[str, Any] | None = None,
    ):
        before = self.get(job_id)
        print(
            "SIEROOM_BRIDGE_EXACT_FAILURE: "
            f"job={job_id} operation={getattr(before, 'operation', None)} "
            f"error={error!r} result={bridge_result!r}",
            flush=True,
        )
        return original_mark_failed(
            self,
            job_id,
            error,
            bridge_result=bridge_result,
        )

    ClassroomBridgeQueue.enqueue = enqueue_hardened
    ClassroomBridgeQueue.mark_completed = mark_completed_hardened
    ClassroomBridgeQueue.mark_failed = mark_failed_hardened
    setattr(ClassroomBridgeQueue, "_sieroom_triple_contract_r62", True)


def install_achievement_levels_tool() -> None:
    """Añade una escritura verificada y EXCLUSIVA para Nivel de Logro (nivelEva=1)."""
    try:
        from mcp.server.fastmcp import FastMCP
    except Exception:
        return

    original_run = FastMCP.run
    if getattr(original_run, "_sieroom_achievement_levels_bootstrap", False):
        return

    @functools.wraps(original_run)
    def run_with_achievement_levels(self: Any, *args: Any, **kwargs: Any):
        main = sys.modules.get("__main__")
        namespace = vars(main) if main is not None else {}
        if namespace.get("mcp") is self and not getattr(self, "_sieroom_achievement_levels_installed", False):
            sieweb = namespace.get("sieweb")
            if sieweb is not None:

                @self.tool()
                def sieweb_save_achievement_levels_verified(
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
                    require_full_roster: bool = True,
                    confirmed: bool = False,
                ) -> dict[str, Any]:
                    """Guarda SOLO Nivel de Logro de una competencia (nivelEva=1), con matrícula exacta y verificación posterior."""
                    section_ng = json.loads(section_ng_json or "[]")
                    grade_map = {
                        str(code).strip(): str(grade).strip().upper()
                        for code, grade in json.loads(grades_by_student_code_json or "{}").items()
                        if str(code).strip()
                    }
                    extra = json.loads(extra_params_json or "{}")
                    if not grade_map:
                        raise ValueError("grades_by_student_code no puede estar vacío.")
                    invalid = {code: grade for code, grade in grade_map.items() if grade not in {"A", "B", "C"}}
                    if invalid:
                        raise ValueError(
                            "Nivel de Logro solo admite A, B o C. Valores inválidos: "
                            + json.dumps(invalid, ensure_ascii=False)
                        )

                    summary = sieweb.get_gradebook_summary(
                        class_period_id=int(class_period_id),
                        root_content_id=int(root_content_id),
                        extra_params=extra,
                    )
                    class_info = summary.get("class") or {}
                    if str(class_info.get("idClasePeriodo") or "") != str(class_period_id):
                        raise ValueError("Protección Nivel de Logro: idClasePeriodo no coincide con el registro releído.")
                    if str(class_info.get("idContenidoPrin") or "") != str(root_content_id):
                        raise ValueError("Protección Nivel de Logro: idContenidoPrin no coincide con el registro releído.")
                    observed_course = str(class_info.get("cursocod") or "").strip()
                    if observed_course and observed_course != str(course_code).strip():
                        raise ValueError(
                            f"Protección Nivel de Logro: CURSOCOD {observed_course!r} != {str(course_code).strip()!r}."
                        )

                    targets = [
                        item for item in (summary.get("criteria") or [])
                        if str(item.get("id") or "") == str(header_id)
                    ]
                    if len(targets) != 1:
                        raise ValueError(
                            f"Protección Nivel de Logro: la cabecera {header_id} no es única en el registro."
                        )
                    target = targets[0]
                    try:
                        target_level = int(target.get("nivelEva"))
                    except (TypeError, ValueError):
                        target_level = -1
                    if target_level != 1:
                        raise ValueError(
                            f"Protección Nivel de Logro: cabecera {header_id} tiene nivelEva={target.get('nivelEva')!r}; se exige 1."
                        )
                    program = str(target.get("programa") or "").strip().lower()
                    if program and "competencia" not in program:
                        raise ValueError(
                            f"Protección Nivel de Logro: cabecera {header_id} no está identificada como Competencia ({target.get('programa')!r})."
                        )

                    roster = [
                        str(student.get("alucod") or "").strip()
                        for student in (summary.get("students") or [])
                        if str(student.get("alucod") or "").strip()
                    ]
                    roster_set = set(roster)
                    requested_set = set(grade_map)
                    if require_full_roster and requested_set != roster_set:
                        raise ValueError(
                            "Protección Nivel de Logro: el lote no coincide con la matrícula completa. "
                            + json.dumps(
                                {
                                    "roster_count": len(roster_set),
                                    "requested_count": len(requested_set),
                                    "missing": sorted(roster_set - requested_set),
                                    "extra": sorted(requested_set - roster_set),
                                },
                                ensure_ascii=False,
                            )
                        )

                    # Obliga a que el alcance de sección pueda resolverse antes de preparar cualquier PUT.
                    sieweb.resolve_grade_write_scope(summary, section_ng)
                    records = sieweb.build_grade_records(
                        summary,
                        header_id=int(header_id),
                        grades_by_student_code=grade_map,
                    )
                    if len(records) != len(grade_map):
                        raise ValueError("Protección Nivel de Logro: preflight incompleto; no se envió nada.")
                    wrong_level = [
                        {
                            "alucod": record.get("alucod"),
                            "nivelEva": record.get("nivelEva"),
                        }
                        for record in records
                        if record.get("nivelEva") not in (1, "1")
                    ]
                    if wrong_level:
                        raise ValueError(
                            "Protección Nivel de Logro: una o más celdas preparadas no son nivelEva=1. "
                            + json.dumps(wrong_level, ensure_ascii=False)
                        )

                    grade_counts = {
                        grade: sum(1 for value in grade_map.values() if value == grade)
                        for grade in ("A", "B", "C")
                    }
                    preview = {
                        "achievement_level_only": True,
                        "class": {
                            "idClasePeriodo": class_info.get("idClasePeriodo"),
                            "idContenidoPrin": class_info.get("idContenidoPrin"),
                            "nomSalon": class_info.get("nomSalon"),
                            "cursonom": class_info.get("cursonom"),
                            "cursocod": class_info.get("cursocod"),
                        },
                        "target": target,
                        "student_count": len(grade_map),
                        "grade_counts": grade_counts,
                        "prepared_count": len(records),
                    }
                    if not confirmed:
                        return {"requires_confirmation": True, "preview": preview}

                    result = sieweb.save_grades_verified(
                        year=str(year),
                        course_code=str(course_code),
                        class_period_id=int(class_period_id),
                        root_content_id=int(root_content_id),
                        period=int(period),
                        section_ng=section_ng,
                        header_id=int(header_id),
                        grades_by_student_code=grade_map,
                        class_name=None,
                        extra_params=extra,
                        notify=False,
                        protect_achievement_level=False,
                        performance_level=1,
                    )
                    return {
                        "saved": bool(result.get("saved")),
                        "achievement_level_only": True,
                        "target": target,
                        "student_count": len(grade_map),
                        "grade_counts": grade_counts,
                        "result": result,
                    }

                setattr(self, "_sieroom_achievement_levels_installed", True)
                print("SieRoom: escritura verificada de Nivel de Logro (nivelEva=1) habilitada.", flush=True)
        return original_run(self, *args, **kwargs)

    setattr(run_with_achievement_levels, "_sieroom_achievement_levels_bootstrap", True)
    FastMCP.run = run_with_achievement_levels


install()
install_achievement_levels_tool()
