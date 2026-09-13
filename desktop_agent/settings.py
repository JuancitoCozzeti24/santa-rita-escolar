from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
import os


@dataclass(frozen=True)
class DesktopSettings:
    data_dir: Path
    classroom_url: str
    cieweb_url: str
    model: str
    openai_api_key: str
    backend_url: str = ""
    backend_secret: str = ""
    headless: bool = False

    @classmethod
    def from_env(cls) -> "DesktopSettings":
        data_dir = Path(os.getenv("SIEROOM_DESKTOP_DATA", ".sieroom")).resolve()
        return cls(
            data_dir=data_dir,
            classroom_url=os.getenv("SIEROOM_CLASSROOM_URL", "https://classroom.google.com/"),
            cieweb_url=os.getenv("SIEROOM_CIEWEB_URL", "https://www.sieweb.com.pe/"),
            model=os.getenv("SIEROOM_VISION_MODEL", "gpt-5.1"),
            openai_api_key=os.getenv("OPENAI_API_KEY", ""),
            backend_url=os.getenv("SIEROOM_BACKEND_URL", "").rstrip("/"),
            backend_secret=os.getenv("SIEROOM_BACKEND_SECRET", ""),
            headless=os.getenv("SIEROOM_HEADLESS", "0").strip() == "1",
        )
