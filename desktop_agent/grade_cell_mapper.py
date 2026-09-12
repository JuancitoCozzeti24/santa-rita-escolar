from __future__ import annotations

from dataclasses import asdict, dataclass
from typing import Any

from playwright.sync_api import Page


@dataclass
class GradeCellMap:
    student_count: int
    mapped_student_count: int
    column_count: int
    columns: list[dict[str, Any]]
    students: list[dict[str, Any]]

    def as_dict(self) -> dict[str, Any]:
        return asdict(self)


_SCRIPT = r"""
() => {
  const clean = (value, max = 500) => String(value ?? '')
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

  const all = Array.from(document.querySelectorAll('body *')).filter(visible);

  const leafTexts = (root) => Array.from(root.querySelectorAll('*'))
    .filter(visible)
    .filter((el) => Array.from(el.children).filter(visible).length === 0)
    .map((el) => ({el, text: clean(el.innerText || el.textContent, 300), rect: rectOf(el)}))
    .filter((x) => x.text);

  const chooseRow = (codeEl) => {
    const code = clean(codeEl.innerText || codeEl.textContent, 40);
    let current = codeEl;
    const options = [];
    for (let depth = 0; current && current !== document.body && depth < 10; depth++, current = current.parentElement) {
      if (!visible(current)) continue;
      const r = current.getBoundingClientRect();
      if (r.width < 250 || r.height < 12 || r.height > 80) continue;
      const text = clean(current.innerText || current.textContent, 1600);
      if (!text.includes(code)) continue;
      const leaves = leafTexts(current);
      const hasName = leaves.some((x) => /[A-Za-zÁÉÍÓÚÜÑáéíóúüñ]{2,}.*[, ].*[A-Za-zÁÉÍÓÚÜÑáéíóúüñ]{2,}/.test(x.text));
      if (!hasName) continue;
      options.push({el: current, rect: rectOf(current), leaves, depth});
    }
    if (!options.length) return null;
    options.sort((a,b) => (a.rect.height-b.rect.height) || (a.rect.width-b.rect.width) || (a.depth-b.depth));
    return options[0];
  };

  const students = [];
  const seenCodes = new Set();
  for (const el of all) {
    const text = clean(el.innerText || el.textContent, 40);
    if (!/^\d{8}$/.test(text) || seenCodes.has(text)) continue;
    const row = chooseRow(el);
    if (!row) continue;
    const texts = row.leaves.map((x) => x.text);
    let order = '';
    for (const t of texts) {
      if (/^\d{1,2}$/.test(t) && Number(t) >= 1 && Number(t) <= 60) { order = t; break; }
    }
    let name = '';
    for (const t of texts) {
      if (t === text || t === order) continue;
      if (/[A-Za-zÁÉÍÓÚÜÑáéíóúüñ]{2,}/.test(t) && (t.includes(',') || t.split(' ').length >= 2)) {
        name = t; break;
      }
    }
    seenCodes.add(text);
    students.push({code: text, order, name, row_rect: row.rect});
  }
  students.sort((a,b) => Number(a.order || 999) - Number(b.order || 999));

  if (!students.length) return {student_count: 0, mapped_student_count: 0, column_count: 0, columns: [], students: []};

  // Candidate grade cells are blank or text-bearing rectangles aligned with student rows,
  // to the right of the fixed name pane. SIEweb renders these cells separately from the
  // code/order/name row, so geometry is the stable bridge between both panes.
  const firstRight = Math.max(...students.map((s) => s.row_rect.right));
  const minGradeX = Math.max(450, firstRight - 8);
  const maxGradeX = Math.min(window.innerWidth - 10, minGradeX + 900);

  const elementCandidates = all.map((el) => {
    const r = rectOf(el);
    const style = getComputedStyle(el);
    return {
      el,
      rect: r,
      tag: el.tagName.toLowerCase(),
      id: clean(el.id, 120),
      class_name: clean(el.className, 240),
      role: clean(el.getAttribute('role'), 100),
      text: clean(el.innerText || el.textContent, 120),
      background: clean(style.backgroundColor, 80),
      border_left: clean(style.borderLeftColor, 80),
      cursor: clean(style.cursor, 40),
      child_count: Array.from(el.children).filter(visible).length,
    };
  }).filter((c) => {
    const r = c.rect;
    return r.x >= minGradeX - 12 && r.x < maxGradeX &&
      r.width >= 18 && r.width <= 180 && r.height >= 12 && r.height <= 42;
  });

  const byStudent = new Map();
  const xSupport = new Map();

  for (const student of students) {
    const rr = student.row_rect;
    const rowHeight = Math.max(14, rr.height);
    const candidates = elementCandidates.filter((c) => {
      const r = c.rect;
      const overlap = Math.max(0, Math.min(r.bottom, rr.bottom) - Math.max(r.y, rr.y));
      const ratio = overlap / Math.min(r.height, rowHeight);
      const centerAligned = Math.abs(r.cy - (rr.y + rr.height/2)) <= Math.max(4, rowHeight * 0.45);
      return ratio >= 0.65 && centerAligned;
    });

    // Deduplicate nested elements occupying the same visual cell. Prefer the smallest area,
    // then fewer children, because it is usually the actual clickable cell surface.
    const buckets = new Map();
    for (const c of candidates) {
      const bx = Math.round(c.rect.x / 2) * 2;
      const bw = Math.round(c.rect.width / 2) * 2;
      const key = `${bx}|${bw}`;
      const area = c.rect.width * c.rect.height;
      const prev = buckets.get(key);
      if (!prev || area < prev.area || (area === prev.area && c.child_count < prev.item.child_count)) {
        buckets.set(key, {item: c, area});
      }
    }

    const compact = Array.from(buckets.values()).map((x) => x.item);
    byStudent.set(student.code, compact);
    const seenX = new Set();
    for (const c of compact) {
      const key = Math.round(c.rect.x / 3) * 3;
      if (seenX.has(key)) continue;
      seenX.add(key);
      xSupport.set(key, (xSupport.get(key) || 0) + 1);
    }
  }

  const minSupport = Math.max(4, Math.ceil(students.length * 0.55));
  const supportedX = Array.from(xSupport.entries())
    .filter(([,count]) => count >= minSupport)
    .map(([x,count]) => ({x: Number(x), support: count}))
    .sort((a,b) => a.x - b.x);

  // Collapse adjacent x buckets generated by nested borders of the same column.
  const clusters = [];
  for (const item of supportedX) {
    const last = clusters[clusters.length - 1];
    if (last && Math.abs(item.x - last.x) <= 8) {
      if (item.support > last.support) {
        last.x = item.x;
        last.support = item.support;
      }
    } else {
      clusters.push({...item});
    }
  }

  const firstStudentY = Math.min(...students.map((s) => s.row_rect.y));
  const headerPool = all.map((el) => ({
    el,
    text: clean(el.innerText || el.textContent, 500),
    rect: rectOf(el),
    child_count: Array.from(el.children).filter(visible).length,
  })).filter((h) => h.text && h.rect.bottom <= firstStudentY + 3 && h.rect.y >= firstStudentY - 180);

  const columns = clusters.map((cluster, index) => {
    const rowSamples = [];
    for (const student of students) {
      const candidates = byStudent.get(student.code) || [];
      const best = candidates
        .filter((c) => Math.abs(c.rect.x - cluster.x) <= 10)
        .sort((a,b) => Math.abs(a.rect.x-cluster.x) - Math.abs(b.rect.x-cluster.x))[0];
      if (best) rowSamples.push(best);
    }
    const avgWidth = rowSamples.length ? rowSamples.reduce((a,c) => a+c.rect.width,0)/rowSamples.length : 0;
    const center = cluster.x + avgWidth/2;
    const headers = headerPool
      .filter((h) => h.rect.x - 3 <= center && h.rect.right + 3 >= center)
      .sort((a,b) => {
        const da = firstStudentY - a.rect.bottom;
        const db = firstStudentY - b.rect.bottom;
        if (da !== db) return da-db;
        return (a.rect.width*a.rect.height) - (b.rect.width*b.rect.height);
      });
    const header = headers[0];
    const sample = rowSamples[0];
    return {
      index,
      x: cluster.x,
      support: cluster.support,
      average_width: Math.round(avgWidth*10)/10,
      header: header ? header.text : '',
      header_rect: header ? header.rect : null,
      sample_tag: sample ? sample.tag : '',
      sample_class: sample ? sample.class_name : '',
      sample_background: sample ? sample.background : '',
      sample_cursor: sample ? sample.cursor : '',
    };
  });

  const mappedStudents = students.map((student) => {
    const rowCandidates = byStudent.get(student.code) || [];
    const cells = columns.map((col) => {
      const best = rowCandidates
        .filter((c) => Math.abs(c.rect.x - col.x) <= 10)
        .sort((a,b) => Math.abs(a.rect.x-col.x) - Math.abs(b.rect.x-col.x))[0];
      if (!best) return null;
      return {
        column_index: col.index,
        x: best.rect.x,
        y: best.rect.y,
        width: best.rect.width,
        height: best.rect.height,
        text: best.text,
        tag: best.tag,
        id: best.id,
        class_name: best.class_name,
        role: best.role,
        background: best.background,
        cursor: best.cursor,
      };
    }).filter(Boolean);
    return {...student, grade_cells: cells};
  });

  return {
    student_count: students.length,
    mapped_student_count: mappedStudents.filter((s) => s.grade_cells.length > 0).length,
    column_count: columns.length,
    columns,
    students: mappedStudents,
  };
}
"""


def map_grade_cells(page: Page) -> GradeCellMap:
    payload = page.evaluate(_SCRIPT)
    return GradeCellMap(**payload)
