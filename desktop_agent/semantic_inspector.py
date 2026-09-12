from __future__ import annotations

from dataclasses import dataclass, asdict
from typing import Any
from urllib.parse import urlparse

from playwright.sync_api import Page


@dataclass
class SemanticReport:
    site: str
    page_kind: str
    summary: dict[str, Any]

    def as_dict(self) -> dict[str, Any]:
        return asdict(self)


def classify_page(url: str) -> tuple[str, str]:
    value = url.lower()
    if "classroom.google.com" in value:
        if "/a/" in value or "/studentwork/" in value:
            return "classroom", "assignment_or_student_work"
        if "/c/" in value:
            return "classroom", "course"
        return "classroom", "home"

    if "sieweb.com.pe" in value or "sieweb" in value:
        if "/sistema/login" in value:
            return "sieweb", "login"
        if "registronotas" in value:
            return "sieweb", "registro_notas"
        if "/intranet/" in value:
            return "sieweb", "intranet"
        return "sieweb", "other"

    return "other", "other"


def _safe_text(locator, timeout: int = 500) -> str:
    try:
        return locator.inner_text(timeout=timeout).strip()
    except Exception:
        return ""


def _unique(items: list[str], limit: int = 80) -> list[str]:
    result: list[str] = []
    for item in items:
        value = " ".join(item.split())
        if value and value not in result:
            result.append(value[:500])
        if len(result) >= limit:
            break
    return result


def _visible_texts(page: Page, selector: str, limit: int = 80) -> list[str]:
    values: list[str] = []
    for locator in page.locator(selector).all()[:limit]:
        text = _safe_text(locator)
        if text:
            values.append(text)
    return _unique(values, limit)


def _links(page: Page, limit: int = 100) -> list[dict[str, str]]:
    result: list[dict[str, str]] = []
    for locator in page.locator("a[href]").all()[:limit]:
        try:
            href = locator.get_attribute("href") or ""
            text = _safe_text(locator)
            if href:
                result.append({"text": text[:300], "href": href[:1000]})
        except Exception:
            continue
    return result


def _selects(page: Page, limit: int = 30) -> list[dict[str, Any]]:
    result: list[dict[str, Any]] = []
    for locator in page.locator("select").all()[:limit]:
        try:
            name = locator.get_attribute("name") or ""
            element_id = locator.get_attribute("id") or ""
            aria = locator.get_attribute("aria-label") or ""
            options = []
            for option in locator.locator("option").all()[:80]:
                text = _safe_text(option)
                value = option.get_attribute("value") or ""
                selected = option.is_checked() if option.get_attribute("type") in {"checkbox", "radio"} else False
                try:
                    selected = bool(option.evaluate("el => el.selected"))
                except Exception:
                    pass
                if text or value:
                    options.append({"text": text[:200], "value": value[:200], "selected": selected})
            result.append({
                "name": name,
                "id": element_id,
                "aria_label": aria,
                "options": options,
            })
        except Exception:
            continue
    return result


def _tables(page: Page, max_tables: int = 12, max_rows: int = 40) -> list[dict[str, Any]]:
    tables: list[dict[str, Any]] = []
    for table in page.locator("table").all()[:max_tables]:
        try:
            headers = _visible_texts(table, "th", 40)
            rows: list[list[str]] = []
            for row in table.locator("tr").all()[:max_rows]:
                cells: list[str] = []
                for cell in row.locator("th, td").all()[:30]:
                    text = _safe_text(cell)
                    cells.append(" ".join(text.split())[:300])
                if any(cells):
                    rows.append(cells)
            tables.append({"headers": headers, "rows": rows, "row_count_sampled": len(rows)})
        except Exception:
            continue
    return tables


def _form_fields(page: Page, limit: int = 80) -> list[dict[str, str]]:
    result: list[dict[str, str]] = []
    for locator in page.locator("input, textarea, [contenteditable='true']").all()[:limit]:
        try:
            field_type = (locator.get_attribute("type") or "").lower()
            if field_type in {"password", "hidden"}:
                continue
            result.append({
                "tag": locator.evaluate("el => el.tagName.toLowerCase()"),
                "type": field_type,
                "name": locator.get_attribute("name") or "",
                "id": locator.get_attribute("id") or "",
                "aria_label": locator.get_attribute("aria-label") or "",
                "placeholder": locator.get_attribute("placeholder") or "",
            })
        except Exception:
            continue
    return result


def inspect_semantics(page: Page) -> SemanticReport:
    site, page_kind = classify_page(page.url)
    common = {
        "url": page.url,
        "title": page.title(),
        "headings": _visible_texts(page, "h1, h2, h3, [role='heading']", 80),
        "buttons": _visible_texts(page, "button, [role='button']", 80),
        "links": _links(page, 120),
    }

    if site == "classroom":
        classroom_links = [
            link for link in common["links"]
            if "classroom.google.com" in link["href"] or link["href"].startswith("/")
        ]
        course_links = [link for link in classroom_links if "/c/" in link["href"]]
        assignment_links = [link for link in classroom_links if "/a/" in link["href"] or "/studentwork/" in link["href"]]
        summary = {
            **common,
            "course_links": course_links[:80],
            "assignment_links": assignment_links[:80],
            "visible_labels": _visible_texts(page, "[aria-label]", 80),
        }
        return SemanticReport(site, page_kind, summary)

    if site == "sieweb":
        summary = {
            **common,
            "selects": _selects(page),
            "tables": _tables(page),
            "fields": _form_fields(page),
            "path": urlparse(page.url).path,
        }
        return SemanticReport(site, page_kind, summary)

    return SemanticReport(site, page_kind, common)
