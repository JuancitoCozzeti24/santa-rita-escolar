from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class Observation:
    url: str
    title: str
    screenshot_b64: str
    viewport: dict[str, int]
