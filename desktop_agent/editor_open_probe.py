from __future__ import annotations

from dataclasses import asdict, dataclass
from datetime import datetime
from pathlib import Path
from typing import Any

from playwright.sync_api import Page


@dataclass
class EditorOpenProbeResult:
    ok: bool
    student_code: str
    student_name: str
    student_order: str
    column_index: int
    column_label: str
    cell_text_before: str
    cell_text_after: str
    editor_detected: bool
    editor_elements: list[dict[str, Any]]
    network_requests: list[dict[str, Any]]
    escape_sent: bool
    editor_closed_after_escape: bool
    grade_text_unchanged: bool
    error: str = ""

    def as_dict(self) -> dict[str, Any]:
        return asdict(self)


def normalize_grade_view(page: Page) -> list[dict[str, Any]]:
    """Move scrollable grade surfaces to their left edge without changing data."""
    return page.evaluate(
        r"""
        () => {
          const changed = [];
          const all = [document.scrollingElement, ...document.querySelectorAll('body *')]
            .filter(Boolean);
          for (const el of all) {
            try {
              const sw = Number(el.scrollWidth || 0);
              const cw = Number(el.clientWidth || 0);
              const sl = Number(el.scrollLeft || 0);
              if (sw > cw + 40 && Math.abs(sl) > 1) {
                changed.push({
                  tag: String(el.tagName || 'document').toLowerCase(),
                  id: String(el.id || '').slice(0, 100),
                  class_name: String(el.className || '').slice(0, 180),
                  before: sl,
                  scroll_width: sw,
                  client_width: cw,
                });
                el.scrollLeft = 0;
              }
            } catch (_) {}
          }
          try { window.scrollTo(0, window.scrollY); } catch (_) {}
          return changed.slice(0, 30);
        }
        """
    )


def _safe_editor_snapshot(page: Page) -> list[dict[str, Any]]:
    return page.evaluate(
        r"""
        () => {
          const clean = (v, n=500) => String(v ?? '').replace(/\s+/g, ' ').trim().slice(0,n);
          const visible = (el) => {
            if (!el || !(el instanceof Element)) return false;
            const s = getComputedStyle(el);
            const r = el.getBoundingClientRect();
            return s.display !== 'none' && s.visibility !== 'hidden' && r.width > 0 && r.height > 0;
          };
          const selectors = [
            "[role='dialog']", ".q-dialog", ".q-menu", ".q-popup-edit", ".q-popup-proxy",
            "input:not([type='password']):not([type='hidden'])", "textarea", "select",
            "[contenteditable='true']"
          ];
          const seen = new Set();
          const out = [];
          for (const selector of selectors) {
            for (const el of document.querySelectorAll(selector)) {
              if (!visible(el) || seen.has(el)) continue;
              seen.add(el);
              const r = el.getBoundingClientRect();
              out.push({
                tag: el.tagName.toLowerCase(),
                role: clean(el.getAttribute('role'), 80),
                type: clean(el.getAttribute('type'), 80),
                id: clean(el.id, 120),
                class_name: clean(el.className, 240),
                aria_label: clean(el.getAttribute('aria-label'), 160),
                placeholder: clean(el.getAttribute('placeholder'), 160),
                text: clean(el.innerText || el.textContent, 600),
                value: ('value' in el) ? clean(el.value, 200) : '',
                rect: {x:r.x, y:r.y, width:r.width, height:r.height},
              });
            }
          }
          return out.slice(0, 80);
        }
        """
    )


def _visible_editor_signature(snapshot: list[dict[str, Any]]) -> set[str]:
    keys: set[str] = set()
    for item in snapshot:
        keys.add(
            "|".join(
                [
                    str(item.get("tag", "")),
                    str(item.get("role", "")),
                    str(item.get("id", "")),
                    str(item.get("class_name", "")),
                    str(item.get("placeholder", "")),
                ]
            )
        )
    return keys


def _cell_text(page: Page, x: float, y: float) -> str:
    return page.evaluate(
        "([x,y]) => { const e=document.elementFromPoint(x,y); return e ? String(e.innerText || e.textContent || '').trim().slice(0,300) : ''; }",
        [x, y],
    )


def probe_editor_open(
    page: Page,
    cell_map: Any,
    student_order: int,
    column_number: int,
    evidence_dir: Path,
) -> EditorOpenProbeResult:
    """Open exactly one mapped grade cell, inspect the editor, then press Escape.

    No value is typed and no save/submit control is activated. This is an interaction
    probe, not a grade-writing operation.
    """
    try:
        student = next(
            (s for s in cell_map.students if int(str(s.get("order") or 0)) == int(student_order)),
            None,
        )
        if not student:
            return EditorOpenProbeResult(False, "", "", str(student_order), column_number - 1, "", "", "", False, [], [], False, False, True, "Student order not found")

        cells = list(student.get("grade_cells") or [])
        cell = next((c for c in cells if int(c.get("column_index", -1)) == column_number - 1), None)
        if not cell:
            return EditorOpenProbeResult(False, str(student.get("code", "")), str(student.get("name", "")), str(student.get("order", "")), column_number - 1, "", "", "", False, [], [], False, False, True, "Mapped grade cell not found")

        column = next((c for c in cell_map.columns if int(c.get("index", -1)) == column_number - 1), {})
        label = str(column.get("header") or "")
        x = float(cell.get("x", 0)) + float(cell.get("width", 0)) / 2
        y = float(cell.get("y", 0)) + float(cell.get("height", 0)) / 2

        before_snapshot = _safe_editor_snapshot(page)
        before_signature = _visible_editor_signature(before_snapshot)
        before_text = _cell_text(page, x, y)
        requests: list[dict[str, Any]] = []

        def on_request(request) -> None:
            method = str(request.method or "GET").upper()
            if method in {"POST", "PUT", "PATCH", "DELETE"}:
                requests.append({
                    "method": method,
                    "url": str(request.url)[:600],
                    "resource_type": str(request.resource_type)[:80],
                })

        page.on("request", on_request)
        try:
            page.mouse.click(x, y)
            page.wait_for_timeout(700)
            after_snapshot = _safe_editor_snapshot(page)
            after_signature = _visible_editor_signature(after_snapshot)
            new_keys = after_signature - before_signature
            new_elements = [
                item for item in after_snapshot
                if "|".join([
                    str(item.get("tag", "")), str(item.get("role", "")),
                    str(item.get("id", "")), str(item.get("class_name", "")),
                    str(item.get("placeholder", "")),
                ]) in new_keys
            ]
            editor_detected = bool(new_elements)

            stamp = datetime.now().strftime("%Y%m%d_%H%M%S")
            open_png = evidence_dir / f"{stamp}_sieweb_editor_probe_open.png"
            try:
                page.screenshot(path=str(open_png), full_page=False)
            except Exception:
                pass

            page.keyboard.press("Escape")
            page.wait_for_timeout(450)
            closed_snapshot = _safe_editor_snapshot(page)
            closed_signature = _visible_editor_signature(closed_snapshot)
            editor_closed = not bool(new_keys & closed_signature)
            after_text = _cell_text(page, x, y)

            result = EditorOpenProbeResult(
                ok=True,
                student_code=str(student.get("code", "")),
                student_name=str(student.get("name", "")),
                student_order=str(student.get("order", "")),
                column_index=column_number - 1,
                column_label=label,
                cell_text_before=before_text,
                cell_text_after=after_text,
                editor_detected=editor_detected,
                editor_elements=new_elements[:30],
                network_requests=requests[:50],
                escape_sent=True,
                editor_closed_after_escape=editor_closed,
                grade_text_unchanged=(before_text == after_text),
            )
            return result
        finally:
            try:
                page.remove_listener("request", on_request)
            except Exception:
                pass
    except Exception as exc:
        return EditorOpenProbeResult(False, "", "", str(student_order), column_number - 1, "", "", "", False, [], [], False, False, True, str(exc)[:1000])
