from __future__ import annotations

from typing import Any

from playwright.sync_api import Page

from grade_cell_mapper import GradeCellMap
from grade_cell_mapper_rc2 import map_grade_cells as base_map_grade_cells


_READ_VALUES_SCRIPT = r"""
(payload) => {
  const clean = (value, max = 300) => String(value ?? '')
    .replace(/\s+/g, ' ')
    .trim()
    .slice(0, max);

  const visible = (el) => {
    if (!el || !(el instanceof Element)) return false;
    const s = getComputedStyle(el);
    const r = el.getBoundingClientRect();
    return s.display !== 'none' && s.visibility !== 'hidden' && r.width > 0 && r.height > 0;
  };

  const gradeToken = (value) => {
    const v = clean(value, 40).toUpperCase();
    return /^(AD|A|B|C)$/.test(v) ? v : '';
  };

  const findProgramCell = (x, y) => {
    let el = document.elementFromPoint(x, y);
    for (let i = 0; el && el !== document.body && i < 8; i++, el = el.parentElement) {
      const cls = String(el.className || '');
      if (cls.includes('td') && cls.includes('bgprograma_3')) return el;
    }
    return null;
  };

  const readCell = (cell) => {
    const cx = Number(cell.x || 0) + Number(cell.width || 0) / 2;
    const cy = Number(cell.y || 0) + Number(cell.height || 0) / 2;
    const el = findProgramCell(cx, cy);
    if (!el) {
      return {
        text: '', raw_text: '', sanitized_text: '', value_confident: false,
        value_state: 'unreadable', value_source: 'cell_not_found'
      };
    }

    const raw = clean(el.innerText || el.textContent, 220);

    // Si existe un editor visible, su value tiene prioridad.
    const editor = Array.from(el.querySelectorAll('input,select,textarea'))
      .find(visible);
    if (editor) {
      const value = gradeToken(editor.value);
      if (value) {
        return {
          text: value, raw_text: raw, sanitized_text: value,
          value_confident: true, value_state: 'grade', value_source: 'visible_editor'
        };
      }
      if (clean(editor.value, 40) === '') {
        return {
          text: '', raw_text: raw, sanitized_text: '',
          value_confident: true, value_state: 'blank', value_source: 'visible_editor_blank'
        };
      }
      return {
        text: clean(editor.value, 40), raw_text: raw, sanitized_text: clean(editor.value, 40),
        value_confident: false, value_state: 'unexpected', value_source: 'visible_editor_unexpected'
      };
    }

    // Clonamos la celda para quitar iconos/controles auxiliares antes de leer texto.
    const clone = el.cloneNode(true);
    const junkSelectors = [
      'svg', 'button', 'i', '[role="button"]', '[aria-hidden="true"]',
      '.q-icon', '.material-icons', '.material-icons-outlined',
      '.material-symbols-outlined', '.material-symbols-rounded', '.material-symbols-sharp'
    ];
    for (const sel of junkSelectors) {
      clone.querySelectorAll(sel).forEach(node => node.remove());
    }

    // SIEweb puede renderizar nombres de iconos como texto. Se eliminan solo tokens UI conocidos.
    const uiTokens = /COMMENT|VIEW_HISTORY|HISTORY|CHAT|EDIT|MORE_VERT|INFO|VISIBILITY/gi;
    let sanitized = clean(clone.innerText || clone.textContent, 120)
      .replace(uiTokens, '')
      .replace(/\s+/g, ' ')
      .trim();

    const value = gradeToken(sanitized);
    if (value) {
      return {
        text: value, raw_text: raw, sanitized_text: sanitized,
        value_confident: true, value_state: 'grade', value_source: 'sanitized_cell_text'
      };
    }
    if (sanitized === '') {
      return {
        text: '', raw_text: raw, sanitized_text: '',
        value_confident: true, value_state: 'blank', value_source: 'sanitized_cell_blank'
      };
    }

    return {
      text: sanitized, raw_text: raw, sanitized_text: sanitized,
      value_confident: false, value_state: 'unexpected', value_source: 'sanitized_cell_unexpected'
    };
  };

  return (payload.students || []).map(student => ({
    code: student.code,
    values: (student.grade_cells || []).map(cell => ({
      column_index: cell.column_index,
      ...readCell(cell)
    }))
  }));
}
"""


def map_grade_cells_rc3(page: Page) -> GradeCellMap:
    mapped = base_map_grade_cells(page)
    if not mapped.students:
        return mapped

    try:
        readings = page.evaluate(_READ_VALUES_SCRIPT, mapped.as_dict())
    except Exception:
        readings = []

    by_code: dict[str, dict[int, dict[str, Any]]] = {}
    for item in readings or []:
        code = str(item.get("code") or "")
        by_code[code] = {
            int(v.get("column_index") or 0): v
            for v in (item.get("values") or [])
        }

    students: list[dict[str, Any]] = []
    for student in mapped.students:
        code = str(student.get("code") or "")
        read_map = by_code.get(code, {})
        cells: list[dict[str, Any]] = []
        for cell in student.get("grade_cells") or []:
            col = int(cell.get("column_index") or 0)
            reading = read_map.get(col) or {
                "text": "",
                "raw_text": "",
                "sanitized_text": "",
                "value_confident": False,
                "value_state": "unreadable",
                "value_source": "no_reading",
            }
            cells.append({**cell, **reading})
        students.append({**student, "grade_cells": cells})

    return GradeCellMap(
        student_count=mapped.student_count,
        mapped_student_count=mapped.mapped_student_count,
        column_count=mapped.column_count,
        columns=mapped.columns,
        students=students,
    )


map_grade_cells = map_grade_cells_rc3
