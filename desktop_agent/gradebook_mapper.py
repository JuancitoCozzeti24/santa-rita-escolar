from __future__ import annotations

from dataclasses import asdict, dataclass
from typing import Any

from playwright.sync_api import Page


@dataclass
class GradebookMap:
    url: str
    title: str
    table_count: int
    grid_count: int
    control_count: int
    tables: list[dict[str, Any]]
    grids: list[dict[str, Any]]
    controls: list[dict[str, Any]]
    grade_like_values: list[str]

    def as_dict(self) -> dict[str, Any]:
        return asdict(self)


def map_gradebook(page: Page) -> GradebookMap:
    """Read the visible SIEweb gradebook structure without modifying the page.

    Password/hidden controls are excluded. Values from ordinary grade controls are
    read because the purpose of this phase is to understand the current gradebook
    structure before any write capability is introduced.
    """

    payload = page.evaluate(
        """
        () => {
          const visible = (el) => {
            const style = window.getComputedStyle(el);
            const rect = el.getBoundingClientRect();
            return style.display !== 'none' && style.visibility !== 'hidden' && rect.width >= 0 && rect.height >= 0;
          };

          const clean = (value, max = 400) => String(value ?? '')
            .replace(/\s+/g, ' ')
            .trim()
            .slice(0, max);

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

          const allControls = Array.from(document.querySelectorAll(controlSelector))
            .filter(visible)
            .map((el, index) => ({ index, ...readControl(el) }))
            .filter(Boolean);

          const tables = Array.from(document.querySelectorAll('table')).map((table, tableIndex) => {
            const rows = Array.from(table.querySelectorAll('tr'));
            const mappedRows = rows.slice(0, 100).map((row, rowIndex) => {
              const cells = Array.from(row.querySelectorAll(':scope > th, :scope > td'));
              return {
                row_index: rowIndex,
                text: clean(row.innerText || row.textContent, 1000),
                cells: cells.slice(0, 80).map((cell, columnIndex) => ({
                  column_index: columnIndex,
                  tag: cell.tagName.toLowerCase(),
                  text: clean(cell.innerText || cell.textContent, 500),
                  colspan: Number(cell.getAttribute('colspan') || 1),
                  rowspan: Number(cell.getAttribute('rowspan') || 1),
                  controls: Array.from(cell.querySelectorAll(controlSelector))
                    .filter(visible)
                    .slice(0, 12)
                    .map(readControl)
                    .filter(Boolean),
                })),
              };
            });

            const headers = [];
            Array.from(table.querySelectorAll('th')).slice(0, 120).forEach((th) => {
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
                rows: rows.slice(0, 100).map((row, rowIndex) => ({
                  row_index: rowIndex,
                  text: clean(row.innerText || row.textContent, 1000),
                  cells: Array.from(row.querySelectorAll('[role="columnheader"], [role="rowheader"], [role="gridcell"], [role="cell"]'))
                    .slice(0, 80)
                    .map((cell, columnIndex) => ({
                      column_index: columnIndex,
                      role: clean(cell.getAttribute('role'), 100),
                      text: clean(cell.innerText || cell.textContent, 500),
                      controls: Array.from(cell.querySelectorAll(controlSelector))
                        .filter(visible)
                        .slice(0, 12)
                        .map(readControl)
                        .filter(Boolean),
                    })),
                })),
              };
            });

          const gradePattern = /^(AD|A|B|C|[0-9]|1[0-9]|20)$/i;
          const gradeLike = [];
          const consider = (value) => {
            const v = clean(value, 30).toUpperCase();
            if (v && gradePattern.test(v) && !gradeLike.includes(v)) gradeLike.push(v);
          };
          allControls.forEach((c) => {
            consider(c.value);
            consider(c.selected_text);
          });
          tables.forEach((table) => table.rows.forEach((row) => row.cells.forEach((cell) => {
            consider(cell.text);
            cell.controls.forEach((c) => {
              consider(c.value);
              consider(c.selected_text);
            });
          })));

          return {
            url: location.href,
            title: document.title,
            table_count: tables.length,
            grid_count: roleGrids.length,
            control_count: allControls.length,
            tables,
            grids: roleGrids,
            controls: allControls.slice(0, 300),
            grade_like_values: gradeLike,
          };
        }
        """
    )

    return GradebookMap(**payload)
