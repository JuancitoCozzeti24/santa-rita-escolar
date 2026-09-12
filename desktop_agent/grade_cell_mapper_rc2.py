from __future__ import annotations

from dataclasses import replace
from typing import Any

from playwright.sync_api import Page

from grade_cell_mapper import GradeCellMap, map_grade_cells as base_map_grade_cells


_REMAP_SCRIPT = r"""
(payload) => {
  const clean = (value, max = 400) => String(value ?? '')
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

  const students = payload.students || [];
  if (!students.length) {
    return {columns: payload.columns || [], students, remapped: false, reason: 'no_students'};
  }

  // SIEweb usa estas superficies para las celdas de competencia. Esta detección
  // es independiente del ancho de la ventana: evita el antiguo corte fijo x>=450,
  // que podía ocultar la primera competencia en pantallas más estrechas.
  const cells = Array.from(document.querySelectorAll('.td.bgprograma_3'))
    .filter(visible)
    .map(el => ({
      el,
      rect: rectOf(el),
      text: clean(el.innerText || el.textContent, 120),
      class_name: clean(el.className, 240),
      tag: el.tagName.toLowerCase(),
      id: clean(el.id, 120),
      role: clean(el.getAttribute('role'), 80),
      cursor: clean(getComputedStyle(el).cursor, 40),
      background: clean(getComputedStyle(el).backgroundColor, 80),
    }))
    .filter(c => c.rect.width >= 18 && c.rect.width <= 180 && c.rect.height >= 12 && c.rect.height <= 42);

  if (!cells.length) {
    return {columns: payload.columns || [], students, remapped: false, reason: 'no_program_cells'};
  }

  const byStudent = new Map();
  const support = new Map();

  for (const student of students) {
    const rr = student.row_rect || {};
    const rowY = Number(rr.y || 0);
    const rowH = Math.max(14, Number(rr.height || 20));
    const rowBottom = rowY + rowH;
    const rowCenter = rowY + rowH / 2;

    const aligned = cells.filter(c => {
      const r = c.rect;
      const overlap = Math.max(0, Math.min(r.bottom, rowBottom) - Math.max(r.y, rowY));
      const ratio = overlap / Math.min(r.height, rowH);
      const centerAligned = Math.abs(r.cy - rowCenter) <= Math.max(5, rowH * 0.48);
      return ratio >= 0.60 && centerAligned;
    });

    // Deduplicar superficies anidadas por posición.
    const buckets = new Map();
    for (const c of aligned) {
      const bx = Math.round(c.rect.x / 2) * 2;
      const bw = Math.round(c.rect.width / 2) * 2;
      const key = `${bx}|${bw}`;
      const area = c.rect.width * c.rect.height;
      const prev = buckets.get(key);
      if (!prev || area < prev.area) buckets.set(key, {area, item: c});
    }

    const compact = Array.from(buckets.values()).map(x => x.item).sort((a,b) => a.rect.x - b.rect.x);
    byStudent.set(student.code, compact);

    const seen = new Set();
    for (const c of compact) {
      const key = Math.round(c.rect.x / 3) * 3;
      if (seen.has(key)) continue;
      seen.add(key);
      support.set(key, (support.get(key) || 0) + 1);
    }
  }

  const minSupport = Math.max(4, Math.ceil(students.length * 0.55));
  const supported = Array.from(support.entries())
    .filter(([, count]) => count >= minSupport)
    .map(([x, count]) => ({x: Number(x), support: count}))
    .sort((a,b) => a.x - b.x);

  const clusters = [];
  for (const item of supported) {
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

  if (!clusters.length) {
    return {columns: payload.columns || [], students, remapped: false, reason: 'no_supported_columns'};
  }

  const columns = clusters.map((cluster, index) => {
    const samples = [];
    for (const student of students) {
      const candidates = byStudent.get(student.code) || [];
      const best = candidates
        .filter(c => Math.abs(c.rect.x - cluster.x) <= 10)
        .sort((a,b) => Math.abs(a.rect.x - cluster.x) - Math.abs(b.rect.x - cluster.x))[0];
      if (best) samples.push(best);
    }
    const avgWidth = samples.length ? samples.reduce((acc, c) => acc + c.rect.width, 0) / samples.length : 0;
    const sample = samples[0];
    return {
      index,
      x: cluster.x,
      support: cluster.support,
      average_width: Math.round(avgWidth * 10) / 10,
      header: '',
      header_rect: null,
      sample_tag: sample ? sample.tag : '',
      sample_class: sample ? sample.class_name : '',
      sample_background: sample ? sample.background : '',
      sample_cursor: sample ? sample.cursor : '',
    };
  });

  const mappedStudents = students.map(student => {
    const candidates = byStudent.get(student.code) || [];
    const gradeCells = columns.map(col => {
      const best = candidates
        .filter(c => Math.abs(c.rect.x - col.x) <= 10)
        .sort((a,b) => Math.abs(a.rect.x - col.x) - Math.abs(b.rect.x - col.x))[0];
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
    return {...student, grade_cells: gradeCells};
  });

  return {
    columns,
    students: mappedStudents,
    remapped: true,
    reason: 'program_cells_dynamic_x',
  };
}
"""


def map_grade_cells_rc2(page: Page) -> GradeCellMap:
    base = base_map_grade_cells(page)
    if not base.students:
        return base

    payload: dict[str, Any] = base.as_dict()
    try:
        result = page.evaluate(_REMAP_SCRIPT, payload)
    except Exception:
        return base

    if not result.get("remapped"):
        return base

    columns = result.get("columns") or []
    students = result.get("students") or []
    if not columns or not students:
        return base

    return GradeCellMap(
        student_count=len(students),
        mapped_student_count=sum(1 for s in students if s.get("grade_cells")),
        column_count=len(columns),
        columns=columns,
        students=students,
    )


# Nombre uniforme para que el launcher pueda importarlo como mapper principal.
map_grade_cells = map_grade_cells_rc2
