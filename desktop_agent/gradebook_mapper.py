from __future__ import annotations

from dataclasses import asdict, dataclass
from typing import Any

from playwright.sync_api import Frame, Page


@dataclass
class GradebookMap:
    url: str
    title: str
    frame_count: int
    table_count: int
    grid_count: int
    control_count: int
    candidate_row_count: int
    student_row_count: int
    frames: list[dict[str, Any]]
    student_rows: list[dict[str, Any]]
    grade_like_values: list[str]

    def as_dict(self) -> dict[str, Any]:
        return asdict(self)


_FRAME_SCRIPT = r"""
() => {
  const visible = (el) => {
    if (!el || !(el instanceof Element)) return false;
    const style = window.getComputedStyle(el);
    const rect = el.getBoundingClientRect();
    return style.display !== 'none' && style.visibility !== 'hidden' && rect.width > 0 && rect.height > 0;
  };

  const clean = (value, max = 400) => String(value ?? '')
    .replace(/\s+/g, ' ')
    .trim()
    .slice(0, max);

  const rectOf = (el) => {
    const r = el.getBoundingClientRect();
    return {
      x: Math.round(r.x * 10) / 10,
      y: Math.round(r.y * 10) / 10,
      width: Math.round(r.width * 10) / 10,
      height: Math.round(r.height * 10) / 10,
      right: Math.round(r.right * 10) / 10,
      bottom: Math.round(r.bottom * 10) / 10,
    };
  };

  const controlSelector = [
    'input:not([type="password"]):not([type="hidden"])',
    'select',
    'textarea',
    '[contenteditable="true"]',
    '[role="combobox"]',
    '[role="spinbutton"]'
  ].join(',');

  const readControl = (el) => {
    const tag = el.tagName.toLowerCase();
    const type = clean(el.getAttribute('type') || '').toLowerCase();
    if (type === 'password' || type === 'hidden') return null;
    let value = '';
    let selectedText = '';
    if (tag === 'select') {
      value = clean(el.value, 200);
      const option = el.options && el.selectedIndex >= 0 ? el.options[el.selectedIndex] : null;
      selectedText = option ? clean(option.textContent, 200) : '';
    } else if (tag === 'input' || tag === 'textarea') {
      value = clean(el.value, 200);
    } else if (el.getAttribute('contenteditable') === 'true') {
      value = clean(el.textContent, 200);
    } else {
      value = clean(el.getAttribute('aria-valuetext') || el.textContent, 200);
    }
    return {
      tag,
      type,
      name: clean(el.getAttribute('name'), 200),
      id: clean(el.id, 200),
      class_name: clean(el.className, 300),
      aria_label: clean(el.getAttribute('aria-label'), 300),
      role: clean(el.getAttribute('role'), 100),
      placeholder: clean(el.getAttribute('placeholder'), 200),
      value,
      selected_text: selectedText,
      disabled: Boolean(el.disabled),
      readonly: Boolean(el.readOnly),
      rect: rectOf(el),
    };
  };

  const controls = Array.from(document.querySelectorAll(controlSelector))
    .filter(visible)
    .map((el, index) => ({ index, ...readControl(el) }))
    .filter(Boolean);

  const tables = Array.from(document.querySelectorAll('table')).map((table, tableIndex) => {
    const rows = Array.from(table.querySelectorAll('tr'));
    const mappedRows = rows.slice(0, 180).map((row, rowIndex) => {
      const cells = Array.from(row.querySelectorAll(':scope > th, :scope > td'));
      return {
        row_index: rowIndex,
        text: clean(row.innerText || row.textContent, 1200),
        rect: rectOf(row),
        cells: cells.slice(0, 120).map((cell, columnIndex) => ({
          column_index: columnIndex,
          tag: cell.tagName.toLowerCase(),
          text: clean(cell.innerText || cell.textContent, 500),
          class_name: clean(cell.className, 250),
          rect: rectOf(cell),
          colspan: Number(cell.getAttribute('colspan') || 1),
          rowspan: Number(cell.getAttribute('rowspan') || 1),
          controls: Array.from(cell.querySelectorAll(controlSelector))
            .filter(visible)
            .slice(0, 20)
            .map(readControl)
            .filter(Boolean),
        })),
      };
    });

    const headers = [];
    Array.from(table.querySelectorAll('th')).slice(0, 180).forEach((th) => {
      const text = clean(th.innerText || th.textContent, 500);
      if (text && !headers.includes(text)) headers.push(text);
    });

    return {
      table_index: tableIndex,
      id: clean(table.id, 200),
      class_name: clean(table.className, 300),
      total_rows: rows.length,
      sampled_rows: mappedRows.length,
      headers,
      rows: mappedRows,
    };
  });

  const roleGrids = Array.from(document.querySelectorAll('[role="grid"], [role="table"], [role="treegrid"]'))
    .filter(visible)
    .map((grid, gridIndex) => {
      const rows = Array.from(grid.querySelectorAll('[role="row"]'));
      return {
        grid_index: gridIndex,
        role: clean(grid.getAttribute('role'), 100),
        id: clean(grid.id, 200),
        class_name: clean(grid.className, 300),
        total_rows: rows.length,
        rows: rows.slice(0, 180).map((row, rowIndex) => ({
          row_index: rowIndex,
          text: clean(row.innerText || row.textContent, 1200),
          rect: rectOf(row),
          cells: Array.from(row.querySelectorAll('[role="columnheader"], [role="rowheader"], [role="gridcell"], [role="cell"]'))
            .slice(0, 120)
            .map((cell, columnIndex) => ({
              column_index: columnIndex,
              role: clean(cell.getAttribute('role'), 100),
              text: clean(cell.innerText || cell.textContent, 500),
              class_name: clean(cell.className, 250),
              rect: rectOf(cell),
              controls: Array.from(cell.querySelectorAll(controlSelector))
                .filter(visible)
                .slice(0, 20)
                .map(readControl)
                .filter(Boolean),
            })),
        })),
      };
    });

  const rowSelectors = [
    '[role="row"]', '.slick-row', '.ag-row', '.jqgrow', '.k-master-row',
    '.dx-data-row', '.ui-widget-content.jqgrow', '[class*="grid-row"]',
    '[class*="table-row"]', '[class*="data-row"]', '[class~="row"]'
  ].join(',');

  const seen = new Set();
  const candidateRows = [];
  for (const row of Array.from(document.querySelectorAll(rowSelectors))) {
    if (!visible(row)) continue;
    const text = clean(row.innerText || row.textContent, 1400);
    const children = Array.from(row.children).filter(visible);
    if (!text && children.length < 2) continue;
    const key = `${row.tagName}|${row.id}|${row.className}|${text}`;
    if (seen.has(key)) continue;
    seen.add(key);
    candidateRows.push({
      tag: row.tagName.toLowerCase(),
      id: clean(row.id, 200),
      class_name: clean(row.className, 300),
      role: clean(row.getAttribute('role'), 100),
      text,
      child_count: children.length,
      rect: rectOf(row),
      cells: children.slice(0, 120).map((child, index) => ({
        column_index: index,
        tag: child.tagName.toLowerCase(),
        class_name: clean(child.className, 250),
        role: clean(child.getAttribute('role'), 100),
        text: clean(child.innerText || child.textContent, 500),
        rect: rectOf(child),
        controls: Array.from(child.querySelectorAll(controlSelector))
          .filter(visible)
          .slice(0, 20)
          .map(readControl)
          .filter(Boolean),
      })),
    });
    if (candidateRows.length >= 300) break;
  }

  // Locate actual student rows using the 8-digit SIEweb student code as a stable anchor.
  const allVisible = Array.from(document.querySelectorAll('body *')).filter(visible);
  const codeElements = allVisible.filter((el) => /^\d{8}$/.test(clean(el.innerText || el.textContent, 40)));
  const studentsByCode = new Map();

  const leafTexts = (root) => Array.from(root.querySelectorAll('*'))
    .filter(visible)
    .filter((el) => Array.from(el.children).filter(visible).length === 0)
    .map((el) => ({ el, text: clean(el.innerText || el.textContent, 300), rect: rectOf(el) }))
    .filter((item) => item.text);

  const chooseRowAncestor = (codeEl) => {
    let current = codeEl;
    const options = [];
    for (let depth = 0; current && current !== document.body && depth < 9; depth++, current = current.parentElement) {
      if (!visible(current)) continue;
      const r = current.getBoundingClientRect();
      const text = clean(current.innerText || current.textContent, 1600);
      if (r.width < 250 || r.height < 12 || r.height > 85) continue;
      if (!text.includes(clean(codeEl.innerText || codeEl.textContent, 40))) continue;
      const leaves = leafTexts(current);
      const hasName = leaves.some((x) => /[A-Za-zÁÉÍÓÚÜÑáéíóúüñ]{2,}.*[, ].*[A-Za-zÁÉÍÓÚÜÑáéíóúüñ]{2,}/.test(x.text));
      if (!hasName) continue;
      options.push({ el: current, depth, leaves, rect: rectOf(current), text });
    }
    if (!options.length) return null;
    options.sort((a, b) => (a.rect.height - b.rect.height) || (a.rect.width - b.rect.width) || (a.depth - b.depth));
    return options[0];
  };

  for (const codeEl of codeElements) {
    const code = clean(codeEl.innerText || codeEl.textContent, 40);
    if (studentsByCode.has(code)) continue;
    const candidate = chooseRowAncestor(codeEl);
    if (!candidate) continue;

    const leaves = candidate.leaves
      .filter((item) => item.rect.width > 0 && item.rect.height > 0)
      .sort((a, b) => (a.rect.x - b.rect.x) || (a.rect.y - b.rect.y));

    const uniqueLeaves = [];
    const leafSeen = new Set();
    for (const item of leaves) {
      const key = `${item.text}|${item.rect.x}|${item.rect.y}|${item.rect.width}`;
      if (leafSeen.has(key)) continue;
      leafSeen.add(key);
      uniqueLeaves.push(item);
    }

    const texts = uniqueLeaves.map((x) => x.text);
    let order = '';
    for (const text of texts) {
      if (/^\d{1,2}$/.test(text)) {
        const n = Number(text);
        if (n >= 1 && n <= 60) { order = text; break; }
      }
    }

    let name = '';
    for (const text of texts) {
      if (text === code || text === order) continue;
      if (/^(Código|Nombre|No\.?.?\s*orden)$/i.test(text)) continue;
      if (/[A-Za-zÁÉÍÓÚÜÑáéíóúüñ]{2,}/.test(text) && (text.includes(',') || text.split(' ').length >= 2)) {
        name = text;
        break;
      }
    }

    const rowControls = Array.from(candidate.el.querySelectorAll(controlSelector))
      .filter(visible)
      .map(readControl)
      .filter(Boolean);

    studentsByCode.set(code, {
      code,
      order,
      name,
      row_tag: candidate.el.tagName.toLowerCase(),
      row_id: clean(candidate.el.id, 200),
      row_class: clean(candidate.el.className, 300),
      row_text: candidate.text,
      row_rect: candidate.rect,
      controls: rowControls,
      cells: uniqueLeaves.slice(0, 80).map((item, index) => ({
        index,
        text: item.text,
        rect: item.rect,
      })),
    });
  }

  const studentRows = Array.from(studentsByCode.values()).sort((a, b) => {
    const ao = Number(a.order || 9999);
    const bo = Number(b.order || 9999);
    if (ao !== bo) return ao - bo;
    return a.row_rect.y - b.row_rect.y;
  });

  const headerTexts = ['Código', 'No. orden', 'Nombre'];
  const headerCells = allVisible
    .map((el) => ({ el, text: clean(el.innerText || el.textContent, 350) }))
    .filter((item) => item.text && (headerTexts.includes(item.text) || /^Resuelve problemas de/i.test(item.text)))
    .map((item) => ({ text: item.text, rect: rectOf(item.el), tag: item.el.tagName.toLowerCase(), class_name: clean(item.el.className, 250) }))
    .slice(0, 80);

  const iframes = Array.from(document.querySelectorAll('iframe')).map((el, index) => ({
    index,
    id: clean(el.id, 200),
    name: clean(el.getAttribute('name'), 200),
    src: clean(el.getAttribute('src'), 1000),
    class_name: clean(el.className, 300),
    visible: visible(el),
  }));

  const gradePattern = /^(AD|A|B|C|[0-9]|1[0-9]|20)$/i;
  const gradeLike = [];
  const consider = (value) => {
    const v = clean(value, 30).toUpperCase();
    if (v && gradePattern.test(v) && !gradeLike.includes(v)) gradeLike.push(v);
  };
  controls.forEach((c) => { consider(c.value); consider(c.selected_text); });
  tables.forEach((table) => table.rows.forEach((row) => row.cells.forEach((cell) => {
    consider(cell.text);
    cell.controls.forEach((c) => { consider(c.value); consider(c.selected_text); });
  })));
  studentRows.forEach((row) => {
    row.controls.forEach((c) => { consider(c.value); consider(c.selected_text); });
    row.cells.forEach((cell) => consider(cell.text));
  });

  return {
    document_url: location.href,
    document_title: document.title,
    table_count: tables.length,
    grid_count: roleGrids.length,
    control_count: controls.length,
    candidate_row_count: candidateRows.length,
    student_row_count: studentRows.length,
    tables,
    grids: roleGrids,
    controls: controls.slice(0, 400),
    candidate_rows: candidateRows,
    student_rows: studentRows,
    header_cells: headerCells,
    iframes,
    grade_like_values: gradeLike,
  };
}
"""


def _map_frame(frame: Frame, index: int) -> dict[str, Any]:
    try:
        payload = frame.evaluate(_FRAME_SCRIPT)
        payload["frame_index"] = index
        payload["frame_name"] = frame.name or ""
        payload["frame_url"] = frame.url
        payload["accessible"] = True
        return payload
    except Exception as exc:
        return {
            "frame_index": index,
            "frame_name": frame.name or "",
            "frame_url": frame.url,
            "accessible": False,
            "error": str(exc)[:500],
            "table_count": 0,
            "grid_count": 0,
            "control_count": 0,
            "candidate_row_count": 0,
            "student_row_count": 0,
            "tables": [],
            "grids": [],
            "controls": [],
            "candidate_rows": [],
            "student_rows": [],
            "header_cells": [],
            "iframes": [],
            "grade_like_values": [],
        }


def map_gradebook(page: Page) -> GradebookMap:
    """Map Registro de Notas in read-only mode, including student-row discovery."""
    frames = [_map_frame(frame, index) for index, frame in enumerate(page.frames)]

    grade_like: list[str] = []
    students_by_code: dict[str, dict[str, Any]] = {}
    for frame in frames:
        for value in frame.get("grade_like_values", []):
            if value not in grade_like:
                grade_like.append(value)
        for student in frame.get("student_rows", []):
            code = str(student.get("code", ""))
            if code and code not in students_by_code:
                students_by_code[code] = {**student, "frame_index": frame.get("frame_index", 0)}

    student_rows = sorted(
        students_by_code.values(),
        key=lambda row: (int(row.get("order") or 9999), row.get("code", "")),
    )

    return GradebookMap(
        url=page.url,
        title=page.title(),
        frame_count=len(frames),
        table_count=sum(int(frame.get("table_count", 0)) for frame in frames),
        grid_count=sum(int(frame.get("grid_count", 0)) for frame in frames),
        control_count=sum(int(frame.get("control_count", 0)) for frame in frames),
        candidate_row_count=sum(int(frame.get("candidate_row_count", 0)) for frame in frames),
        student_row_count=len(student_rows),
        frames=frames,
        student_rows=student_rows,
        grade_like_values=grade_like,
    )
