from __future__ import annotations

import json
import os
import shutil
import socket
import subprocess
import time
import urllib.request
from dataclasses import asdict, dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from playwright.sync_api import Browser, BrowserContext, Page, sync_playwright


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
    """Phase 1 controller: inspect a normal local Chrome/Edge without writes.

    The browser is started as a regular installed browser with a dedicated
    persistent profile. Playwright attaches afterwards through Chrome DevTools
    Protocol (CDP), instead of launching Chrome in Playwright's test mode.
    """

    def __init__(self, profile_dir: Path, evidence_dir: Path) -> None:
        self.profile_dir = profile_dir.resolve()
        self.evidence_dir = evidence_dir.resolve()
        self.profile_dir.mkdir(parents=True, exist_ok=True)
        self.evidence_dir.mkdir(parents=True, exist_ok=True)
        self._pw: Any = None
        self._browser: Browser | None = None
        self._browser_process: subprocess.Popen[Any] | None = None
        self.context: BrowserContext | None = None
        self.browser_name: str = ""

    @staticmethod
    def _find_browser() -> tuple[Path, str]:
        candidates: list[tuple[Path, str]] = []

        for env_name in ("PROGRAMFILES", "PROGRAMFILES(X86)", "LOCALAPPDATA"):
            base = os.environ.get(env_name)
            if not base:
                continue
            root = Path(base)
            candidates.extend(
                [
                    (root / "Google" / "Chrome" / "Application" / "chrome.exe", "Google Chrome"),
                    (root / "Microsoft" / "Edge" / "Application" / "msedge.exe", "Microsoft Edge"),
                ]
            )

        for executable, name in candidates:
            if executable.exists():
                return executable, name

        for command, name in (("chrome", "Google Chrome"), ("msedge", "Microsoft Edge")):
            found = shutil.which(command)
            if found:
                return Path(found), name

        raise FileNotFoundError("No se encontró Google Chrome ni Microsoft Edge instalado.")

    @staticmethod
    def _free_port() -> int:
        with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as sock:
            sock.bind(("127.0.0.1", 0))
            return int(sock.getsockname()[1])

    @staticmethod
    def _wait_for_cdp(port: int, timeout_seconds: float = 20.0) -> None:
        endpoint = f"http://127.0.0.1:{port}/json/version"
        deadline = time.monotonic() + timeout_seconds
        last_error: Exception | None = None
        while time.monotonic() < deadline:
            try:
                with urllib.request.urlopen(endpoint, timeout=1.0) as response:
                    if response.status == 200:
                        return
            except Exception as exc:
                last_error = exc
                time.sleep(0.25)
        raise RuntimeError(f"El navegador abrió, pero el canal local de control no respondió: {last_error}")

    def start(self) -> BrowserContext:
        executable, self.browser_name = self._find_browser()
        port = self._free_port()

        creationflags = 0
        if os.name == "nt":
            creationflags = getattr(subprocess, "CREATE_NEW_PROCESS_GROUP", 0)

        args = [
            str(executable),
            f"--remote-debugging-port={port}",
            f"--user-data-dir={self.profile_dir}",
            "--start-maximized",
            "--no-first-run",
            "--no-default-browser-check",
            "https://classroom.google.com/",
        ]

        self._browser_process = subprocess.Popen(
            args,
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
            creationflags=creationflags,
        )
        self._wait_for_cdp(port)

        self._pw = sync_playwright().start()
        self._browser = self._pw.chromium.connect_over_cdp(f"http://127.0.0.1:{port}")
        if not self._browser.contexts:
            raise RuntimeError("No se encontró el contexto del navegador dedicado.")
        self.context = self._browser.contexts[0]
        return self.context

    def stop(self) -> None:
        if self._browser is not None:
            try:
                self._browser.close()
            except Exception:
                pass
            self._browser = None
        self.context = None

        if self._pw is not None:
            try:
                self._pw.stop()
            except Exception:
                pass
            self._pw = None

        if self._browser_process is not None:
            try:
                if self._browser_process.poll() is None:
                    self._browser_process.terminate()
                    self._browser_process.wait(timeout=5)
            except Exception:
                try:
                    self._browser_process.kill()
                except Exception:
                    pass
            self._browser_process = None

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
                inputs.append(
                    {
                        "tag": locator.evaluate("el => el.tagName.toLowerCase()"),
                        "type": locator.get_attribute("type") or "",
                        "name": locator.get_attribute("name") or "",
                        "aria_label": locator.get_attribute("aria-label") or "",
                        "placeholder": locator.get_attribute("placeholder") or "",
                    }
                )
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
