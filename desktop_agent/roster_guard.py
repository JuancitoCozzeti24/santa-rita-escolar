from __future__ import annotations

from dataclasses import dataclass
from typing import Iterable


# Lista de códigos entregada expresamente por el docente para 2026.
# Se conservan solo códigos + sección para minimizar datos personales en el agente.
AUTHORITATIVE_CODES_2026: dict[str, tuple[str, ...]] = {
    "S2A": (
        "20220055", "20170002", "20180001", "20170005", "20170081", "20170008",
        "20180026", "20170010", "20180066", "20170011", "20260059", "20180034",
        "20170014", "20170015", "20170016", "20160076", "20180053", "20180052",
        "20210067", "20180042", "20170021", "20260061", "20200082", "20180043",
        "20220050", "20170024", "20180022", "20170083",
    ),
    "S2B": (
        "20180002", "20170080", "20170006", "20170009", "20170082", "20180031",
        "20180032", "20180035", "20180036", "20170017", "20170018", "20180037",
        "20180038", "20230060", "20180024", "20180039", "20180069", "20170022",
        "20180044", "20170023", "20180045", "20170025", "20180058", "20180046",
        "20180054", "20180059", "20250047", "20180050",
    ),
    "S5A": (
        "20200091", "20150004", "20140025", "20150007", "20140022", "20150010",
        "20150013", "20150015", "20140019", "20150019", "20150064", "20140016",
        "20150042", "20140013", "20160050", "20150020", "20150023", "20150040",
        "20150027", "20220059", "20150029", "20150031", "20140009", "20140007",
        "20150037",
    ),
    "S5B": (
        "20150001", "20150002", "20200092", "20150003", "20150048", "20150006",
        "20150009", "20150062", "20150047", "20140021", "20150046", "20140017",
        "20150044", "20140014", "20150043", "20150041", "20240051", "20150030",
        "20150068", "20140008", "20150034", "20140005", "20150039", "20140001",
        "20150035", "20150036",
    ),
}

EXPECTED_COUNTS_2026 = {key: len(value) for key, value in AUTHORITATIVE_CODES_2026.items()}


@dataclass(frozen=True)
class RosterCheck:
    section: str
    expected_count: int
    observed_count: int
    ok: bool
    missing: tuple[str, ...]
    unexpected: tuple[str, ...]
    duplicates: tuple[str, ...]

    def summary(self) -> str:
        if self.ok:
            return f"{self.observed_count}/{self.expected_count} alumnos verificados"
        parts = [f"{self.observed_count}/{self.expected_count} alumnos"]
        if self.missing:
            parts.append(f"faltan {len(self.missing)}")
        if self.unexpected:
            parts.append(f"sobran {len(self.unexpected)}")
        if self.duplicates:
            parts.append(f"duplicados {len(self.duplicates)}")
        return "; ".join(parts)


def normalize_section(value: str) -> str:
    text = "".join(ch for ch in str(value or "").upper() if ch.isalnum())
    aliases = {
        "2A": "S2A", "S2A": "S2A", "2B": "S2B", "S2B": "S2B",
        "5A": "S5A", "S5A": "S5A", "5B": "S5B", "S5B": "S5B",
    }
    return aliases.get(text, text)


def authoritative_codes(section: str) -> tuple[str, ...]:
    key = normalize_section(section)
    if key not in AUTHORITATIVE_CODES_2026:
        raise ValueError(f"Sección no autorizada para RC1: {section!r}")
    return AUTHORITATIVE_CODES_2026[key]


def validate_roster(section: str, observed_codes: Iterable[str]) -> RosterCheck:
    key = normalize_section(section)
    expected = authoritative_codes(key)
    raw = [str(code or "").strip() for code in observed_codes if str(code or "").strip()]
    seen: set[str] = set()
    duplicates: list[str] = []
    for code in raw:
        if code in seen and code not in duplicates:
            duplicates.append(code)
        seen.add(code)

    expected_set = set(expected)
    observed_set = set(raw)
    missing = tuple(sorted(expected_set - observed_set))
    unexpected = tuple(sorted(observed_set - expected_set))
    ok = not missing and not unexpected and not duplicates and len(raw) == len(expected)
    return RosterCheck(
        section=key,
        expected_count=len(expected),
        observed_count=len(raw),
        ok=ok,
        missing=missing,
        unexpected=unexpected,
        duplicates=tuple(sorted(duplicates)),
    )


def require_matching_rosters(section: str, *, browser_codes: Iterable[str], api_codes: Iterable[str]) -> tuple[RosterCheck, RosterCheck]:
    browser = validate_roster(section, browser_codes)
    api = validate_roster(section, api_codes)
    if not browser.ok or not api.ok:
        details = []
        if not browser.ok:
            details.append("navegador=" + browser.summary())
        if not api.ok:
            details.append("API=" + api.summary())
        raise RuntimeError(
            "PROTECCIÓN DE NÓMINA: la sección observada no coincide exactamente con la lista autorizada 2026. "
            + " | ".join(details)
        )
    if set(str(x).strip() for x in browser_codes) != set(str(x).strip() for x in api_codes):
        raise RuntimeError("PROTECCIÓN DE NÓMINA: navegador y SIEweb API no contienen los mismos códigos.")
    return browser, api
