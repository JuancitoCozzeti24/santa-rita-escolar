from __future__ import annotations

from urllib.parse import parse_qs, urlparse
import builtins

import main as legacy
import launcher_v100rc1 as rc1
import launcher_v100rc3 as rc3
import launcher_v100rc7 as rc7
import launcher_v100rc9 as rc9
import launcher_v100rc10 as rc10  # conserva estabilización DOM de RC10
import verified_writer_bridge as writer
from verified_writer_bridge import VerifiedWriterBridgeError


APP_VERSION = "1.0.0-rc11"
_original_print = builtins.print


def _print_rc11(*args, **kwargs):
    patched = []
    for arg in args:
        if isinstance(arg, str):
            text = arg.replace("RC10", "RC11").replace("RC9", "RC11")
            patched.append(text)
        else:
            patched.append(arg)
    _original_print(*patched, **kwargs)


rc9.print = _print_rc11
rc9.APP_VERSION = APP_VERSION


def _parse_gradebook_url(url: str) -> dict[str, int] | None:
    if "/lms/api/hyoclaseperiodo/obtregistronotas" not in str(url or "").lower():
        return None
    try:
        qs = parse_qs(urlparse(url).query)
        def first_int(name: str, default: int = 0) -> int:
            values = qs.get(name) or qs.get(name.lower()) or qs.get(name.upper()) or []
            if not values:
                # parse_qs conserva mayúsculas; búsqueda case-insensitive defensiva.
                for key, value in qs.items():
                    if str(key).lower() == name.lower():
                        values = value
                        break
            return int(str(values[0])) if values else int(default)

        class_period_id = first_int("idClasePeriodo")
        root_content_id = first_int("idContenido")
        previous_period_id = first_int("idPeriodoAnt", 0)
        if class_period_id <= 0 or root_content_id <= 0:
            return None
        return {
            "idClasePeriodo": class_period_id,
            "idContenido": root_content_id,
            "idPeriodoAnt": previous_period_id,
        }
    except Exception:
        return None


def _resource_gradebook_context(page) -> dict[str, int] | None:
    try:
        urls = page.evaluate(
            r"""
            () => performance.getEntriesByType('resource')
              .map(e => String(e.name || ''))
              .filter(u => /\/lms\/api\/HyoClasePeriodo\/obtRegistroNotas/i.test(u))
              .slice(-20)
            """
        ) or []
    except Exception:
        urls = []
    for url in reversed(urls):
        parsed = _parse_gradebook_url(str(url))
        if parsed:
            return parsed
    return None


def _capture_current_gradebook_context(page) -> dict[str, int]:
    """Obtiene los IDs REALES de la libreta visible sin usar tablas estáticas de sección.

    Primero aprovecha la petición de obtRegistroNotas que ya hizo la pestaña. Si el
    navegador no conserva Resource Timing, vuelve a seleccionar el MISMO período y
    escucha únicamente esa petición GET. No escribe notas ni cambia de sección.
    """
    existing = _resource_gradebook_context(page)
    if existing:
        return existing

    captured: list[str] = []

    def on_request(req) -> None:
        try:
            url = str(req.url or "")
            method = str(req.method or "GET").upper()
        except Exception:
            return
        if method == "GET" and "/lms/api/hyoclaseperiodo/obtregistronotas" in url.lower():
            captured.append(url)

    page.on("request", on_request)
    try:
        snapshot = rc7._selector_snapshot(page)
        period = rc7._find_snapshot(snapshot, "periodo") or rc7._find_snapshot(snapshot, "período")
        if period:
            rc7._select_same_value(page, period)
            page.wait_for_timeout(1400)
        else:
            page.wait_for_timeout(350)
    finally:
        try:
            page.remove_listener("request", on_request)
        except Exception:
            pass

    for url in reversed(captured):
        parsed = _parse_gradebook_url(url)
        if parsed:
            return parsed

    retry = _resource_gradebook_context(page)
    if retry:
        return retry

    raise VerifiedWriterBridgeError(
        "RC11 no pudo localizar la petición real obtRegistroNotas de la libreta visible. "
        "No se escribió nada. Mantén abierto Registro de Notas con Salón, Curso y Período seleccionados."
    )


def _prepare_one_cell_write_rc11(
    page,
    *,
    dom_student_codes: list[str],
    student_code: str,
    student_name: str,
    column_number: int,
    column_label: str,
    dom_current: str,
    proposed: str,
):
    proposed = str(proposed or "").strip().upper()
    dom_current = str(dom_current or "").strip().upper()
    if proposed not in {"A", "B", "C"}:
        raise VerifiedWriterBridgeError("RC11 solo admite A, B o C.")
    if dom_current not in {"", "A", "B", "C"}:
        raise VerifiedWriterBridgeError("El valor DOM actual no es una calificación confiable.")

    browser_context = writer.infer_browser_context(page)
    client, auth_status = writer._hydrate_client_from_browser(page)

    try:
        live = _capture_current_gradebook_context(page)
        extra = {"idPeriodoAnt": int(live.get("idPeriodoAnt") or 0)}
        before = client.get_gradebook_summary(
            class_period_id=int(live["idClasePeriodo"]),
            root_content_id=int(live["idContenido"]),
            extra_params=extra,
        )
    except VerifiedWriterBridgeError:
        raise
    except Exception as exc:
        raise VerifiedWriterBridgeError(
            "No se pudo autenticar/releer la libreta actual usando sus IDs capturados del navegador. "
            f"No se escribió nada. Detalle: {exc}"
        ) from exc

    class_info = before.get("class") or {}
    # Los IDs de la respuesta, cuando existen, deben concordar con la petición real.
    summary_cp = class_info.get("idClasePeriodo")
    if summary_cp not in (None, "") and str(summary_cp) != str(live["idClasePeriodo"]):
        raise VerifiedWriterBridgeError(
            "La API devolvió un idClasePeriodo distinto al de la libreta visible. No se escribió nada."
        )
    summary_root = class_info.get("idContenidoPrin")
    if summary_root not in (None, "") and str(summary_root) != str(live["idContenido"]):
        raise VerifiedWriterBridgeError(
            "La API devolvió un contenido raíz distinto al de la libreta visible. No se escribió nada."
        )

    api_period = int(class_info.get("periodo") or browser_context["period"] or 0)
    if api_period != int(browser_context["period"]):
        raise VerifiedWriterBridgeError(
            f"El período DOM/API no coincide ({browser_context['period']} vs {api_period}). No se escribió nada."
        )
    api_course = str(class_info.get("cursocod") or "").strip()
    if api_course and api_course != str(browser_context["course_code"]).strip():
        raise VerifiedWriterBridgeError(
            f"El curso DOM/API no coincide ({browser_context['course_code']} vs {api_course}). No se escribió nada."
        )

    dom_codes = {str(x).strip() for x in dom_student_codes if str(x).strip()}
    api_codes = {
        str(s.get("alucod") or "").strip()
        for s in (before.get("students") or [])
        if str(s.get("alucod") or "").strip()
    }
    if not dom_codes or dom_codes != api_codes:
        raise VerifiedWriterBridgeError(
            f"La matrícula DOM/API no coincide (DOM={len(dom_codes)}, API={len(api_codes)}). No se escribió nada."
        )
    if student_code not in api_codes:
        raise VerifiedWriterBridgeError("El alumno objetivo no existe en la matrícula API revalidada.")

    criterion = writer._match_criterion(client, before, column_label)
    try:
        header_id = int(criterion.get("id"))
        level = int(criterion.get("nivelEva"))
    except Exception as exc:
        raise VerifiedWriterBridgeError("La cabecera API objetivo no expone id/nivelEva válidos.") from exc
    if level not in {1, 3}:
        raise VerifiedWriterBridgeError(f"RC11 bloquea nivelEva={level}; solo admite 1 o 3.")

    api_current = writer._student_grade(before, student_code, header_id)
    if api_current not in {"", "A", "B", "C"}:
        raise VerifiedWriterBridgeError(
            f"La API devolvió un valor actual no admitido ({api_current!r}). Escritura bloqueada."
        )
    if api_current != dom_current:
        raise VerifiedWriterBridgeError(
            f"DOM y API discrepan sobre la celda objetivo (DOM={dom_current or '(vacío)'}, "
            f"API={api_current or '(vacío)'}). No se escribió nada."
        )
    if api_current and api_current != proposed:
        raise VerifiedWriterBridgeError(
            f"RC11 no sobrescribe una nota existente ({api_current} -> {proposed}). "
            "Solo permite celda vacía o valor ya idéntico."
        )

    api_context = {
        "section": browser_context.get("section"),
        "idAmbito": class_info.get("idAmbito"),
        "idClase": class_info.get("idClase"),
        "idClasePeriodo": int(live["idClasePeriodo"]),
        "idContenido": int(live["idContenido"]),
        "periodo": api_period,
        "idPeriodoAnt": int(live.get("idPeriodoAnt") or 0),
        "course": {
            "NOMCLASE": class_info.get("cursonom") or "",
            "NOMBRE": class_info.get("cursonom") or "",
        },
        "context_source": "live_obtRegistroNotas_request",
    }

    return writer.PreparedWrite(
        client=client,
        browser_context=browser_context,
        api_context=api_context,
        before=before,
        before_snapshot=writer._grade_snapshot(before),
        auth_status=auth_status,
        student_code=student_code,
        student_name=student_name,
        column_number=int(column_number),
        column_label=column_label,
        header_id=header_id,
        criterion_level=level,
        criterion_text=str(criterion.get("_matched_text") or writer._criterion_text(criterion)),
        criterion_match_score=float(criterion.get("_match_score") or 0.0),
        dom_current=dom_current,
        api_current=api_current,
        proposed=proposed,
    )


# RC9 hace el lote y RC10 estabiliza DOM. RC11 sustituye únicamente la resolución
# estática de contexto por los IDs reales de la petición que abrió la libreta.
rc9.prepare_one_cell_write = _prepare_one_cell_write_rc11

legacy.APP_VERSION = APP_VERSION
legacy.map_grade_cells = rc3.map_grade_cells_normalized_rc3
legacy.probe_grade_cells = rc1.probe_grade_cells_preview
legacy.print_grade_cell_probe = rc9.print_grade_cell_probe_rc9


if __name__ == "__main__":
    legacy.main()
