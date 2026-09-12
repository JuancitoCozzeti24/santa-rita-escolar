from __future__ import annotations

import base64
import difflib
import json
import re
from dataclasses import dataclass
from typing import Any

from playwright.sync_api import Page

from sieweb import SieWebClient, SieWebError


_ALLOWED_GRADES = {"A", "B", "C"}
_JWT_RE = re.compile(r"eyJ[A-Za-z0-9_-]+\.[A-Za-z0-9_-]+\.[A-Za-z0-9_-]*")


class VerifiedWriterBridgeError(RuntimeError):
    pass


def _clean(value: Any) -> str:
    return " ".join(str(value or "").split())


def _decode_jsonish(value: Any) -> Any:
    if not isinstance(value, str):
        return value
    raw = value.strip()
    if not raw or raw[:1] not in {"{", "[", '"'}:
        return value
    try:
        return json.loads(raw)
    except Exception:
        return value


def _walk_values(value: Any, path: str = ""):
    decoded = _decode_jsonish(value)
    if decoded is not value:
        yield from _walk_values(decoded, path)
        return
    if isinstance(value, dict):
        for key, item in value.items():
            child = f"{path}.{key}" if path else str(key)
            yield child, item
            yield from _walk_values(item, child)
    elif isinstance(value, list):
        for index, item in enumerate(value):
            child = f"{path}[{index}]"
            yield child, item
            yield from _walk_values(item, child)


def _jwt_payload(token: str) -> dict[str, Any]:
    try:
        part = token.split(".", 2)[1]
        part += "=" * (-len(part) % 4)
        raw = base64.urlsafe_b64decode(part.encode("ascii"))
        obj = json.loads(raw.decode("utf-8", errors="replace"))
        return obj if isinstance(obj, dict) else {}
    except Exception:
        return {}


def _extract_browser_auth(page: Page) -> dict[str, Any]:
    """Lee la sesión ya autenticada sin persistir ni imprimir secretos."""
    state = page.context.storage_state()
    cookies = [
        c for c in (state.get("cookies") or [])
        if "sieweb.com.pe" in str(c.get("domain") or "").lower()
    ]

    local_items: dict[str, Any] = {}
    for origin in state.get("origins") or []:
        if "sieweb.com.pe" not in str(origin.get("origin") or "").lower():
            continue
        for item in origin.get("localStorage") or []:
            local_items[str(item.get("name") or "")] = item.get("value")

    try:
        session_items = page.evaluate(
            "() => Object.fromEntries(Array.from({length: sessionStorage.length}, (_,i) => {const k=sessionStorage.key(i); return [k, sessionStorage.getItem(k)];}))"
        )
        if not isinstance(session_items, dict):
            session_items = {}
    except Exception:
        session_items = {}

    sources: dict[str, Any] = {
        "localStorage": local_items,
        "sessionStorage": session_items,
        "cookies": {str(c.get("name") or ""): c.get("value") for c in cookies},
    }

    candidates: list[tuple[int, str, str, dict[str, Any]]] = []
    for path, value in _walk_values(sources):
        if not isinstance(value, str):
            continue
        for match in _JWT_RE.findall(value):
            p = path.lower()
            score = 0
            if "sie" in p and "token" in p:
                score += 50
            if p.endswith("token") or ".token" in p:
                score += 35
            if "authorization" in p or "accesstoken" in p or "access_token" in p:
                score += 25
            if "viewer" in p:
                score -= 10
            if "refresh" in p:
                score -= 40
            payload = _jwt_payload(match)
            if payload:
                score += 10
                keys = {str(k).lower() for k in payload}
                if keys & {"usucod", "usuario", "user", "username", "sub"}:
                    score += 8
            candidates.append((score, path, match, payload))

    candidates.sort(key=lambda x: x[0], reverse=True)
    token = candidates[0][2] if candidates else ""
    token_payload = candidates[0][3] if candidates else {}

    def find_user_code(value: Any) -> str:
        wanted = {
            "usucod", "usu_cod", "codigo_usuario", "codigousuario",
            "usuario", "username", "usercode", "user_code",
        }
        for path, item in _walk_values(value):
            key = re.split(r"[.\[]", path.lower())[-1].rstrip("]")
            if key not in wanted or item in (None, ""):
                continue
            text = str(item).strip()
            if text and len(text) <= 80 and not text.startswith("eyJ"):
                return text.upper()
        return ""

    user_code = find_user_code(token_payload) or find_user_code(sources)

    return {
        "cookies": cookies,
        "token": token,
        "user_code": user_code,
        "has_cookie": bool(cookies),
        "has_token": bool(token),
        "has_user_code": bool(user_code),
    }


def _hydrate_client_from_browser(page: Page) -> tuple[SieWebClient, dict[str, bool]]:
    auth = _extract_browser_auth(page)
    client = SieWebClient()
    client.session.cookies.clear()
    for cookie in auth["cookies"]:
        name = str(cookie.get("name") or "")
        value = str(cookie.get("value") or "")
        if not name:
            continue
        kwargs: dict[str, Any] = {"path": str(cookie.get("path") or "/")}
        domain = str(cookie.get("domain") or "").strip()
        if domain:
            kwargs["domain"] = domain
        client.session.cookies.set(name, value, **kwargs)

    client._token = str(auth.get("token") or "")
    if auth.get("user_code"):
        client._user_code = str(auth["user_code"]).upper()
    client._logged_in = True
    client._set_authenticated_headers()

    return client, {
        "browser_cookie_present": bool(auth.get("has_cookie")),
        "browser_token_present": bool(auth.get("has_token")),
        "browser_user_code_present": bool(auth.get("has_user_code")),
    }


def infer_browser_context(page: Page) -> dict[str, Any]:
    try:
        data = page.evaluate(
            r"""
            () => {
              const clean = v => String(v ?? '').replace(/\s+/g,' ').trim();
              const visible = el => {
                if (!el || !(el instanceof Element)) return false;
                const s=getComputedStyle(el), r=el.getBoundingClientRect();
                return s.display!=='none' && s.visibility!=='hidden' && r.width>0 && r.height>0;
              };
              const fields = Array.from(document.querySelectorAll('.q-field'))
                .filter(visible).map(el => clean(el.innerText || el.textContent)).filter(Boolean).slice(0,20);
              return {url: location.href, title: document.title, fields, body: clean(document.body.innerText).slice(0,8000)};
            }
            """
        )
    except Exception as exc:
        raise VerifiedWriterBridgeError(f"No se pudo leer el contexto visible de SIEweb: {exc}") from exc

    hay = " | ".join([*(data.get("fields") or []), str(data.get("body") or "")])
    upper = hay.upper()

    section = ""
    for pattern in (
        r"\|\|\s*(S[1-6][A-Z])\b",
        r"\b(S[1-6][A-Z])\b",
    ):
        m = re.search(pattern, upper)
        if m:
            section = m.group(1)
            break

    course_code = ""
    m = re.search(r"\b(\d{2})\s*-\s*MAT[ÉE]M", upper)
    if m:
        course_code = m.group(1)

    period = 0
    m = re.search(r"\b([1-4])\s*PERIODO\b", upper)
    if m:
        period = int(m.group(1))

    year = ""
    years = re.findall(r"\b20\d{2}\b", upper)
    if years:
        year = years[-1]

    if "sieweb.com.pe" not in str(data.get("url") or "").lower() or "registronotas" not in str(data.get("url") or "").lower():
        raise VerifiedWriterBridgeError("La pestaña activa no es Registro de Notas de SIEweb.")
    if not section or not course_code or period <= 0 or not year:
        raise VerifiedWriterBridgeError(
            "No se pudo resolver de forma inequívoca sección, curso, período y año desde la pantalla actual."
        )
    return {
        "section": section,
        "course_code": course_code,
        "period": period,
        "year": year,
        "url": str(data.get("url") or ""),
    }


def _criterion_text(item: dict[str, Any]) -> str:
    return _clean(
        item.get("descripcion") or item.get("desc") or item.get("abreviatura")
        or item.get("description") or item.get("nombre") or ""
    )


def _match_criterion(client: SieWebClient, summary: dict[str, Any], label: str) -> dict[str, Any]:
    wanted = client._canon_text(label)
    candidates: list[tuple[float, dict[str, Any], str]] = []
    for item in summary.get("criteria") or []:
        if not isinstance(item, dict):
            continue
        level = item.get("nivelEva")
        if str(level) not in {"1", "3"}:
            continue
        text = _criterion_text(item)
        canon = client._canon_text(text)
        if not canon:
            continue
        if canon == wanted:
            score = 1.0
        elif canon.startswith(wanted) or wanted.startswith(canon):
            score = 0.94 if min(len(canon), len(wanted)) >= 12 else 0.70
        else:
            score = difflib.SequenceMatcher(None, wanted, canon).ratio()
        candidates.append((score, item, text))

    if not candidates:
        raise VerifiedWriterBridgeError("La API de SIEweb no devolvió un criterio compatible con la columna visible.")
    candidates.sort(key=lambda x: x[0], reverse=True)
    best = candidates[0]
    second = candidates[1][0] if len(candidates) > 1 else 0.0
    if best[0] < 0.82 or (best[0] < 0.999 and best[0] - second < 0.08):
        raise VerifiedWriterBridgeError(
            "La competencia visible no pudo asociarse de forma única a una cabecera API. Escritura bloqueada."
        )
    item = dict(best[1])
    item["_match_score"] = round(best[0], 4)
    item["_matched_text"] = best[2]
    return item


def _note_grade(note: Any) -> str:
    if not isinstance(note, dict):
        return ""
    lower = {str(k).lower(): v for k, v in note.items()}
    value = lower.get("notareg")
    if value in (None, ""):
        value = lower.get("notaini")
    return str(value or "").strip().upper()


def _student_grade(summary: dict[str, Any], code: str, header_id: int) -> str:
    matches = [
        s for s in (summary.get("students") or [])
        if str(s.get("alucod") or "").strip() == str(code).strip()
    ]
    if len(matches) != 1:
        raise VerifiedWriterBridgeError(
            f"El alumno {code} no aparece exactamente una vez en la relectura API de SIEweb."
        )
    notes = matches[0].get("notas") or {}
    if not isinstance(notes, dict):
        return ""
    note = notes.get(str(header_id))
    if note is None:
        note = notes.get(header_id)
    if note is None:
        for key, candidate in notes.items():
            if not isinstance(candidate, dict):
                continue
            low = {str(k).lower(): v for k, v in candidate.items()}
            hid = low.get("idcabecera", key)
            if str(hid) == str(header_id):
                note = candidate
                break
    return _note_grade(note)


def _grade_snapshot(summary: dict[str, Any]) -> dict[str, str]:
    snap: dict[str, str] = {}
    for student in summary.get("students") or []:
        code = str(student.get("alucod") or "").strip()
        if not code:
            continue
        notes = student.get("notas") or {}
        if not isinstance(notes, dict):
            continue
        for key, note in notes.items():
            if not isinstance(note, dict):
                continue
            low = {str(k).lower(): v for k, v in note.items()}
            header = low.get("idcabecera", key)
            snap[f"{code}:{header}"] = _note_grade(note)
    return snap


@dataclass
class PreparedWrite:
    client: SieWebClient
    browser_context: dict[str, Any]
    api_context: dict[str, Any]
    before: dict[str, Any]
    before_snapshot: dict[str, str]
    auth_status: dict[str, bool]
    student_code: str
    student_name: str
    column_number: int
    column_label: str
    header_id: int
    criterion_level: int
    criterion_text: str
    criterion_match_score: float
    dom_current: str
    api_current: str
    proposed: str

    @property
    def target_kind(self) -> str:
        return "NIVEL DE LOGRO" if self.criterion_level == 1 else "DESEMPEÑO"

    @property
    def confirmation_phrase(self) -> str:
        return "ESCRIBIR NIVEL DE LOGRO" if self.criterion_level == 1 else "ESCRIBIR DESEMPEÑO"

    def public_dict(self) -> dict[str, Any]:
        return {
            "browser_context": self.browser_context,
            "api_context": {
                "section": self.api_context.get("section"),
                "idAmbito": self.api_context.get("idAmbito"),
                "idClase": self.api_context.get("idClase"),
                "idClasePeriodo": self.api_context.get("idClasePeriodo"),
                "idContenido": self.api_context.get("idContenido"),
                "periodo": self.api_context.get("periodo"),
                "idPeriodoAnt": self.api_context.get("idPeriodoAnt"),
            },
            "auth_status": self.auth_status,
            "target": {
                "student_code": self.student_code,
                "student_name": self.student_name,
                "column": self.column_number,
                "column_label": self.column_label,
                "header_id": self.header_id,
                "criterion_level": self.criterion_level,
                "target_kind": self.target_kind,
                "criterion_text": self.criterion_text,
                "criterion_match_score": self.criterion_match_score,
                "dom_current": self.dom_current,
                "api_current": self.api_current,
                "proposed": self.proposed,
            },
        }


def prepare_one_cell_write(
    page: Page,
    *,
    dom_student_codes: list[str],
    student_code: str,
    student_name: str,
    column_number: int,
    column_label: str,
    dom_current: str,
    proposed: str,
) -> PreparedWrite:
    proposed = str(proposed or "").strip().upper()
    dom_current = str(dom_current or "").strip().upper()
    if proposed not in _ALLOWED_GRADES:
        raise VerifiedWriterBridgeError("RC4 solo admite A, B o C.")
    if dom_current not in {"", "A", "B", "C"}:
        raise VerifiedWriterBridgeError("El valor DOM actual no es una calificación confiable.")

    browser_context = infer_browser_context(page)
    client, auth_status = _hydrate_client_from_browser(page)

    try:
        api_context = client.resolve_class_context(
            section=browser_context["section"],
            period=int(browser_context["period"]),
            course_code=str(browser_context["course_code"]),
        )
        extra = {"idPeriodoAnt": int(api_context.get("idPeriodoAnt") or 0)}
        before = client.get_gradebook_summary(
            class_period_id=int(api_context["idClasePeriodo"]),
            root_content_id=int(api_context["idContenido"]),
            extra_params=extra,
        )
    except Exception as exc:
        raise VerifiedWriterBridgeError(
            "No se pudo autenticar/releer la libreta mediante el writer verificado usando la sesión del navegador. "
            f"No se escribió nada. Detalle: {exc}"
        ) from exc

    dom_codes = {str(x).strip() for x in dom_student_codes if str(x).strip()}
    api_codes = {
        str(s.get("alucod") or "").strip()
        for s in (before.get("students") or [])
        if str(s.get("alucod") or "").strip()
    }
    if not dom_codes or dom_codes != api_codes:
        raise VerifiedWriterBridgeError(
            f"La matrícula DOM/API no coincide (DOM={len(dom_codes)}, API={len(api_codes)}). No se escribió nada."
        )
    if student_code not in api_codes:
        raise VerifiedWriterBridgeError("El alumno objetivo no existe en la matrícula API revalidada.")

    criterion = _match_criterion(client, before, column_label)
    try:
        header_id = int(criterion.get("id"))
        level = int(criterion.get("nivelEva"))
    except Exception as exc:
        raise VerifiedWriterBridgeError("La cabecera API objetivo no expone id/nivelEva válidos.") from exc
    if level not in {1, 3}:
        raise VerifiedWriterBridgeError(f"RC4 bloquea nivelEva={level}; solo admite 1 o 3.")

    api_current = _student_grade(before, student_code, header_id)
    if api_current not in {"", "A", "B", "C"}:
        raise VerifiedWriterBridgeError(
            f"La API devolvió un valor actual no admitido ({api_current!r}). Escritura bloqueada."
        )
    if api_current != dom_current:
        raise VerifiedWriterBridgeError(
            f"DOM y API discrepan sobre la celda objetivo (DOM={dom_current or '(vacío)'}, API={api_current or '(vacío)'}). No se escribió nada."
        )

    # RC4 es deliberadamente conservadora: no reemplaza una nota distinta.
    if api_current and api_current != proposed:
        raise VerifiedWriterBridgeError(
            f"RC4 no sobrescribe una nota existente ({api_current} -> {proposed}). Solo permite celda vacía o valor ya idéntico."
        )

    return PreparedWrite(
        client=client,
        browser_context=browser_context,
        api_context=api_context,
        before=before,
        before_snapshot=_grade_snapshot(before),
        auth_status=auth_status,
        student_code=student_code,
        student_name=student_name,
        column_number=int(column_number),
        column_label=column_label,
        header_id=header_id,
        criterion_level=level,
        criterion_text=str(criterion.get("_matched_text") or _criterion_text(criterion)),
        criterion_match_score=float(criterion.get("_match_score") or 0.0),
        dom_current=dom_current,
        api_current=api_current,
        proposed=proposed,
    )


def execute_one_cell_verified(prepared: PreparedWrite) -> dict[str, Any]:
    client = prepared.client
    ctx = prepared.api_context
    extra = {"idPeriodoAnt": int(ctx.get("idPeriodoAnt") or 0)}

    if prepared.api_current == prepared.proposed:
        after = client.get_gradebook_summary(
            class_period_id=int(ctx["idClasePeriodo"]),
            root_content_id=int(ctx["idContenido"]),
            extra_params=extra,
        )
        observed = _student_grade(after, prepared.student_code, prepared.header_id)
        return {
            "verified": observed == prepared.proposed,
            "write_sent": False,
            "already_present": True,
            "observed": observed,
            "unexpected_grade_changes": [],
            "writer_mode": "no-op-already-present",
        }

    class_info = prepared.before.get("class") or {}
    scope = class_info.get("arrNivelGrado") or class_info.get("objNG")
    class_name = str(
        ctx.get("course", {}).get("NOMCLASE")
        or ctx.get("course", {}).get("NOMBRE")
        or ctx.get("section")
        or ""
    )

    kwargs: dict[str, Any] = {
        "year": str(prepared.browser_context["year"]),
        "course_code": str(prepared.browser_context["course_code"]),
        "class_period_id": int(ctx["idClasePeriodo"]),
        "root_content_id": int(ctx["idContenido"]),
        "period": int(ctx["periodo"]),
        "section_ng": scope,
        "header_id": int(prepared.header_id),
        "grades_by_student_code": {prepared.student_code: prepared.proposed},
        "class_name": class_name,
        "extra_params": extra,
        "notify": False,
        "verification_attempts": 3,
    }
    if prepared.criterion_level == 1:
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

    try:
        writer_result = client.save_grades_verified(**kwargs)
    except (SieWebError, Exception) as exc:
        raise VerifiedWriterBridgeError(
            f"El writer verificado no pudo confirmar la escritura: {exc}"
        ) from exc

    after = client.get_gradebook_summary(
        class_period_id=int(ctx["idClasePeriodo"]),
        root_content_id=int(ctx["idContenido"]),
        extra_params=extra,
    )
    observed = _student_grade(after, prepared.student_code, prepared.header_id)
    after_snapshot = _grade_snapshot(after)
    target_key = f"{prepared.student_code}:{prepared.header_id}"
    all_keys = sorted(set(prepared.before_snapshot) | set(after_snapshot))
    unexpected = [
        {
            "cell": key,
            "before": prepared.before_snapshot.get(key, ""),
            "after": after_snapshot.get(key, ""),
        }
        for key in all_keys
        if key != target_key and prepared.before_snapshot.get(key, "") != after_snapshot.get(key, "")
    ]
    verified = (
        bool(writer_result.get("saved"))
        and observed == prepared.proposed
        and not unexpected
        and bool((writer_result.get("verification") or {}).get("ok"))
    )
    return {
        "verified": verified,
        "write_sent": True,
        "already_present": False,
        "observed": observed,
        "unexpected_grade_changes": unexpected,
        "writer_mode": writer_result.get("mode"),
        "writer_verification": writer_result.get("verification"),
        "writer_attempts": writer_result.get("verification_attempts"),
        "non_target_verification": writer_result.get("non_target_verification"),
    }
