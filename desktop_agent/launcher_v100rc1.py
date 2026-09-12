from __future__ import annotations

from datetime import datetime
from typing import Any
import uuid

import main as legacy
from editor_open_probe import normalize_grade_view
from grade_cell_mapper import map_grade_cells as base_map_grade_cells
from grade_cell_probe import probe_grade_cells as base_probe_grade_cells

APP_VERSION = "1.0.0-rc1"


class PreviewProbe:
    def __init__(self, base: Any, page: Any, cell_map: Any) -> None:
        self._base = base
        self._page = page
        self._cell_map = cell_map
        self.column_count = base.column_count
        self.probed_cell_count = base.probed_cell_count
        self.columns = base.columns
        self.cell_signatures = base.cell_signatures

    def as_dict(self) -> dict[str, Any]:
        return self._base.as_dict()


def map_grade_cells_normalized(page):
    changed = normalize_grade_view(page)
    if changed:
        page.wait_for_timeout(180)
    mapped = base_map_grade_cells(page)
    setattr(mapped, "normalized_scroll_surfaces", changed)
    return mapped


def probe_grade_cells_preview(page, grade_cell_map):
    base = base_probe_grade_cells(page, grade_cell_map)
    return PreviewProbe(base, page, grade_cell_map)


def _selected_context(page) -> dict[str, Any]:
    try:
        return page.evaluate(
            r"""
            () => {
              const clean = (v, n=300) => String(v ?? '').replace(/\s+/g,' ').trim().slice(0,n);
              const visible = (el) => {
                if (!el || !(el instanceof Element)) return false;
                const s = getComputedStyle(el); const r = el.getBoundingClientRect();
                return s.display !== 'none' && s.visibility !== 'hidden' && r.width > 0 && r.height > 0;
              };
              const fields = Array.from(document.querySelectorAll('.q-field'))
                .filter(visible)
                .map((el) => clean(el.innerText || el.textContent, 220))
                .filter(Boolean)
                .slice(0, 12);
              const body = clean(document.body.innerText, 4000);
              const year = (body.match(/\b20\d{2}\b/g) || []).slice(-1)[0] || '';
              return {title: document.title, url: location.href, fields, year};
            }
            """
        )
    except Exception:
        return {"title": "", "url": page.url, "fields": [], "year": ""}


def _find_student(cell_map, order: int):
    for student in cell_map.students:
        try:
            if int(str(student.get("order") or 0)) == order:
                return student
        except Exception:
            continue
    return None


def _target_cell(student: dict[str, Any], column_zero: int):
    for cell in student.get("grade_cells") or []:
        if int(cell.get("column_index") or 0) == column_zero:
            return cell
    return None


def _short_label(value: Any) -> str:
    text = " ".join(str(value or "").split())
    return text[:170] if text else "(sin etiqueta)"


def _create_preflight_plan(probe: PreviewProbe) -> None:
    page = probe._page
    cell_map = probe._cell_map

    print("\n============================================================")
    print(" SIEROOM 1.0 RC1 — PREVISUALIZAR ESCRITURA VERIFICADA")
    print("============================================================")
    print("Esta RC1 NO escribe notas. Prepara y valida el plan que luego")
    print("se conectará al writer verificado de SIEROOM.")

    if not cell_map.students or cell_map.student_count <= 0:
        print("No se pudo aislar la matrícula. Escritura bloqueada.")
        return
    if cell_map.mapped_student_count != cell_map.student_count:
        print("No todas las filas están asociadas a celdas. Escritura bloqueada.")
        return
    if probe.column_count <= 0:
        print("No se detectaron columnas de nota. Escritura bloqueada.")
        return

    print(f"\nMatrícula detectada: {cell_map.student_count} estudiantes")
    print(f"Columnas de nota detectadas: {probe.column_count}")
    print("\nCompetencias/columnas:")
    for col in probe.columns:
        idx = int(col.get("index") or 0) + 1
        label = col.get("semantic_header") or col.get("header") or ""
        print(f"  {idx}. {_short_label(label)}")

    choice = legacy.prompt("\nP = preparar una escritura (NO ejecutarla) | ENTER = terminar: ").lower()
    if choice not in {"p", "plan", "previsualizar"}:
        return

    max_order = max([int(str(s.get("order") or 0)) for s in cell_map.students] or [1])
    raw_order = legacy.prompt(f"Número de orden del estudiante [1-{max_order}] (ENTER=1): ") or "1"
    raw_col = legacy.prompt(f"Columna [1-{probe.column_count}] (ENTER=1): ") or "1"
    proposed = legacy.prompt("Nota propuesta [A/B/C] (ENTER=A): ").strip().upper() or "A"

    try:
        order = int(raw_order)
        column = int(raw_col)
    except ValueError:
        print("Entrada inválida. Plan cancelado.")
        return

    if proposed not in {"A", "B", "C"}:
        print("Solo se admite A, B o C. Plan cancelado.")
        return
    if order < 1 or order > max_order or column < 1 or column > probe.column_count:
        print("Alumno/columna fuera de rango. Plan cancelado.")
        return

    student = _find_student(cell_map, order)
    if not student:
        print("No se encontró exactamente al estudiante solicitado. Plan cancelado.")
        return
    cell = _target_cell(student, column - 1)
    if not cell:
        print("No se encontró exactamente la celda solicitada. Plan cancelado.")
        return

    col = probe.columns[column - 1]
    label = col.get("semantic_header") or col.get("header") or ""
    context = _selected_context(page)
    current_text = str(cell.get("text") or "").strip().upper()

    plan_id = f"SIEWEB-{datetime.now().strftime('%Y%m%d-%H%M%S')}-{uuid.uuid4().hex[:8]}"
    safeguards = {
        "site_is_sieweb": "sieweb.com.pe" in str(context.get("url") or "").lower(),
        "gradebook_url": "registroNotas".lower() in str(context.get("url") or "").lower(),
        "roster_complete": cell_map.student_count == cell_map.mapped_student_count,
        "target_student_unique": True,
        "target_cell_found": True,
        "grade_allowed": proposed in {"A", "B", "C"},
        "write_enabled": False,
    }
    safe = all(v for k, v in safeguards.items() if k != "write_enabled")

    payload = {
        "plan_id": plan_id,
        "created_at": datetime.now().isoformat(timespec="seconds"),
        "mode": "PREVIEW_ONLY_RC1",
        "writer_contract": "sieweb.save_grades_verified",
        "write_enabled": False,
        "context": context,
        "roster_count": cell_map.student_count,
        "target": {
            "student_order": order,
            "student_code": str(student.get("code") or ""),
            "student_name": str(student.get("name") or ""),
            "column": column,
            "column_label": str(label or ""),
            "current_visible_value": current_text,
            "proposed_value": proposed,
        },
        "safeguards": safeguards,
        "preflight_ok": safe,
        "next_required_step": "explicitly enable one-cell verified write in a later build",
    }

    evidence_dir = legacy.app_data_root() / "evidence"
    path = legacy.save_json(evidence_dir, f"{plan_id}_verified_write_preflight.json", payload)

    print("\n--- PLAN DE ESCRITURA VERIFICADA ---")
    print(f"Plan: {plan_id}")
    print(f"Alumno: orden {order} | {student.get('code')} | {student.get('name')}")
    print(f"Competencia: columna {column} | {_short_label(label)}")
    print(f"Valor visible actual: {current_text or '(vacío)'}")
    print(f"Nota propuesta: {proposed}")
    print(f"Preflight: {'OK' if safe else 'BLOQUEADO'}")
    print(f"Evidencia: {path}")
    print("\nESCRITURA BLOQUEADA EN RC1: no se modificó SIEweb.")
    print("La siguiente build reutilizará este mismo plan para una sola")
    print("escritura con verificación posterior obligatoria.")


def print_grade_cell_probe_rc1(probe: PreviewProbe) -> None:
    print("\n--- PRECHECK DE LIBRETA ---")
    print(f"Estudiantes: {probe._cell_map.student_count}")
    print(f"Estudiantes con celdas asociadas: {probe._cell_map.mapped_student_count}")
    print(f"Columnas: {probe.column_count}")
    for col in probe.columns:
        idx = int(col.get("index") or 0) + 1
        label = col.get("semantic_header") or col.get("header") or ""
        print(f"  {idx}. {_short_label(label)}")
    _create_preflight_plan(probe)


legacy.APP_VERSION = APP_VERSION
legacy.map_grade_cells = map_grade_cells_normalized
legacy.probe_grade_cells = probe_grade_cells_preview
legacy.print_grade_cell_probe = print_grade_cell_probe_rc1

if __name__ == "__main__":
    legacy.main()
