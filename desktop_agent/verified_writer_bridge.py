from __future__ import annotations

import getpass
import json
import os
import re
import unicodedata
from dataclasses import dataclass
from typing import Any

from roster_guard import require_matching_rosters


@dataclass
class VerifiedPreflight:
    section: str
    period: int
    course_code: str
    id_ambito: int
    class_period_id: int
    root_content_id: int
    previous_period_id: int
    year: str
    student_code: str
    student_name: str
    header_id: int
    header_label: str
    performance_level: int
    current_grade: str
    requested_grade: str
    section_ng: list[dict[str, str]]
    class_name: str
    extra_params: dict[str, Any]
    summary: dict[str, Any]


def _norm(value: Any) -> str:
    text = unicodedata.normalize("NFD", str(value or ""))
    text = "".join(ch for ch in text if unicodedata.category(ch) != "Mn")
    return " ".join(re.sub(r"[^A-Z0-9]+", " ", text.upper()).split())


def _walk_values(value: Any, path: tuple[str, ...] = ()):
    if isinstance(value, dict):
        for key, child in value.items():
            key_s = str(key)
            yield path + (key_s,), child
            yield from _walk_values(child, path + (key_s,))
    elif isinstance(value, list):
        for idx, child in enumerate(value):
            yield from _walk_values(child, path + (str(idx),))


def _decode_storage_value(raw: Any) -> Any:
    if not isinstance(raw, str):
        return raw
    text = raw.strip()
    if text[:1] in {"{", "[", '"'}:
        try:
            return json.loads(text)
        except Exception:
            return raw
    return raw


def _browser_storage(page) -> dict[str, Any]:
    try:
        return page.evaluate(
            """() => {
              const copy = (s) => { const o = {}; for (let i=0;i<s.length;i++){ const k=s.key(i); o[k]=s.getItem(k); } return o; };
              return {local: copy(localStorage), session: copy(sessionStorage)};
            }"""
        ) or {}
    except Exception:
        return {}


def _find_browser_token_and_user(page) -> tuple[str, str]:
    storage = _browser_storage(page)
    expanded: dict[str, Any] = {}
    for scope, rows in (storage or {}).items():
        if not isinstance(rows, dict):
            continue
        expanded[scope] = {key: _decode_storage_value(value) for key, value in rows.items()}

    token_candidates: list[tuple[int, str]] = []
    user_candidates: list[tuple[int, str]] = []
    for path, value in _walk_values(expanded):
        if value in (None, "", [], {}):
            continue
        key = _norm(path[-1] if path else "").replace(" ", "")
        path_text = _norm(" ".join(path)).replace(" ", "")
        if isinstance(value, str):
            text = value.strip().strip('"')
            if text.startswith("eyJ") and text.count(".") >= 2:
                score = 20
                if key in {"TOKEN", "SIETOKEN", "AUTHTOKEN", "ACCESSTOKEN"}:
                    score += 100
                elif "TOKEN" in key:
                    score += 40
                if "VIEWER" in key or "REFRESH" in key:
                    score -= 60
                token_candidates.append((score, text))

            if key in {"USUCOD", "USUARIO", "USERCODE", "CODIGOUSUARIO"}:
                clean = text.strip()
                if 2 <= len(clean) <= 80 and "@" not in clean:
                    score = 100 if key == "USUCOD" else 60
                    if "INFOCOLEGIO" in path_text:
                        score += 40
                    user_candidates.append((score, clean.upper()))

    token = max(token_candidates, default=(0, ""), key=lambda x: x[0])[1]
    user = max(user_candidates, default=(0, ""), key=lambda x: x[0])[1]
    return token, user


def _apply_browser_cookies(client, page) -> int:
    count = 0
    try:
        cookies = page.context.cookies(["https://santaritadecasia.sieweb.com.pe"])
    except Exception:
        cookies = []
    for cookie in cookies or []:
        name = str(cookie.get("name") or "")
        value = str(cookie.get("value") or "")
        if not name:
            continue
        kwargs: dict[str, Any] = {"path": str(cookie.get("path") or "/")}
        domain = str(cookie.get("domain") or "").lstrip(".")
        if domain:
            kwargs["domain"] = domain
        try:
            client.session.cookies.set(name, value, **kwargs)
            count += 1
        except Exception:
            pass
    return count


def client_from_browser(page):
    # Import tardío: PyInstaller incluye los módulos raíz, pero el agente no exige
    # credenciales en disco para intentar reutilizar la sesión ya autenticada.
    import sieweb as sieweb_module

    token, user = _find_browser_token_and_user(page)
    if not token or not user:
        return None
    client = sieweb_module.SieWebClient()
    _apply_browser_cookies(client, page)
    client._token = token
    client._user_code = user
    client._logged_in = True
    client._set_authenticated_headers()
    try:
        client._refresh_token_with_cookie()
    except Exception:
        pass
    return client


def client_from_prompt():
    """Fallback en memoria. RC1 nunca escribe usuario/contraseña a un archivo."""
    import config as config_module
    import sieweb as sieweb_module

    print("\nNo pude reutilizar automáticamente la sesión del navegador.")
    print("Puedes autenticar el escritor verificado solo para esta ejecución.")
    user = input("Usuario SIEweb: ").strip()
    password = getpass.getpass("Contraseña SIEweb (no se mostrará ni se guardará): ")
    if not user or not password:
        raise RuntimeError("Autenticación cancelada; no se escribió nada.")
    os.environ["SIEWEB_USER"] = user
    os.environ["SIEWEB_PASSWORD"] = password
    fresh = config_module.Settings()
    config_module.settings = fresh
    sieweb_module.settings = fresh
    client = sieweb_module.SieWebClient()
    client.login()
    return client


def get_verified_client(page, *, id_ambito: int):
    client = client_from_browser(page)
    if client is not None:
        try:
            # Una lectura mínima confirma que token/cookies/usuario forman una sesión válida.
            client.list_classes(id_ambito=id_ambito)
            return client, "browser-session"
        except Exception:
            pass
    client = client_from_prompt()
    client.list_classes(id_ambito=id_ambito)
    return client, "temporary-login"


def _criterion_family(value: Any) -> str:
    t = _norm(value)
    if "CANTIDAD" in t:
        return "cantidad"
    if "REGULARIDAD" in t and "EQUIVALENCIA" in t:
        return "regularidad"
    if "MOVIMIENTO" in t and ("FORMA" in t or "LOCALIZA" in t):
        return "forma"
    if "GESTION" in t and "DATOS" in t:
        return "datos"
    return ""


def _criterion_texts(row: dict[str, Any]) -> list[str]:
    values = []
    for key in ("desc", "descripcion", "abreviatura"):
        text = str(row.get(key) or "").strip()
        if text and text not in values:
            values.append(text)
    return values


def resolve_criterion(summary: dict[str, Any], visible_label: str) -> dict[str, Any]:
    criteria = [row for row in (summary.get("criteria") or []) if isinstance(row, dict)]
    wanted = _norm(visible_label)
    exact = [row for row in criteria if wanted and any(_norm(text) == wanted for text in _criterion_texts(row))]
    if len(exact) == 1:
        return exact[0]

    family = _criterion_family(visible_label)
    if family:
        family_rows = [
            row for row in criteria
            if any(_criterion_family(text) == family for text in _criterion_texts(row))
        ]
        # La grilla principal observada muestra Competencias nivelEva=1. Se prefiere
        # esa identidad y solo se acepta si queda una única cabecera.
        top = [
            row for row in family_rows
            if int(row.get("nivelEva") or 0) == 1
            and _norm(row.get("programa")) == "COMPETENCIA"
        ]
        if len(top) == 1:
            return top[0]
        if len(family_rows) == 1:
            return family_rows[0]

    raise RuntimeError(
        "PROTECCIÓN DE CABECERA: el encabezado visible no pudo asociarse a una única cabecera SIEweb. "
        f"Etiqueta visible: {visible_label!r}; coincidencias exactas={len(exact)}."
    )


def _current_grade(client, student: dict[str, Any], header_id: int) -> str:
    note = client._note_object_for_header(student, header_id)
    if not note:
        return ""
    fields = client._grade_field_values(note)
    for value in fields.values():
        normalized = client._normalize_grade_value(value)
        if normalized:
            return normalized
    return ""


def prepare_single_cell(
    *,
    client,
    browser_codes: list[str],
    page_context,
    student_code: str,
    visible_column_label: str,
    requested_grade: str,
) -> VerifiedPreflight:
    if page_context.id_ambito is None:
        raise RuntimeError(
            "PROTECCIÓN DE CONTEXTO: no se pudo resolver idAmbito de esta sección desde el navegador. "
            "No se habilitará escritura."
        )
    desired = str(requested_grade or "").strip().upper()
    if desired not in {"A", "B", "C"}:
        raise RuntimeError("RC1 solo permite una nota cualitativa A, B o C.")

    ctx = client.resolve_class_context(
        section=page_context.section,
        period=page_context.period,
        course_code=page_context.course_code,
        id_ambito=int(page_context.id_ambito),
    )
    extra = {"idPeriodoAnt": int(ctx.get("idPeriodoAnt") or 0)}
    summary = client.get_gradebook_summary(
        class_period_id=int(ctx["idClasePeriodo"]),
        root_content_id=int(ctx["idContenido"]),
        extra_params=extra,
    )
    class_info = summary.get("class") or {}
    year = str(class_info.get("ano") or "").strip()
    if year != "2026":
        raise RuntimeError(f"PROTECCIÓN DE AÑO: la libreta API indicó {year!r}; RC1 está autorizado para 2026.")

    api_codes = [str(row.get("alucod") or "").strip() for row in (summary.get("students") or [])]
    require_matching_rosters(page_context.section, browser_codes=browser_codes, api_codes=api_codes)

    matches = client._students_matching_code(summary, student_code)
    if len(matches) != 1:
        raise RuntimeError(
            f"PROTECCIÓN DE ALUMNO: código {student_code} produjo {len(matches)} coincidencias en SIEweb."
        )
    student = matches[0]
    criterion = resolve_criterion(summary, visible_column_label)
    header_id = int(criterion.get("id") or 0)
    if header_id <= 0:
        raise RuntimeError("PROTECCIÓN DE CABECERA: SIEweb no devolvió un ID de cabecera válido.")
    level = int(criterion.get("nivelEva") or 0)
    if level not in {1, 3}:
        raise RuntimeError(
            f"PROTECCIÓN DE NIVEL: la cabecera {header_id} tiene nivelEva={level}; RC1 solo admite 1 o 3."
        )

    current = _current_grade(client, student, header_id)
    section_ng = client.resolve_grade_write_scope(summary, None)
    class_name = str(class_info.get("nomSalon") or page_context.section)
    return VerifiedPreflight(
        section=page_context.section,
        period=int(ctx["periodo"]),
        course_code=page_context.course_code,
        id_ambito=int(page_context.id_ambito),
        class_period_id=int(ctx["idClasePeriodo"]),
        root_content_id=int(ctx["idContenido"]),
        previous_period_id=int(ctx.get("idPeriodoAnt") or 0),
        year=year,
        student_code=str(student.get("alucod") or student_code).strip(),
        student_name=str(student.get("nomcomp") or "").strip(),
        header_id=header_id,
        header_label=str(criterion.get("desc") or criterion.get("descripcion") or visible_column_label).strip(),
        performance_level=level,
        current_grade=current,
        requested_grade=desired,
        section_ng=section_ng,
        class_name=class_name,
        extra_params=extra,
        summary=summary,
    )


def execute_single_cell(client, preflight: VerifiedPreflight) -> dict[str, Any]:
    # Si ya está correcta, no se hace PUT: la relectura actual ya constituye el estado observado.
    if client._normalize_grade_value(preflight.current_grade) == client._normalize_grade_value(preflight.requested_grade):
        return {
            "saved": False,
            "already_correct": True,
            "verification": {"ok": True, "verified_count": 1, "requested_count": 1},
            "mode": "no-write-already-correct",
        }

    kwargs = dict(
        year=preflight.year,
        course_code=preflight.course_code,
        class_period_id=preflight.class_period_id,
        root_content_id=preflight.root_content_id,
        period=preflight.period,
        section_ng=preflight.section_ng,
        header_id=preflight.header_id,
        grades_by_student_code={preflight.student_code: preflight.requested_grade},
        class_name=preflight.class_name,
        extra_params=preflight.extra_params,
        notify=False,
        verification_attempts=3,
    )
    if preflight.performance_level == 1:
        kwargs.update(
            protect_achievement_level=False,
            performance_level=1,
            allow_achievement_level=True,
        )
    else:
        kwargs.update(
            protect_achievement_level=True,
            performance_level=3,
            allow_achievement_level=False,
        )
    result = client.save_grades_verified(**kwargs)
    verification = result.get("verification") or {}
    if verification.get("ok") is not True or int(verification.get("verified_count") or 0) != 1:
        raise RuntimeError("NO VERIFICADO: SIEweb no confirmó la única celda solicitada tras la relectura.")
    if preflight.performance_level == 1:
        non_target = result.get("non_target_verification") or {}
        if non_target.get("checked") is not True or non_target.get("ok") is not True:
            raise RuntimeError("NO VERIFICADO: la protección de celdas no objetivo no quedó confirmada.")
    return result
