from __future__ import annotations

import asyncio
import base64
import hashlib
import html
import io
import json
import os
import re
import secrets
import unicodedata
from collections import defaultdict
from datetime import datetime
from pathlib import Path
from typing import Any
from urllib.parse import quote
from zoneinfo import ZoneInfo

import qrcode
import requests
from starlette.requests import Request
from starlette.responses import HTMLResponse, JSONResponse


SESSIONS: dict[str, dict[str, Any]] = {}
ROSTER_PATH = Path(__file__).with_name("attendance_roster.json")
DEVICE_COOKIE = "sieroom_attendance_device"
LIMA = ZoneInfo("America/Lima")
DEFAULT_END_TIME = "16:30"
DEFAULT_SHEET_NAME = "SieRoom - Asistencias de asesoría 2026"


def _now() -> datetime:
    return datetime.now(LIMA)


def _norm(value: str) -> str:
    text = unicodedata.normalize("NFKD", str(value or ""))
    text = "".join(ch for ch in text if not unicodedata.combining(ch))
    text = re.sub(r"[^A-Za-z0-9]+", " ", text).upper()
    return " ".join(text.split())


def _load_advisory_roster() -> dict[str, Any]:
    try:
        return json.loads(ROSTER_PATH.read_text(encoding="utf-8"))
    except Exception:
        return {"source": "", "source_modified": "", "sections": {}}


def _spec_tokens(spec: str) -> set[str]:
    return {x for x in _norm(spec).split() if x not in {"Y", "DE", "DEL", "LA", "LAS", "LOS"}}


def _matches_spec(student_name: str, spec: str) -> bool:
    words = set(_norm(student_name).split())
    wanted = _spec_tokens(spec)
    return bool(wanted) and wanted.issubset(words)


def _truthy_env(name: str, default: bool = False) -> bool:
    raw = os.getenv(name)
    if raw is None:
        return default
    return str(raw).strip().lower() in {"1", "true", "yes", "si", "sí", "on"}


def _hash(value: str) -> str:
    return hashlib.sha256(str(value or "").encode("utf-8", "ignore")).hexdigest()


def _client_ip(request: Request) -> str:
    forwarded = str(request.headers.get("x-forwarded-for") or "").strip()
    if forwarded:
        return forwarded.split(",", 1)[0].strip()
    client = getattr(request, "client", None)
    return str(getattr(client, "host", "") or "")


def _parse_end_at(raw: str, *, now: datetime) -> datetime:
    text = str(raw or DEFAULT_END_TIME).strip().lower()
    # La UI v0.7.3 envía HH:MM. Se conservan formatos anteriores por compatibilidad.
    m = re.search(r"(\d{1,2})\s*:\s*(\d{2})", text)
    if not m:
        raise ValueError("Hora de cierre inválida. Usa HH:MM.")
    hour = int(m.group(1))
    minute = int(m.group(2))
    is_pm = "p" in text and hour < 12
    is_am = "a" in text and hour == 12
    if is_pm:
        hour += 12
    if is_am:
        hour = 0
    if not (0 <= hour <= 23 and 0 <= minute <= 59):
        raise ValueError("Hora de cierre inválida.")
    return now.replace(hour=hour, minute=minute, second=0, microsecond=0)


def _display_time(dt: datetime) -> str:
    hour = dt.hour
    suffix = "a. m." if hour < 12 else "p. m."
    h12 = hour % 12 or 12
    return f"{h12}:{dt.minute:02d} {suffix}"


def install(mcp, sieweb, settings, classroom=None):
    roster_cfg = _load_advisory_roster()
    allowed_specs: dict[str, list[str]] = {
        str(k).upper(): [str(x) for x in v]
        for k, v in dict(roster_cfg.get("sections") or {}).items()
    }
    require_teacher_confirm = _truthy_env("ATTENDANCE_REQUIRE_TEACHER_CONFIRM", True)
    sheet_name = str(os.getenv("ATTENDANCE_SHEET_NAME") or DEFAULT_SHEET_NAME).strip()
    sheet_cache: dict[str, str] = {"id": "", "url": "", "error": ""}

    def admin_ok(request: Request) -> bool:
        expected = str(os.getenv("ATTENDANCE_ADMIN_SECRET") or settings.classroom_bridge_secret or "")
        provided = str(request.query_params.get("key") or request.headers.get("x-attendance-admin-secret") or "")
        return bool(expected and provided and secrets.compare_digest(expected, provided))

    def all_students(section: str) -> list[dict[str, str]]:
        data = sieweb.resolve_student_recipients_by_sections([section])
        return [
            {"code": str(r.get("USUCOD") or ""), "name": str(r.get("USUNOM") or "").strip()}
            for r in data.get("resolved", [])
            if str(r.get("USUCOD") or "").strip()
        ]

    def advisory_students(section: str) -> tuple[list[dict[str, str]], list[str]]:
        specs = allowed_specs.get(section, [])
        live = all_students(section)
        selected: list[dict[str, str]] = []
        matched_specs: set[str] = set()
        for student in live:
            for spec in specs:
                if _matches_spec(student["name"], spec):
                    selected.append(student)
                    matched_specs.add(spec)
                    break
        selected.sort(key=lambda x: _norm(x["name"]))
        unresolved = [spec for spec in specs if spec not in matched_specs]
        return selected, unresolved

    def family(section: str, code: str):
        data = sieweb.resolve_family_recipients_by_sections([section])
        for r in data.get("resolved", []):
            if str(r.get("student_code") or "") == code:
                return {
                    "code": str(r.get("family_code") or ""),
                    "name": str(r.get("family_name") or ""),
                }
        return None

    # ---------- Google Sheets ----------
    def _google_token() -> str:
        if classroom is None:
            raise RuntimeError("El cliente Google no está disponible para crear el registro de asistencia.")
        token = getattr(classroom, "_access_token", None)
        if token:
            return token
        return classroom._refresh_access_token()

    def _google_request(method: str, url: str, *, params=None, json_body=None) -> dict[str, Any]:
        token = _google_token()
        headers = {"Authorization": f"Bearer {token}"}
        response = requests.request(method, url, headers=headers, params=params, json=json_body, timeout=45)
        if response.status_code == 401 and classroom is not None:
            headers["Authorization"] = f"Bearer {classroom._refresh_access_token()}"
            response = requests.request(method, url, headers=headers, params=params, json=json_body, timeout=45)
        if not response.ok:
            raise RuntimeError(f"Google API falló ({response.status_code}): {response.text[:700]}")
        return response.json() if response.content else {}

    def _sheets_values(method: str, sheet_id: str, a1_range: str, *, values=None, append=False) -> dict[str, Any]:
        encoded = quote(a1_range, safe="")
        if append:
            url = f"https://sheets.googleapis.com/v4/spreadsheets/{sheet_id}/values/{encoded}:append"
            return _google_request(
                "POST", url,
                params={"valueInputOption": "USER_ENTERED", "insertDataOption": "INSERT_ROWS"},
                json_body={"values": values or []},
            )
        if method == "GET":
            url = f"https://sheets.googleapis.com/v4/spreadsheets/{sheet_id}/values/{encoded}"
            return _google_request("GET", url)
        url = f"https://sheets.googleapis.com/v4/spreadsheets/{sheet_id}/values/{encoded}"
        return _google_request(
            "PUT", url,
            params={"valueInputOption": "USER_ENTERED"},
            json_body={"values": values or []},
        )

    def _ensure_attendance_sheet() -> tuple[str, str]:
        if sheet_cache["id"]:
            return sheet_cache["id"], sheet_cache["url"]
        try:
            drive = _google_request(
                "GET",
                "https://www.googleapis.com/drive/v3/files",
                params={
                    "q": f"name = '{sheet_name.replace(chr(39), chr(92)+chr(39))}' and trashed = false and mimeType = 'application/vnd.google-apps.spreadsheet'",
                    "spaces": "drive",
                    "fields": "files(id,name,webViewLink,createdTime)",
                    "orderBy": "createdTime desc",
                    "pageSize": 10,
                },
            )
            files = drive.get("files") or []
            if files:
                sheet_cache["id"] = str(files[0]["id"])
                sheet_cache["url"] = str(files[0].get("webViewLink") or f"https://docs.google.com/spreadsheets/d/{files[0]['id']}/edit")
                sheet_cache["error"] = ""
                return sheet_cache["id"], sheet_cache["url"]

            created = _google_request(
                "POST",
                "https://sheets.googleapis.com/v4/spreadsheets",
                json_body={
                    "properties": {"title": sheet_name, "locale": "es_PE", "timeZone": "America/Lima"},
                    "sheets": [
                        {"properties": {"title": "Asistencias"}},
                        {"properties": {"title": "Sesiones"}},
                        {"properties": {"title": "Resumen"}},
                    ],
                },
            )
            sid = str(created.get("spreadsheetId") or "")
            if not sid:
                raise RuntimeError("Google Sheets no devolvió spreadsheetId.")
            surl = str(created.get("spreadsheetUrl") or f"https://docs.google.com/spreadsheets/d/{sid}/edit")
            sheet_cache["id"], sheet_cache["url"], sheet_cache["error"] = sid, surl, ""
            _sheets_values("PUT", sid, "Asistencias!A1:J1", values=[["ID sesión", "Fecha", "Sección", "Estudiante", "Código SIEweb", "Hora ingreso", "Estado", "Aviso familia", "Hora aviso", "Observación"]])
            _sheets_values("PUT", sid, "Sesiones!A1:K1", values=[["ID sesión", "Fecha", "Sección", "Creada", "Cierre programado", "Cerrada", "Convocados", "Asistieron", "Faltaron", "Pendientes", "Estado"]])
            _sheets_values("PUT", sid, "Resumen!A1:F1", values=[["Sección", "Estudiante", "Asistencias", "Faltas", "Total sesiones", "% asistencia"]])
            return sid, surl
        except Exception as ex:
            sheet_cache["error"] = str(ex)
            raise

    def _append_session_start(ses: dict[str, Any]) -> None:
        try:
            sid, surl = _ensure_attendance_sheet()
            result = _sheets_values(
                "POST", sid, "Sesiones!A:K", append=True,
                values=[[ses["token"], ses["date"], ses["section"], ses["created_at_display"], ses["end_time"], "", len(ses["roster_snapshot"]), 0, 0, 0, "ABIERTA"]],
            )
            rng = str((result.get("updates") or {}).get("updatedRange") or "")
            m = re.search(r"!(?:[A-Z]+)(\d+):", rng)
            ses["session_sheet_row"] = int(m.group(1)) if m else None
            ses["sheet_id"] = sid
            ses["sheet_url"] = surl
            ses["sheet_error"] = ""
        except Exception as ex:
            ses["sheet_error"] = str(ex)

    def _append_final_student_row(ses: dict[str, Any], student: dict[str, str], *, state: str, rec: dict[str, Any] | None = None, observation: str = "") -> None:
        if rec is not None and rec.get("sheet_final_logged"):
            return
        code = student["code"]
        if code in set(ses.get("absent_sheet_logged") or set()) and state == "FALTÓ":
            return
        try:
            sid, surl = _ensure_attendance_sheet()
            time_in = rec.get("time", "") if rec else ""
            notified = "SÍ" if rec and rec.get("notified") else ("SÍ" if state == "FALTÓ" and ses.get("absence_notifications", {}).get(code, {}).get("notified") else "NO")
            notified_at = rec.get("notified_at", "") if rec else str(ses.get("absence_notifications", {}).get(code, {}).get("notified_at") or "")
            _sheets_values(
                "POST", sid, "Asistencias!A:J", append=True,
                values=[[ses["token"], ses["date"], ses["section"], student["name"], code, time_in, state, notified, notified_at, observation]],
            )
            ses["sheet_id"] = sid
            ses["sheet_url"] = surl
            ses["sheet_error"] = ""
            if rec is not None:
                rec["sheet_final_logged"] = True
            elif state == "FALTÓ":
                ses.setdefault("absent_sheet_logged", set()).add(code)
        except Exception as ex:
            ses["sheet_error"] = str(ex)
            if rec is not None:
                rec["sheet_error"] = str(ex)

    def _update_session_sheet_row(ses: dict[str, Any]) -> None:
        row = ses.get("session_sheet_row")
        if not row:
            return
        try:
            sid, _ = _ensure_attendance_sheet()
            confirmed = sum(1 for r in ses["attendees"].values() if r.get("status") == "confirmed")
            pending = sum(1 for r in ses["attendees"].values() if r.get("status") == "pending")
            absent = len(ses.get("absence_notifications") or {})
            status = "CERRADA" if ses.get("finalized") else ("CERRADA · PENDIENTES" if ses.get("closed") else "ABIERTA")
            _sheets_values(
                "PUT", sid, f"Sesiones!F{row}:K{row}",
                values=[[ses.get("closed_at_display", ""), len(ses["roster_snapshot"]), confirmed, absent, pending, status]],
            )
        except Exception as ex:
            ses["sheet_error"] = str(ex)

    def _rebuild_summary() -> None:
        try:
            sid, _ = _ensure_attendance_sheet()
            data = _sheets_values("GET", sid, "Asistencias!A2:J").get("values") or []
            stats: dict[tuple[str, str], dict[str, int]] = defaultdict(lambda: {"a": 0, "f": 0})
            for row in data:
                row = list(row) + [""] * (10 - len(row))
                section, name, state = str(row[2]), str(row[3]), str(row[6])
                if not section or not name:
                    continue
                if state == "ASISTIÓ":
                    stats[(section, name)]["a"] += 1
                elif state == "FALTÓ":
                    stats[(section, name)]["f"] += 1
            rows = [["Sección", "Estudiante", "Asistencias", "Faltas", "Total sesiones", "% asistencia"]]
            for (section, name), st in sorted(stats.items(), key=lambda x: (_norm(x[0][0]), _norm(x[0][1]))):
                total = st["a"] + st["f"]
                pct = round((st["a"] / total) * 100, 1) if total else 0
                rows.append([section, name, st["a"], st["f"], total, pct / 100])
            # Limpiamos un rango amplio para no dejar restos de alumnos antiguos.
            encoded = quote("Resumen!A1:F500", safe="")
            _google_request("POST", f"https://sheets.googleapis.com/v4/spreadsheets/{sid}/values/{encoded}:clear")
            _sheets_values("PUT", sid, f"Resumen!A1:F{max(1, len(rows))}", values=rows)
        except Exception:
            # El historial principal tiene prioridad; un fallo del resumen no invalida la asistencia.
            pass

    # ---------- Notificaciones ----------
    def _notify_family(ses: dict[str, Any], code: str, rec: dict[str, Any]) -> tuple[bool, str]:
        if rec.get("notified"):
            return True, ""
        fam = family(ses["section"], code)
        if not fam or not fam["code"]:
            return False, "No se encontró la familia en SIEweb."
        subject = "Asistencia registrada – Taller de asesoría"
        text = (
            "Estimados padres de familia:\n\n"
            f"Les informo que {rec['name']} ha registrado correctamente su asistencia "
            "al taller de asesoría de Matemática.\n\n"
            f"Su asistencia ha quedado registrada satisfactoriamente. El taller culminará hoy a las {ses['end_time']}.\n\n"
            "Si tienen alguna duda o consulta, estaré disponible para atenderlos.\n\n"
            "Saludos cordiales."
        )
        try:
            result = sieweb.send_message(recipient_codes=[fam["code"]], subject=subject, plain_text=text)
            rec["notified"] = True
            rec["notified_at"] = _now().strftime("%d/%m/%Y %H:%M:%S")
            rec["family_name"] = fam["name"]
            rec["notification_result"] = result
            rec["error"] = ""
            return True, ""
        except Exception as ex:
            rec["error"] = str(ex)
            return False, "Asistencia confirmada, pero falló el aviso a la familia."

    def _notify_absence(ses: dict[str, Any], student: dict[str, str]) -> tuple[bool, str]:
        code = student["code"]
        existing = ses.setdefault("absence_notifications", {}).get(code)
        if existing and existing.get("notified"):
            return True, ""
        fam = family(ses["section"], code)
        if not fam or not fam["code"]:
            ses["absence_notifications"][code] = {"notified": False, "error": "No se encontró la familia en SIEweb."}
            return False, "No se encontró la familia en SIEweb."
        subject = "Inasistencia registrada – Taller de asesoría"
        text = (
            "Estimados padres de familia:\n\n"
            f"Les informo que {student['name']} no asistió al taller de asesoría de Matemática programado para hoy, "
            f"{ses['date']}. Al cierre del taller, a las {ses['end_time']}, su inasistencia ha quedado registrada como falta.\n\n"
            "Este aviso tiene como finalidad mantenerlos informados y facilitar el seguimiento de la participación del estudiante en las asesorías.\n\n"
            "Si existiera alguna situación excepcional que deba ser comunicada, quedaré atento a su mensaje.\n\n"
            "Saludos cordiales."
        )
        try:
            result = sieweb.send_message(recipient_codes=[fam["code"]], subject=subject, plain_text=text)
            ses["absence_notifications"][code] = {
                "notified": True,
                "notified_at": _now().strftime("%d/%m/%Y %H:%M:%S"),
                "family_name": fam["name"],
                "notification_result": result,
                "error": "",
            }
            return True, ""
        except Exception as ex:
            ses["absence_notifications"][code] = {"notified": False, "notified_at": "", "error": str(ex)}
            return False, str(ex)

    # ---------- Cierre automático ----------
    def _active_claims(ses: dict[str, Any]) -> list[dict[str, Any]]:
        return [r for r in ses["attendees"].values() if r.get("status") in {"pending", "confirmed"}]

    def _device_conflict(ses: dict[str, Any], *, device_cookie: str, browser_id: str, fingerprint: str):
        dc = _hash(device_cookie) if device_cookie else ""
        bi = _hash(browser_id) if browser_id else ""
        fp = _hash(fingerprint) if fingerprint else ""
        for rec in _active_claims(ses):
            if dc and dc == rec.get("device_cookie_hash"):
                return rec
            if bi and bi == rec.get("browser_id_hash"):
                return rec
            if fp and fp == rec.get("fingerprint_hash"):
                return rec
        return None

    def _student_by_code(ses: dict[str, Any], code: str) -> dict[str, str] | None:
        return next((x for x in ses.get("roster_snapshot", []) if x["code"] == code), None)

    def _close_due_session(token: str) -> None:
        ses = SESSIONS.get(token)
        if not ses or ses.get("closed"):
            return
        ses["closed"] = True
        ses["closed_at"] = _now().isoformat()
        ses["closed_at_display"] = _now().strftime("%d/%m/%Y %H:%M:%S")

        confirmed_codes = {code for code, rec in ses["attendees"].items() if rec.get("status") == "confirmed"}
        pending_codes = {code for code, rec in ses["attendees"].items() if rec.get("status") == "pending"}
        for student in ses.get("roster_snapshot", []):
            code = student["code"]
            if code in confirmed_codes or code in pending_codes:
                continue
            _notify_absence(ses, student)
            _append_final_student_row(ses, student, state="FALTÓ", observation="Inasistencia registrada al cierre automático de la asesoría.")

        ses["finalized"] = not bool(pending_codes)
        _update_session_sheet_row(ses)
        if ses["finalized"]:
            _rebuild_summary()

    def _resolve_pending_after_close(ses: dict[str, Any], code: str, *, confirmed: bool) -> None:
        if not ses.get("closed"):
            return
        student = _student_by_code(ses, code)
        if not student:
            return
        rec = ses["attendees"].get(code)
        if confirmed:
            _append_final_student_row(ses, student, state="ASISTIÓ", rec=rec, observation="Asistencia confirmada por el docente.")
        else:
            _notify_absence(ses, student)
            _append_final_student_row(ses, student, state="FALTÓ", observation="Registro rechazado por el docente; se contabiliza como falta.")
        pending = sum(1 for r in ses["attendees"].values() if r.get("status") == "pending")
        ses["finalized"] = pending == 0
        _update_session_sheet_row(ses)
        if ses["finalized"]:
            _rebuild_summary()

    async def _deadline_worker(token: str) -> None:
        ses = SESSIONS.get(token)
        if not ses:
            return
        try:
            end_at = datetime.fromisoformat(ses["end_at"])
            delay = max(0.0, (end_at - _now()).total_seconds())
            await asyncio.sleep(delay)
            await asyncio.to_thread(_close_due_session, token)
        except Exception as ex:
            if token in SESSIONS:
                SESSIONS[token]["close_error"] = str(ex)

    def _ensure_due_closed(ses: dict[str, Any]) -> None:
        if ses.get("closed"):
            return
        try:
            if _now() >= datetime.fromisoformat(ses["end_at"]):
                _close_due_session(ses["token"])
        except Exception:
            pass

    # ---------- Panel docente ----------
    @mcp.custom_route("/asesoria", methods=["GET"])
    async def admin(request: Request):
        if not admin_ok(request):
            return HTMLResponse("<h2>Acceso no autorizado</h2>", 401)
        key = request.query_params.get("key", "")
        page = r"""<!doctype html>
<meta charset=utf-8><meta name=viewport content='width=device-width,initial-scale=1'>
<title>SieRoom Asesoría</title>
<style>
body{font-family:system-ui;max-width:1050px;margin:24px auto;padding:16px;color:#111}
input,select,button{font-size:17px;padding:10px;margin:5px}button{cursor:pointer}
.card{border:1px solid #ddd;border-radius:14px;padding:16px;margin:14px 0}.muted{color:#666}.warn{color:#9a5b00}.ok{color:#087a28}.bad{color:#a51b1b}
table{width:100%;border-collapse:collapse}td,th{padding:9px;border-bottom:1px solid #ddd;text-align:left;vertical-align:top}
.small{font-size:13px}.pending{background:#fff9e8}.confirmed{background:#eefaf1}.rejected{background:#fff0f0}.absent{background:#fff4f4}
a.btn{display:inline-block;padding:9px 12px;border:1px solid #bbb;border-radius:8px;text-decoration:none;color:#111;margin:4px 0}
</style>
<h1>Asistencia a asesoría</h1>
<p>Crea una sesión y proyecta el QR. La v0.7.3 registra asistencia, avisa a las familias y al cierre envía automáticamente los avisos de inasistencia.</p>
<div class=card><select id=s><option>2A</option><option>2B</option><option>5A</option><option>5B</option></select><label> Cierre: <input id=e type=time value='16:30'></label><button onclick='createSession()'>Nueva asesoría</button></div>
<div id=out></div>
<script>
const key=KEY;
const esc=v=>String(v??'').replace(/[&<>"']/g,c=>({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[c]));
async function createSession(){
 let r=await fetch('/asesoria/api/session?key='+encodeURIComponent(key),{method:'POST',headers:{'content-type':'application/json'},body:JSON.stringify({section:s.value,end_time:e.value})});
 let j=await r.json();if(!j.ok){out.innerHTML='<p class=bad>'+esc(j.error||JSON.stringify(j))+'</p>';return}
 let sheet=j.sheet_url?'<p><a class=btn target=_blank href="'+esc(j.sheet_url)+'">📊 Abrir registro en Google Sheets</a></p>':('<p class=warn><b>Google Sheets:</b> '+esc(j.sheet_error||'Todavía no disponible.')+'</p>');
 out.innerHTML='<div class=card><h2>'+esc(j.section)+' · '+esc(j.date)+'</h2><p><b>Cierre automático:</b> '+esc(j.end_time)+'</p><p><b>Lista autorizada:</b> '+j.roster_count+' estudiantes</p>'+(j.unresolved_allowlist?.length?'<p class=warn><b>Atención:</b> no pude enlazar automáticamente: '+esc(j.unresolved_allowlist.join(', '))+'</p>':'')+'<img style="width:min(70vw,430px)" src="'+j.qr_data_url+'"><p class=small><b>Enlace:</b> '+esc(j.checkin_url)+'</p><p><b>Seguridad:</b> '+(j.teacher_confirmation?'Confirmación visual del docente activada. El correo de asistencia se envía solo al confirmar.':'Confirmación automática activada.')+'</p>'+sheet+'</div><h3>Registros</h3><div id=list></div>';
 poll(j.token)
}
async function action(t,code,kind){
 let r=await fetch('/asesoria/api/session/'+encodeURIComponent(t)+'/'+kind+'/'+encodeURIComponent(code)+'?key='+encodeURIComponent(key),{method:'POST'});let j=await r.json();
 if(!j.ok)alert(j.error||'No se pudo completar la acción.');
}
async function poll(t){
 let r=await fetch('/asesoria/api/session/'+encodeURIComponent(t)+'/status?key='+encodeURIComponent(key));let j=await r.json();
 if(!j.ok){return}
 let rows=j.attendees.map(x=>{
   let controls=x.status==='pending'?'<button onclick="action(\''+t+'\',\''+x.code+'\',\'confirm\')">✓ Confirmar</button><button onclick="action(\''+t+'\',\''+x.code+'\',\'reject\')">✕ Rechazar</button>':'';
   let aviso=x.notified?'✓ Enviado':(x.error?'⚠ '+esc(x.error):(x.status==='pending'?'Espera confirmación':'—'));
   return '<tr class="'+esc(x.status)+'"><td><b>'+esc(x.name)+'</b><div class=small>'+esc(x.status)+'</div></td><td>'+esc(x.time)+'</td><td>'+aviso+'</td><td>'+controls+'</td></tr>'
 }).join('');
 let abs=j.absences.map(x=>'<tr class=absent><td><b>'+esc(x.name)+'</b><div class=small>FALTA</div></td><td>—</td><td>'+(x.notified?'✓ Aviso de inasistencia enviado':('⚠ '+esc(x.error||'Pendiente')))+'</td><td>—</td></tr>').join('');
 let state=j.closed?('<span class="'+(j.finalized?'ok':'warn')+'"><b>'+esc(j.finalized?'CERRADA':'CERRADA · PENDIENTES POR RESOLVER')+'</b></span>'):'<span class=ok><b>ABIERTA</b></span>';
 let sheet=j.sheet_url?'<a class=btn target=_blank href="'+esc(j.sheet_url)+'">📊 Google Sheets</a>':('<span class=warn>'+esc(j.sheet_error||'Registro Sheets no disponible')+'</span>');
 list.innerHTML='<p>'+state+' · <b>Pendientes:</b> '+j.counts.pending+' · <b>Confirmados:</b> '+j.counts.confirmed+' · <b>Faltas notificadas:</b> '+j.counts.absent+'</p><p>'+sheet+'</p><table><tr><th>Alumno</th><th>Hora</th><th>Aviso a familia</th><th>Acción</th></tr>'+rows+abs+'</table>';
 setTimeout(()=>poll(t),2500)
}
</script>""".replace("KEY", repr(key))
        return HTMLResponse(page)

    @mcp.custom_route("/asesoria/api/session", methods=["POST"])
    async def create(request: Request):
        if not admin_ok(request):
            return JSONResponse({"ok": False, "error": "unauthorized"}, 401)
        try:
            body = await request.json()
        except Exception:
            body = {}
        section = str(body.get("section") or "").upper().replace(" ", "")
        if section not in {"2A", "2B", "5A", "5B"}:
            return JSONResponse({"ok": False, "error": "section_invalid"}, 400)
        now = _now()
        try:
            end_at = _parse_end_at(str(body.get("end_time") or DEFAULT_END_TIME), now=now)
        except ValueError as ex:
            return JSONResponse({"ok": False, "error": str(ex)}, 400)
        if end_at <= now:
            return JSONResponse({"ok": False, "error": f"La hora de cierre {_display_time(end_at)} ya pasó. Elige una hora futura para esta sesión."}, 400)
        try:
            roster, unresolved = advisory_students(section)
        except Exception as ex:
            return JSONResponse({"ok": False, "error": f"No se pudo consultar SIEweb: {ex}"}, 502)
        if not roster:
            return JSONResponse({"ok": False, "error": "No se pudo enlazar ningún estudiante autorizado de asesoría con SIEweb."}, 422)
        token = secrets.token_urlsafe(18)
        ses = {
            "token": token,
            "section": section,
            "date": now.strftime("%d/%m/%Y"),
            "date_iso": now.strftime("%Y-%m-%d"),
            "created_at": now.isoformat(timespec="seconds"),
            "created_at_display": now.strftime("%d/%m/%Y %H:%M:%S"),
            "end_at": end_at.isoformat(timespec="seconds"),
            "end_time": _display_time(end_at),
            "attendees": {},
            "allowed_codes": {x["code"] for x in roster},
            "roster_snapshot": roster,
            "unresolved_allowlist": unresolved,
            "absence_notifications": {},
            "absent_sheet_logged": set(),
            "closed": False,
            "finalized": False,
            "sheet_id": "",
            "sheet_url": "",
            "sheet_error": "",
        }
        SESSIONS[token] = ses
        await asyncio.to_thread(_append_session_start, ses)
        asyncio.create_task(_deadline_worker(token))
        url = f"{settings.public_base_url}/asesoria/r/{token}"
        qr = qrcode.make(url)
        buf = io.BytesIO()
        qr.save(buf, format="PNG")
        return JSONResponse({
            "ok": True,
            "token": token,
            "section": section,
            "date": ses["date"],
            "end_time": ses["end_time"],
            "checkin_url": url,
            "qr_data_url": "data:image/png;base64," + base64.b64encode(buf.getvalue()).decode(),
            "roster_count": len(roster),
            "roster_names": [x["name"] for x in roster],
            "unresolved_allowlist": unresolved,
            "teacher_confirmation": require_teacher_confirm,
            "roster_source": roster_cfg.get("source", ""),
            "sheet_url": ses.get("sheet_url", ""),
            "sheet_error": ses.get("sheet_error", ""),
        })

    @mcp.custom_route("/asesoria/r/{token}", methods=["GET"])
    async def form(request: Request):
        token = str(request.path_params.get("token") or "")
        ses = SESSIONS.get(token)
        if not ses:
            return HTMLResponse("<h2>Esta sesión ya no está disponible.</h2>", 404)
        _ensure_due_closed(ses)
        if ses.get("closed"):
            return HTMLResponse(f"<h2>La asesoría de {html.escape(ses['section'])} ya cerró a las {html.escape(ses['end_time'])}.</h2><p>Ya no se admiten nuevos registros.</p>", 410)
        device_cookie = str(request.cookies.get(DEVICE_COOKIE) or "").strip()
        new_cookie = False
        if not device_cookie:
            device_cookie = secrets.token_urlsafe(24)
            new_cookie = True
        roster = list(ses.get("roster_snapshot") or [])
        opts = "".join(
            '<option value="' + html.escape(x["code"], quote=True) + '">' + html.escape(x["name"]) + "</option>"
            for x in roster
        )
        page = r"""<!doctype html>
<meta charset=utf-8><meta name=viewport content='width=device-width,initial-scale=1'>
<title>Asesoría de Matemática</title>
<style>body{font-family:system-ui;max-width:600px;margin:30px auto;padding:20px;text-align:center}select,button{width:100%;font-size:18px;padding:14px;margin:10px 0}.note{font-size:14px;color:#666}.error{color:#a51b1b}.ok{color:#087a28}</style>
<h1>Asesoría de Matemática</h1><p>SECTION · DATE</p><p><b>Cierre: ENDTIME</b></p>
<p class=note>Solo aparecen los estudiantes convocados a nivelación del II trimestre. Este dispositivo puede registrar a un solo estudiante en esta sesión.</p>
<select id=student><option value=''>— Selecciona tu nombre —</option>OPTIONS</select>
<button id=btn onclick='go()'>REGISTRAR MI ASISTENCIA</button><div id=msg></div>
<script>
function browserId(){let k='sieroom_browser_id',v=localStorage.getItem(k);if(!v){v=(crypto.randomUUID?crypto.randomUUID():String(Date.now())+'-'+Math.random());localStorage.setItem(k,v)}return v}
function fingerprint(){return [navigator.userAgent,navigator.platform,navigator.language,Intl.DateTimeFormat().resolvedOptions().timeZone,screen.width+'x'+screen.height,navigator.hardwareConcurrency||'',navigator.deviceMemory||'',navigator.maxTouchPoints||''].join('|')}
async function go(){
 if(!student.value)return;btn.disabled=true;msg.innerHTML='<p>Registrando…</p>';
 let r=await fetch('/asesoria/api/checkin/TOKEN',{method:'POST',headers:{'content-type':'application/json'},body:JSON.stringify({student_code:student.value,browser_id:browserId(),fingerprint:fingerprint()})});let j=await r.json();
 if(j.ok){msg.innerHTML=j.status==='confirmed'?'<h2 class=ok>✓ Asistencia confirmada</h2><p>La familia ha sido notificada.</p>':'<h2 class=ok>✓ Registro recibido</h2><p>Espera la confirmación visual del docente. El aviso a tu familia se enviará después de esa confirmación.</p>';return}
 btn.disabled=false;msg.innerHTML='<h2 class=error>No se pudo registrar</h2><p>'+(j.error||'')+'</p>'
}
</script>"""
        page = page.replace("SECTION", html.escape(ses["section"]))
        page = page.replace("DATE", html.escape(ses["date"]))
        page = page.replace("ENDTIME", html.escape(ses["end_time"]))
        page = page.replace("OPTIONS", opts).replace("TOKEN", token)
        response = HTMLResponse(page)
        if new_cookie:
            response.set_cookie(
                DEVICE_COOKIE,
                device_cookie,
                max_age=60 * 60 * 24 * 365,
                httponly=True,
                samesite="lax",
                secure=str(settings.public_base_url).lower().startswith("https://"),
            )
        return response

    @mcp.custom_route("/asesoria/api/checkin/{token}", methods=["POST"])
    async def checkin(request: Request):
        token = str(request.path_params.get("token") or "")
        ses = SESSIONS.get(token)
        if not ses:
            return JSONResponse({"ok": False, "error": "Sesión no disponible."}, 404)
        _ensure_due_closed(ses)
        if ses.get("closed"):
            return JSONResponse({"ok": False, "error": f"La asesoría cerró a las {ses['end_time']}. Ya no se admiten nuevos registros."}, 410)
        try:
            body = await request.json()
        except Exception:
            body = {}
        code = str(body.get("student_code") or "").strip()
        browser_id = str(body.get("browser_id") or "").strip()
        fingerprint = str(body.get("fingerprint") or "").strip()
        device_cookie = str(request.cookies.get(DEVICE_COOKIE) or "").strip()
        if not device_cookie or not browser_id:
            return JSONResponse({"ok": False, "error": "No se pudo identificar este dispositivo. Recarga la página y vuelve a intentarlo."}, 400)
        if code not in set(ses.get("allowed_codes") or set()):
            return JSONResponse({"ok": False, "error": "Este estudiante no está convocado a la asesoría del II trimestre."}, 403)

        existing_student = ses["attendees"].get(code)
        if existing_student and existing_student.get("status") in {"pending", "confirmed"}:
            return JSONResponse({"ok": False, "error": "Este estudiante ya fue registrado en esta sesión."}, 409)

        conflict = _device_conflict(ses, device_cookie=device_cookie, browser_id=browser_id, fingerprint=fingerprint)
        if conflict:
            return JSONResponse({"ok": False, "error": f"Este dispositivo ya registró a {conflict.get('name','otro estudiante')} en esta sesión. No puede registrar a otra persona."}, 409)

        student = _student_by_code(ses, code)
        if not student:
            return JSONResponse({"ok": False, "error": "Alumno no válido."}, 400)

        now = _now()
        rec = {
            "code": code,
            "name": student["name"],
            "time": now.strftime("%H:%M:%S"),
            "created_at": now.isoformat(timespec="seconds"),
            "status": "pending" if require_teacher_confirm else "confirmed",
            "notified": False,
            "notified_at": "",
            "error": "",
            "ip": _client_ip(request),
            "user_agent": str(request.headers.get("user-agent") or ""),
            "device_cookie_hash": _hash(device_cookie),
            "browser_id_hash": _hash(browser_id),
            "fingerprint_hash": _hash(fingerprint),
            "sheet_final_logged": False,
        }
        ses["attendees"][code] = rec

        if require_teacher_confirm:
            return JSONResponse({"ok": True, "student": student["name"], "status": "pending", "notified": False})

        sent, error = await asyncio.to_thread(_notify_family, ses, code, rec)
        await asyncio.to_thread(_append_final_student_row, ses, student, state="ASISTIÓ", rec=rec, observation="Asistencia registrada automáticamente.")
        return JSONResponse({"ok": sent, "attendance_saved": True, "student": student["name"], "status": "confirmed", "notified": sent, "error": error}, 200 if sent else 502)

    @mcp.custom_route("/asesoria/api/session/{token}/confirm/{code}", methods=["POST"])
    async def confirm(request: Request):
        if not admin_ok(request):
            return JSONResponse({"ok": False, "error": "unauthorized"}, 401)
        token = str(request.path_params.get("token") or "")
        code = str(request.path_params.get("code") or "")
        ses = SESSIONS.get(token)
        if not ses:
            return JSONResponse({"ok": False, "error": "Sesión no disponible."}, 404)
        _ensure_due_closed(ses)
        rec = ses["attendees"].get(code)
        if not rec:
            return JSONResponse({"ok": False, "error": "Registro no encontrado."}, 404)
        if rec.get("status") == "rejected":
            return JSONResponse({"ok": False, "error": "El registro ya fue rechazado."}, 409)
        rec["status"] = "confirmed"
        rec["confirmed_at"] = _now().isoformat(timespec="seconds")
        sent, error = await asyncio.to_thread(_notify_family, ses, code, rec)
        student = _student_by_code(ses, code)
        if student:
            await asyncio.to_thread(_append_final_student_row, ses, student, state="ASISTIÓ", rec=rec, observation="Asistencia confirmada por el docente.")
        if ses.get("closed"):
            await asyncio.to_thread(_resolve_pending_after_close, ses, code, confirmed=True)
        return JSONResponse({"ok": sent, "status": "confirmed", "notified": sent, "error": error}, 200 if sent else 502)

    @mcp.custom_route("/asesoria/api/session/{token}/reject/{code}", methods=["POST"])
    async def reject(request: Request):
        if not admin_ok(request):
            return JSONResponse({"ok": False, "error": "unauthorized"}, 401)
        token = str(request.path_params.get("token") or "")
        code = str(request.path_params.get("code") or "")
        ses = SESSIONS.get(token)
        if not ses:
            return JSONResponse({"ok": False, "error": "Sesión no disponible."}, 404)
        _ensure_due_closed(ses)
        rec = ses["attendees"].get(code)
        if not rec:
            return JSONResponse({"ok": False, "error": "Registro no encontrado."}, 404)
        if rec.get("notified"):
            return JSONResponse({"ok": False, "error": "No se puede rechazar porque la familia ya fue notificada."}, 409)
        rec["status"] = "rejected"
        rec["rejected_at"] = _now().isoformat(timespec="seconds")
        if ses.get("closed"):
            await asyncio.to_thread(_resolve_pending_after_close, ses, code, confirmed=False)
        return JSONResponse({"ok": True, "status": "rejected"})

    @mcp.custom_route("/asesoria/api/session/{token}/status", methods=["GET"])
    async def status(request: Request):
        if not admin_ok(request):
            return JSONResponse({"ok": False, "error": "unauthorized"}, 401)
        ses = SESSIONS.get(str(request.path_params.get("token") or ""))
        if not ses:
            return JSONResponse({"ok": False, "error": "not_found"}, 404)
        _ensure_due_closed(ses)
        attendees = list(ses["attendees"].values())
        attendees.sort(key=lambda x: x.get("created_at", ""))
        absences = []
        for code, note in (ses.get("absence_notifications") or {}).items():
            student = _student_by_code(ses, code)
            absences.append({
                "code": code,
                "name": student["name"] if student else code,
                "notified": bool(note.get("notified")),
                "notified_at": note.get("notified_at", ""),
                "error": note.get("error", ""),
            })
        absences.sort(key=lambda x: _norm(x["name"]))
        counts = {
            "pending": sum(1 for x in attendees if x.get("status") == "pending"),
            "confirmed": sum(1 for x in attendees if x.get("status") == "confirmed"),
            "rejected": sum(1 for x in attendees if x.get("status") == "rejected"),
            "absent": len(absences),
        }
        public_rows = [
            {
                "code": x.get("code"), "name": x.get("name"), "time": x.get("time"), "status": x.get("status"),
                "notified": bool(x.get("notified")), "notified_at": x.get("notified_at", ""), "error": x.get("error", ""), "ip": x.get("ip", ""),
            }
            for x in attendees
        ]
        return JSONResponse({
            "ok": True,
            "attendees": public_rows,
            "absences": absences,
            "counts": counts,
            "closed": bool(ses.get("closed")),
            "finalized": bool(ses.get("finalized")),
            "end_time": ses.get("end_time", ""),
            "sheet_url": ses.get("sheet_url", ""),
            "sheet_error": ses.get("sheet_error", ""),
            "close_error": ses.get("close_error", ""),
        })
