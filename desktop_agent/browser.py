from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Any
import base64

from playwright.sync_api import BrowserContext, Error, Page, Playwright, sync_playwright

from .settings import DesktopSettings


@dataclass(frozen=True)
class Observation:
    url: str
    title: str
    screenshot_b64: str
    viewport: dict[str, int]


class SchoolBrowser:
    """Navegador dedicado. La imagen es la observación primaria; el DOM es respaldo."""

    def __init__(self, settings: DesktopSettings) -> None:
        self.settings = settings
        self._playwright: Playwright | None = None
        self.context: BrowserContext | None = None
        self.pages: dict[str, Page] = {}

    def start(self) -> "SchoolBrowser":
        self.settings.data_dir.mkdir(parents=True, exist_ok=True)
        self._playwright = sync_playwright().start()
        profile = self.settings.data_dir / "browser-profile"
        launch_options = {
            "headless": self.settings.headless,
            "viewport": {"width": 1440, "height": 960},
            "args": ["--disable-background-timer-throttling"],
        }
        last_error: Exception | None = None
        for channel in ("chrome", "msedge", None):
            try:
                options = dict(launch_options)
                if channel:
                    options["channel"] = channel
                self.context = self._playwright.chromium.launch_persistent_context(
                    str(profile), **options
                )
                break
            except Error as exc:
                last_error = exc
        if self.context is None:
            raise RuntimeError("No se pudo iniciar Chrome, Edge ni Chromium.") from last_error
        existing = list(self.context.pages)
        classroom = existing[0] if existing else self.context.new_page()
        classroom.goto(self.settings.classroom_url, wait_until="domcontentloaded")
        cieweb = self.context.new_page()
        cieweb.goto(self.settings.cieweb_url, wait_until="domcontentloaded")
        self.pages = {"classroom": classroom, "cieweb": cieweb}
        classroom.bring_to_front()
        return self

    def page(self, name: str) -> Page:
        normalized = name.strip().lower()
        if normalized not in self.pages:
            raise ValueError("La pestaña debe ser 'classroom' o 'cieweb'.")
        page = self.pages[normalized]
        page.bring_to_front()
        return page

    def observe(self, name: str) -> Observation:
        page = self.page(name)
        raw = page.screenshot(type="jpeg", quality=78, full_page=False)
        viewport = page.viewport_size or {"width": 1440, "height": 960}
        return Observation(
            url=page.url,
            title=page.title(),
            screenshot_b64=base64.b64encode(raw).decode("ascii"),
            viewport=viewport,
        )

    def dom_fallback(self, name: str, selector: str, action: str, value: str = "") -> None:
        """Respaldo acotado; nunca se usa para explorar o inferir por defecto."""
        locator = self.page(name).locator(selector).first
        locator.wait_for(state="visible", timeout=5_000)
        if action == "click":
            locator.click()
        elif action == "fill":
            locator.fill(value)
        else:
            raise ValueError(f"Acción DOM no admitida: {action}")

    def execute(self, name: str, action: dict[str, Any]) -> None:
        page = self.page(name)
        kind = str(action.get("type") or "")
        if kind == "click":
            page.mouse.click(float(action["x"]), float(action["y"]))
        elif kind == "type":
            page.keyboard.type(str(action.get("text") or ""), delay=12)
        elif kind == "press":
            page.keyboard.press(str(action["key"]))
        elif kind == "scroll":
            page.mouse.wheel(float(action.get("dx", 0)), float(action.get("dy", 600)))
        elif kind == "wait":
            page.wait_for_timeout(min(int(action.get("ms", 750)), 10_000))
        elif kind == "dom_fallback":
            self.dom_fallback(name, str(action["selector"]), str(action["action"]), str(action.get("value") or ""))
        else:
            raise ValueError(f"Acción visual no admitida: {kind}")

    def close(self) -> None:
        if self.context is not None:
            self.context.close()
        if self._playwright is not None:
            self._playwright.stop()

    def __enter__(self) -> "SchoolBrowser":
        return self.start()

    def __exit__(self, *_: object) -> None:
        self.close()
