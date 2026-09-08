from __future__ import annotations

import json
import re
import unicodedata
from dataclasses import asdict, dataclass
from urllib.parse import parse_qs, urlsplit

from playwright.sync_api import Page


# Solo IDs ya confirmados por el código/historial del proyecto. S2B NO se adivina.
KNOWN_SAFE_ID_AMBITO = {"S2A": 518, "S5A": 524, "S5B": 525}


@dataclass(frozen=True)
class PageAcademicContext:
    section: str
    period: int
    course_code: str
    course_name: str
    id_ambito: int | None
    id_ambito_source: str
    page_url: str

    def as_dict(self) -> dict:
        return asdict(self)


def _norm(value: str) -> str:
    text = unicodedata.normalize("NFD", str(value or ""))
    text = "".join(ch for ch in text if unicodedata.category(ch) != "Mn")
    return " ".join(text.upper().split())


def _body_text(page: Page) -> str:
    try:
        return str(page.locator("body").inner_text(timeout=3000) or "")
    except Exception:
        return ""


def detect_section(text: str) -> str:
    hay = _norm(text)
    tests = [
        ("S2A", (r"SECUNDARIA SEGUNDO GRADO\s*[\"']?A[\"']?\s*\|+\s*S2A", r"\bS2A\b")),
        ("S2B", (r"SECUNDARIA SEGUNDO GRADO\s*[\"']?B[\"']?\s*\|+\s*S2B", r"\bS2B\b")),
        ("S5A", (r"SECUNDARIA QUINTO GRADO\s*[\"']?A[\"']?\s*\|+\s*S5A", r"\bS5A\b")),
        ("S5B", (r"SECUNDARIA QUINTO GRADO\s*[\"']?B[\"']?\s*\|+\s*S5B", r"\bS5B\b")),
    ]
    found = [key for key, patterns in tests if any(re.search(pat, hay) for pat in patterns)]
    found = list(dict.fromkeys(found))
    if len(found) != 1:
        raise RuntimeError(
            "No pude identificar una única sección 2A/2B/5A/5B en la pantalla. "
            f"Detectadas: {found or 'ninguna'}."
        )
    return found[0]


def detect_period(text: str) -> int:
    hay = _norm(text)
    matches = [int(x) for x in re.findall(r"\b([1-4])\s*(?:ER|DO|RO|TO)?\s*PERIODO\b", hay)]
    matches = list(dict.fromkeys(matches))
    if len(matches) != 1:
        raise RuntimeError(f"No pude identificar un único período en SIEweb. Detectados: {matches or 'ninguno'}.")
    return matches[0]


def detect_course(text: str) -> tuple[str, str]:
    hay = _norm(text)
    match = re.search(r"\b(\d{2})\s*-\s*MATEMATICA\b", hay)
    if not match:
        raise RuntimeError("La pantalla no muestra un curso de Matemática con código visible.")
    code = match.group(1)
    if code != "05":
        raise RuntimeError(f"PROTECCIÓN DE CURSO: se esperaba 05 - Matemática y se detectó {code}.")
    return code, "Matemática"


def _resource_urls(page: Page) -> list[str]:
    try:
        result = page.evaluate(
            """() => performance.getEntriesByType('resource').map(e => String(e.name || ''))"""
        )
        return [str(item) for item in (result or []) if item]
    except Exception:
        return []


def _id_ambito_from_url(url: str) -> int | None:
    if "HyoClase/obtListar" not in url:
        return None
    try:
        query = parse_qs(urlsplit(url).query)
    except Exception:
        return None
    raw_values = query.get("params") or query.get("Params") or []
    for raw in raw_values:
        try:
            obj = json.loads(raw)
        except Exception:
            continue
        if not isinstance(obj, dict):
            continue
        for key in ("id_ambito", "idAmbito", "ID_AMBITO"):
            if obj.get(key) not in (None, ""):
                try:
                    value = int(obj[key])
                except (TypeError, ValueError):
                    continue
                if value > 0:
                    return value
    return None


def detect_id_ambito(page: Page, section: str) -> tuple[int | None, str]:
    # Se recorre al revés: el último obtListar suele corresponder al selector activo.
    for url in reversed(_resource_urls(page)):
        value = _id_ambito_from_url(url)
        if value is None:
            continue
        known = KNOWN_SAFE_ID_AMBITO.get(section)
        if known is not None and value != known:
            raise RuntimeError(
                f"PROTECCIÓN DE CONTEXTO: la red indicó idAmbito={value} para {section}, "
                f"pero el valor previamente validado es {known}. No se habilitará escritura."
            )
        return value, "browser-network"

    known = KNOWN_SAFE_ID_AMBITO.get(section)
    if known is not None:
        return known, "validated-project-mapping"
    return None, "unresolved"


def detect_academic_context(page: Page) -> PageAcademicContext:
    url = str(page.url or "")
    if "santaritadecasia.sieweb.com.pe" not in url or "/registroNotas" not in url:
        raise RuntimeError("Abre SIEweb > Registro de Notas antes de continuar.")
    text = _body_text(page)
    section = detect_section(text)
    period = detect_period(text)
    course_code, course_name = detect_course(text)
    id_ambito, source = detect_id_ambito(page, section)
    return PageAcademicContext(
        section=section,
        period=period,
        course_code=course_code,
        course_name=course_name,
        id_ambito=id_ambito,
        id_ambito_source=source,
        page_url=url,
    )
