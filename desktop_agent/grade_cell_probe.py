from __future__ import annotations

from dataclasses import asdict, dataclass
from typing import Any

from playwright.sync_api import Page


@dataclass
class GradeCellProbe:
    column_count: int
    probed_cell_count: int
    columns: list[dict[str, Any]]
    cell_signatures: list[dict[str, Any]]

    def as_dict(self) -> dict[str, Any]:
        return asdict(self)


_SCRIPT = r"""
(payload) => {
  const clean = (value, max = 800) => String(value ?? '')
    .replace(/\s+/g, ' ')
    .trim()
    .slice(0, max);

  const visible = (el) => {
    if (!el || !(el instanceof Element)) return false;
    const s = getComputedStyle(el);
    const r = el.getBoundingClientRect();
    return s.display !== 'none' && s.visibility !== 'hidden' && r.width > 0 && r.height > 0;
  };

  const rectOf = (el) => {
    const r = el.getBoundingClientRect();
    return {
      x: Math.round(r.x * 10) / 10,
      y: Math.round(r.y * 10) / 10,
      width: Math.round(r.width * 10) / 10,
      height: Math.round(r.height * 10) / 10,
      right: Math.round(r.right * 10) / 10,
      bottom: Math.round(r.bottom * 10) / 10,
      cx: Math.round((r.x + r.width / 2) * 10) / 10,
      cy: Math.round((r.y + r.height / 2) * 10) / 10,
    };
  };

  const attrsOf = (el) => {
    const attrs = {};
    for (const attr of Array.from(el.attributes || [])) {
      const name = attr.name;
      if (name.toLowerCase().includes('password')) continue;
      attrs[name] = clean(attr.value, 500);
    }
    return attrs;
  };

  const signatureOf = (el) => {
    if (!el) return null;
    const style = getComputedStyle(el);
    const parent = el.parentElement;
    return {
      tag: el.tagName.toLowerCase(),
      id: clean(el.id, 200),
      class_name: clean(el.className, 400),
      text: clean(el.innerText || el.textContent, 300),
      rect: rectOf(el),
      attributes: attrsOf(el),
      onclick_attribute: clean(el.getAttribute('onclick'), 500),
      has_onclick_property: typeof el.onclick === 'function',
      contenteditable: clean(el.getAttribute('contenteditable'), 40),
      role: clean(el.getAttribute('role'), 100),
      tabindex: clean(el.getAttribute('tabindex'), 40),
      cursor: clean(style.cursor, 80),
      background: clean(style.backgroundColor, 100),
      parent_tag: parent ? parent.tagName.toLowerCase() : '',
      parent_class: parent ? clean(parent.className, 400) : '',
      parent_attributes: parent ? attrsOf(parent) : {},
      outer_html: clean(el.outerHTML, 1200),
    };
  };

  const students = payload.students || [];
  const columns = payload.columns || [];
  const firstY = students.length ? Math.min(...students.map(s => Number(s.row_rect?.y || 99999))) : 99999;

  // Find compact header labels aligned with each grade column. Prefer leaf/small elements,
  // close to the student body, instead of a broad container containing every competency.
  const headerCandidates = Array.from(document.querySelectorAll('body *'))
    .filter(visible)
    .map(el => ({
      el,
      text: clean(el.innerText || el.textContent, 600),
      rect: rectOf(el),
      children: Array.from(el.children).filter(visible).length,
    }))
    .filter(h => h.text && h.rect.bottom <= firstY + 4 && h.rect.y >= firstY - 220)
    .filter(h => !/^\d{8}$/.test(h.text));

  const mappedColumns = columns.map(col => {
    const center = Number(col.x) + Number(col.average_width || 0) / 2;
    const candidates = headerCandidates
      .filter(h => h.rect.x - 4 <= center && h.rect.right + 4 >= center)
      .map(h => {
        const distance = Math.max(0, firstY - h.rect.bottom);
        const widthPenalty = Math.abs(h.rect.width - Math.max(45, Number(col.average_width || 55)));
        const areaPenalty = Math.min(500, h.rect.width * h.rect.height / 100);
        const childPenalty = h.children * 30;
        const score = distance * 4 + widthPenalty * 2 + areaPenalty + childPenalty;
        return {...h, score};
      })
      .sort((a,b) => a.score - b.score);

    const best = candidates[0] || null;
    return {
      ...col,
      semantic_header: best ? best.text : (col.header || ''),
      semantic_header_rect: best ? best.rect : null,
      semantic_header_tag: best ? best.el.tagName.toLowerCase() : '',
      semantic_header_class: best ? clean(best.el.className, 300) : '',
    };
  });

  const signatures = [];
  const seen = new Set();
  for (const student of students) {
    for (const cell of (student.grade_cells || [])) {
      const cx = Number(cell.x) + Number(cell.width || 0) / 2;
      const cy = Number(cell.y) + Number(cell.height || 0) / 2;
      let el = document.elementFromPoint(cx, cy);
      if (!el) continue;

      // Walk upward to the cell-sized element that best matches the mapped rectangle.
      let current = el;
      let best = el;
      let bestScore = Number.POSITIVE_INFINITY;
      for (let depth = 0; current && current !== document.body && depth < 7; depth++, current = current.parentElement) {
        if (!visible(current)) continue;
        const r = rectOf(current);
        const score = Math.abs(r.x - Number(cell.x)) + Math.abs(r.y - Number(cell.y)) +
          Math.abs(r.width - Number(cell.width || r.width)) + Math.abs(r.height - Number(cell.height || r.height));
        if (score < bestScore) { best = current; bestScore = score; }
      }

      const sig = signatureOf(best);
      if (!sig) continue;
      const key = `${cell.column_index}|${sig.tag}|${sig.id}|${sig.class_name}|${JSON.stringify(sig.attributes)}`;
      if (!seen.has(key)) {
        seen.add(key);
        signatures.push({
          column_index: cell.column_index,
          sample_student_code: student.code,
          sample_student_name: student.name,
          ...sig,
        });
      }
    }
  }

  return {
    column_count: mappedColumns.length,
    probed_cell_count: students.reduce((acc, s) => acc + (s.grade_cells || []).length, 0),
    columns: mappedColumns,
    cell_signatures: signatures.slice(0, 80),
  };
}
"""


def probe_grade_cells(page: Page, grade_cell_map: Any) -> GradeCellProbe:
    payload = grade_cell_map.as_dict() if hasattr(grade_cell_map, "as_dict") else grade_cell_map
    result = page.evaluate(_SCRIPT, payload)
    return GradeCellProbe(**result)
