from __future__ import annotations

from dataclasses import asdict, dataclass
from datetime import datetime
from pathlib import Path
from typing import Any

from playwright.sync_api import Page


@dataclass
class EditorOpenProbeV2Result:
    ok: bool
    student_code: str
    student_name: str
    student_order: str
    column_index: int
    column_label: str
    selected_before: str
    selected_after_row_click: str
    row_selection_confirmed: bool
    cell_text_before: str
    cell_text_after: str
    editor_detected: bool
    editor_detection_reasons: list[str]
    editor_elements: list[dict[str, Any]]
    active_before: dict[str, Any]
    active_after_open: dict[str, Any]
    network_requests_row_select: list[dict[str, Any]]
    network_requests_editor_open: list[dict[str, Any]]
    escape_sent: bool
    editor_closed_after_escape: bool
    grade_text_unchanged: bool
    error: str = ""

    def as_dict(self) -> dict[str, Any]:
        return asdict(self)


def _clean_text(value: str) -> str:
    return " ".join(str(value or "").replace("\xa0", " ").split())


def _selected_student_line(page: Page) -> str:
    return page.evaluate(
        r"""
        () => {
          const text = String(document.body?.innerText || '');
          const lines = text.split(/\r?\n/).map(x => x.replace(/\s+/g,' ').trim()).filter(Boolean);
          const hit = lines.find(x => /^Estudiante\s*:/i.test(x));
          return hit || '';
        }
        """
    )


def _active_element(page: Page) -> dict[str, Any]:
    return page.evaluate(
        r"""
        () => {
          const el = document.activeElement;
          if (!el) return {};
          const r = el.getBoundingClientRect ? el.getBoundingClientRect() : {x:0,y:0,width:0,height:0};
          const safeValue = (() => {
            try {
              const type = String(el.getAttribute?.('type') || '').toLowerCase();
              if (type === 'password' || type === 'hidden') return '';
              return ('value' in el) ? String(el.value ?? '').slice(0,200) : '';
            } catch (_) { return ''; }
          })();
          return {
            tag: String(el.tagName || '').toLowerCase(),
            id: String(el.id || '').slice(0,120),
            class_name: String(el.className || '').slice(0,240),
            role: String(el.getAttribute?.('role') || '').slice(0,80),
            type: String(el.getAttribute?.('type') || '').slice(0,80),
            contenteditable: String(el.getAttribute?.('contenteditable') || '').slice(0,40),
            value: safeValue,
            rect: {x:r.x||0,y:r.y||0,width:r.width||0,height:r.height||0},
          };
        }
        """
    )


def _editor_snapshot(page: Page) -> list[dict[str, Any]]:
    return page.evaluate(
        r"""
        () => {
          const clean = (v,n=500) => String(v ?? '').replace(/\s+/g,' ').trim().slice(0,n);
          const visible = (el) => {
            if (!el || !(el instanceof Element)) return false;
            const s = getComputedStyle(el), r = el.getBoundingClientRect();
            return s.display !== 'none' && s.visibility !== 'hidden' && r.width > 0 && r.height > 0;
          };
          const selectors = [
            "[role='dialog']", ".q-dialog", ".q-menu", ".q-popup-edit", ".q-popup-proxy",
            ".q-field", ".q-select", ".q-input", ".q-card",
            "input:not([type='password']):not([type='hidden'])", "textarea", "select",
            "[contenteditable='true']", "[role='listbox']", "[role='option']", "[role='combobox']"
          ];
          const out=[], seen=new Set();
          for (const selector of selectors) {
            for (const el of document.querySelectorAll(selector)) {
              if (!visible(el) || seen.has(el)) continue;
              seen.add(el);
              const r = el.getBoundingClientRect();
              const type = clean(el.getAttribute('type'),80).toLowerCase();
              const value = (type === 'password' || type === 'hidden') ? '' : (('value' in el) ? clean(el.value,200) : '');
              out.push({
                tag: el.tagName.toLowerCase(), role: clean(el.getAttribute('role'),80), type,
                id: clean(el.id,120), class_name: clean(el.className,240),
                aria_label: clean(el.getAttribute('aria-label'),160), placeholder: clean(el.getAttribute('placeholder'),160),
                text: clean(el.innerText || el.textContent,600), value,
                rect: {x:r.x,y:r.y,width:r.width,height:r.height},
              });
            }
          }
          return out.slice(0,120);
        }
        """
    )


def _signature(item: dict[str, Any]) -> str:
    return "|".join([
        str(item.get("tag", "")), str(item.get("role", "")), str(item.get("type", "")),
        str(item.get("id", "")), str(item.get("class_name", "")), str(item.get("placeholder", "")),
        str(round(float((item.get("rect") or {}).get("x", 0)), 1)),
        str(round(float((item.get("rect") or {}).get("y", 0)), 1)),
    ])


def _cell_text(page: Page, x: float, y: float) -> str:
    return page.evaluate(
        "([x,y]) => { const e=document.elementFromPoint(x,y); return e ? String(e.innerText || e.textContent || '').trim().slice(0,300) : ''; }",
        [x, y],
    )


def _request_recorder(target: list[dict[str, Any]]):
    def handler(request) -> None:
        method = str(request.method or "GET").upper()
        if method in {"POST", "PUT", "PATCH", "DELETE"}:
            target.append({"method": method, "url": str(request.url)[:600], "resource_type": str(request.resource_type)[:80]})
    return handler


def probe_editor_open_v2(page: Page, cell_map: Any, student_order: int, column_number: int, evidence_dir: Path) -> EditorOpenProbeV2Result:
    """Select target student first, then open one mapped grade cell, observe, and Escape.

    No value is typed and no save/submit control is activated.
    """
    try:
        student = next((s for s in cell_map.students if int(str(s.get("order") or 0)) == int(student_order)), None)
        if not student:
            return EditorOpenProbeV2Result(False,"","",str(student_order),column_number-1,"","","",False,"","",False,[],[],{}, {},[],[],False,False,True,"Student order not found")

        cells = list(student.get("grade_cells") or [])
        cell = next((c for c in cells if int(c.get("column_index", -1)) == column_number - 1), None)
        if not cell:
            return EditorOpenProbeV2Result(False,str(student.get("code","")),str(student.get("name","")),str(student.get("order","")),column_number-1,"","","",False,"","",False,[],[],{}, {},[],[],False,False,True,"Mapped grade cell not found")

        column = next((c for c in cell_map.columns if int(c.get("index", -1)) == column_number - 1), {})
        label = str(column.get("header") or "")
        row_rect = student.get("row_rect") or {}
        row_x = float(row_rect.get("x", 0)) + max(10.0, float(row_rect.get("width", 0)) * 0.72)
        row_y = float(row_rect.get("y", 0)) + float(row_rect.get("height", 0)) / 2
        cell_x = float(cell.get("x", 0)) + float(cell.get("width", 0)) / 2
        cell_y = float(cell.get("y", 0)) + float(cell.get("height", 0)) / 2

        selected_before = _selected_student_line(page)
        row_requests: list[dict[str, Any]] = []
        row_handler = _request_recorder(row_requests)
        page.on("request", row_handler)
        try:
            page.mouse.click(row_x, row_y)
            page.wait_for_timeout(650)
        finally:
            try: page.remove_listener("request", row_handler)
            except Exception: pass

        selected_after = _selected_student_line(page)
        target_name = _clean_text(str(student.get("name", ""))).casefold()
        selected_norm = _clean_text(selected_after).casefold()
        row_confirmed = bool(target_name and target_name in selected_norm)

        before_snapshot = _editor_snapshot(page)
        before_signatures = {_signature(x) for x in before_snapshot}
        active_before = _active_element(page)
        before_text = _cell_text(page, cell_x, cell_y)

        open_requests: list[dict[str, Any]] = []
        open_handler = _request_recorder(open_requests)
        page.on("request", open_handler)
        try:
            page.mouse.click(cell_x, cell_y)
            page.wait_for_timeout(750)
            after_snapshot = _editor_snapshot(page)
            after_signatures = {_signature(x) for x in after_snapshot}
            active_after = _active_element(page)
            new_keys = after_signatures - before_signatures
            new_elements = [x for x in after_snapshot if _signature(x) in new_keys]

            reasons: list[str] = []
            if new_elements:
                reasons.append(f"{len(new_elements)} elementos visibles nuevos")
            tag_after = str(active_after.get("tag", ""))
            role_after = str(active_after.get("role", ""))
            ce_after = str(active_after.get("contenteditable", ""))
            if tag_after in {"input", "textarea", "select"}:
                reasons.append(f"activeElement={tag_after}")
            if role_after in {"combobox", "listbox", "textbox"}:
                reasons.append(f"activeElement role={role_after}")
            if ce_after.lower() == "true":
                reasons.append("activeElement contenteditable=true")
            if active_after and active_after != active_before and (tag_after or role_after or ce_after):
                reasons.append("activeElement cambió tras abrir")
            editor_detected = bool(reasons)

            stamp = datetime.now().strftime("%Y%m%d_%H%M%S")
            try: page.screenshot(path=str(evidence_dir / f"{stamp}_sieweb_editor_probe_v2_open.png"), full_page=False)
            except Exception: pass

            page.keyboard.press("Escape")
            page.wait_for_timeout(500)
            closed_snapshot = _editor_snapshot(page)
            closed_signatures = {_signature(x) for x in closed_snapshot}
            active_closed = _active_element(page)
            new_still_visible = bool(new_keys & closed_signatures)
            active_is_editor = str(active_closed.get("tag", "")) in {"input", "textarea", "select"} or str(active_closed.get("role", "")) in {"combobox", "listbox", "textbox"} or str(active_closed.get("contenteditable", "")).lower() == "true"
            editor_closed = not new_still_visible and not active_is_editor
            after_text = _cell_text(page, cell_x, cell_y)

            return EditorOpenProbeV2Result(
                ok=True,
                student_code=str(student.get("code", "")), student_name=str(student.get("name", "")), student_order=str(student.get("order", "")),
                column_index=column_number-1, column_label=label,
                selected_before=selected_before, selected_after_row_click=selected_after, row_selection_confirmed=row_confirmed,
                cell_text_before=before_text, cell_text_after=after_text,
                editor_detected=editor_detected, editor_detection_reasons=reasons, editor_elements=new_elements[:40],
                active_before=active_before, active_after_open=active_after,
                network_requests_row_select=row_requests[:50], network_requests_editor_open=open_requests[:50],
                escape_sent=True, editor_closed_after_escape=editor_closed, grade_text_unchanged=(before_text == after_text),
            )
        finally:
            try: page.remove_listener("request", open_handler)
            except Exception: pass
    except Exception as exc:
        return EditorOpenProbeV2Result(False,"","",str(student_order),column_number-1,"","","",False,"","",False,[],[],{}, {},[],[],False,False,True,str(exc)[:1000])
