from __future__ import annotations

import json
from dataclasses import asdict, dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from playwright.sync_api import BrowserContext, Page, sync_playwright


@dataclass
class PageReport:
    captured_at: str
    site: str
    url: str
    title: str
    headings: list[str]
    buttons: list[str]
    links: list[str]
    inputs: list[dict[str, str]]


class ReadOnlyBrowserController:
    """Phase 1 controller: inspect pages without intentionally writing to them."""

    def __init__(self, profile_dir: Path, evidence_dir: Path) -> None:
        self.profile_dir = profile_dir.resolve()
        self.evidence_dir = evidence_dir.resolve()
        self.profile_dir.mkdir(parents=True, exist_ok=True)
        self.evidence_dir.mkdir(parents=True, exist_ok=True)
        self._pw: Any = None
        self.context: BrowserContext | None = None

    def start(self) -> BrowserContext:
        self._pw = sync_playwright().start()
        self.context = self._pw.chromium.launch_persistent_context(
            user_data_dir=str(self.profile_dir),
            channel="chrome",
            headless=False,
            viewport=None,
            args=["--start-maximized"],
        )
        return self.context

    def stop(self) -> None:
        if self.context is not None:
            self.context.close()
            self.context = None
        if self._pw is not None:
            self._pw.stop()
            self._pw = None

    @staticmethod
    def detect_site(url: str) -> str:
        value = url.lower()
        if "classroom.google.com" in value:
            return "classroom"
        if "sieweb" in value or "sieroom" in value:
            return "sieweb"
        return "other"

    @staticmethod
    def _texts(page: Page, selector: str, limit: int = 40) -> list[str]:
        result: list[str] = []
        for locator in page.locator(selector).all()[:limit]:
            try:
                text = locator.inner_text(timeout=500).strip()
            except Exception:
                continue
            if text and text not in result:
                result.append(text[:300])
        return result

    def inspect(self, page: Page) -> PageReport:
        inputs: list[dict[str, str]] = []
        for locator in page.locator("input, textarea, [contenteditable='true']").all()[:40]:
            try:
                inputs.append({
                    "tag": locator.evaluate("el => el.tagName.toLowerCase()"),
                    "type": locator.get_attribute("type") or "",
                    "name": locator.get_attribute("name") or "",
                    "aria_label": locator.get_attribute("aria-label") or "",
                    "placeholder": locator.get_attribute("placeholder") or "",
                })
            except Exception:
                continue

        return PageReport(
            captured_at=datetime.now(timezone.utc).isoformat(),
            site=self.detect_site(page.url),
            url=page.url,
            title=page.title(),
            headings=self._texts(page, "h1, h2, h3, [role='heading']"),
            buttons=self._texts(page, "button, [role='button']"),
            links=self._texts(page, "a"),
            inputs=inputs,
        )

    def save_evidence(self, page: Page, report: PageReport) -> tuple[Path, Path]:
        stamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        base = self.evidence_dir / f"{stamp}_{report.site}"
        json_path = base.with_suffix(".json")
        png_path = base.with_suffix(".png")
        json_path.write_text(json.dumps(asdict(report), ensure_ascii=False, indent=2), encoding="utf-8")
        page.screenshot(path=str(png_path), full_page=False)
        return json_path, png_path
