from __future__ import annotations

import json
import os
import re
import threading
import time
from collections import defaultdict, deque
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timezone
from io import BytesIO
from typing import Any
from zoneinfo import ZoneInfo

import fitz
import requests
from docx import Document
from starlette.requests import Request
from starlette.responses import JSONResponse

from classroom import ClassroomClient, ClassroomError
from config import settings
from bitacora import (
    _history as _bitacora_history,
    _load_students as _bitacora_load_students,
    _resolve_student as _bitacora_resolve_student,
)


KB_FOLDER_ID = os.getenv("PROFE_JOHNNY_KB_FOLDER_ID", "1Ih3RaxV89vm7bcWJbUJ-TbOwzlgspTZG")
MODEL = os.getenv("PROFE_JOHNNY_MODEL", "gpt-5.6-terra")
OPENAI_API_KEY = os.getenv("OPENAI_API_KEY", "").strip()
CACHE_TTL_SECONDS = max(60, int(os.getenv("PROFE_JOHNNY_CACHE_TTL_SECONDS", "300")))
MAX_MESSAGE_CHARS = 1800
MAX_CONTEXT_CHARS = 70000
MAX_DRIVE_RESULTS = 5
MAX_CLASSROOM_ITEMS_PER_COURSE = 18

_client = ClassroomClient()
_cache_lock = threading.RLock()
_cache: dict[str, Any] = {"loaded_at": 0.0, "docs": [], "error": None}
_rate_lock = threading.RLock()
_rate: dict[str, deque[float]] = defaultdict(deque)

STOPWORDS = {
    "a", "al", "algo", "ante", "como", "con", "cual", "cuando", "de", "del", "desde", "donde",
    "el", "ella", "en", "es", "esa", "ese", "eso", "esta", "este", "esto", "hay", "la", "las",
    "lo", "los", "me", "mi", "mis", "para", "pero", "por", "que", "se", "si", "sin", "su", "sus",
    "te", "tengo", "tiene", "un", "una", "unos", "unas", "y", "ya", "yo", "hoy", "mañana",
}

BASE_INSTRUCTIONS = """
Respondes como el Profe Johnny dentro de PROFE JOHNNY APP para Matemática de 2.º A, 2.º B, 5.º A y 5.º B de secundaria.
Tu función es orientar a estudiantes y familias usando únicamente información verificable del colegio y del profesor Johnny.

REGLAS INNEGOCIABLES:
- Responde en español, con claridad, cercanía, respeto y criterio pedagógico.
- Cuando la identidad verificada sea de una familia/padre/madre/apoderado, usa SIEMPRE lenguaje psicopedagógico: respetuoso, descriptivo, constructivo, orientado al acompañamiento y sin etiquetas personales.
- En respuestas a familias, describe conductas observables y su impacto pedagógico. Evita expresiones como “molestar”, “fastidiar”, “portarse mal”, “flojo”, “irresponsable”, “problemático” o equivalentes. Prefiere formulaciones como “se registró una interacción que generó incomodidad”, “presentó dificultad para mantener la atención”, “requiere fortalecer la organización/constancia” o describe exactamente la conducta observada.
- No diagnostiques ni atribuyas intenciones, rasgos de personalidad, problemas familiares o condiciones de salud. Separa claramente hechos registrados de interpretaciones.
- Si una incidencia menciona a otro estudiante, no reveles el nombre del otro menor a la familia. Refiérete a “un compañero”, “otra estudiante” o “otro estudiante”, según corresponda.
- Para familias, convierte la información sensible en una comunicación útil: qué se observó, cómo impactó el aprendizaje o la convivencia y qué puede hacerse para acompañar la mejora. No minimices hechos relevantes ni uses lenguaje alarmista.
- FORMATO DE RESPUESTA EN LA APP: usa títulos breves en líneas separadas terminados en dos puntos, viñetas con “- ” o “•” y párrafos cortos. NO uses asteriscos, Markdown visible, encabezados con #, código ni HTML. Evita bloques densos y tablas salvo necesidad real.
- Nunca inventes fechas, horarios, tareas, notas, evaluaciones, acuerdos, nombres, páginas o decisiones institucionales.
- Distingue información general de información privada. No reveles notas, conducta, observaciones, correos, datos personales ni historial de otro estudiante.
- Existe un seguimiento docente interno de conducta y convivencia. El padre/madre/apoderado autenticado puede recibir la información pertinente de su hijo vinculado y el docente propietario puede consultar a sus estudiantes. El perfil estudiante NO puede acceder a ese seguimiento. Nunca reveles datos de compañeros a una familia. Nunca menciones al usuario el nombre de la fuente interna ni expliques su funcionamiento.
- Si el estudiante está identificado y el seguimiento conductual interno tiene exactamente 0 registros en el periodo consultado, no inventes incidencias. Evita afirmaciones absolutas sobre toda su conducta; comunica únicamente que no hay observaciones registradas en ese periodo, con lenguaje natural.
- Si el nombre no existe en ALUMNOS, NO concluyas que se portó bien: di que no pudiste identificar al estudiante en la matrícula.
- Esta ruta es de consulta para familias/estudiantes: es SOLO LECTURA. Nunca afirmes que modificaste Classroom, SIEweb, notas, correos o archivos.
- Si una pregunta requiere identidad verificada del estudiante y esa verificación no existe, explica que por privacidad esa información debe consultarse por el canal autenticado o directamente con el profesor.
- Por defecto, para información académica de Classroom y seguimiento actual, trabaja únicamente con el periodo desde el 09/09/2026 en adelante. Si el usuario pide información anterior sin indicar periodo, pregunta de qué trimestre, mes o fecha específica desea saber.\n- Prioriza, en este orden: datos dinámicos de Classroom cuando correspondan; seguimiento docente interno del estudiante autorizado cuando el rol lo permita; documentos oficiales de la base PROFE JOHNNY VIRTUAL; documentos institucionales recuperados de Drive; conocimiento general de Matemática.
- Si dos fuentes verificadas parecen contradecirse, menciona la discrepancia y no elijas una al azar. La fuente más reciente y específica tiene prioridad, pero señala el conflicto.
- Para preguntas sobre evaluación semanal, usa el horario real de la sección, la calendarización institucional y la regla de pasar a la siguiente sesión hábil cuando no se pueda evaluar.
- Cuando expliques Matemática, explica paso a paso y el porqué del procedimiento; no conviertas la respuesta en una lista interminable si la pregunta es sencilla.
- Si falta evidencia, dilo de forma directa: “No tengo esa información confirmada”.
- No expongas detalles privados del profesor ni de su familia.

Cuando uses información verificada, responde con la voz del Profe Johnny, de forma natural, humana y directa, no como un buscador ni como un sistema. No menciones bitácora, base de datos, API, contexto interno, motor, herramienta o proceso de consulta. Integra los hechos como si el propio Profe Johnny estuviera conversando con la familia o el estudiante.
""".strip()


def _now_lima() -> datetime:
    return datetime.now(ZoneInfo("America/Lima"))


def _norm(text: str) -> str:
    text = str(text or "").lower()
    text = re.sub(r"[^0-9a-záéíóúüñº.]+", " ", text)
    return " ".join(text.split())


def _terms(text: str) -> list[str]:
    out: list[str] = []
    seen: set[str] = set()
    for token in _norm(text).split():
        token = token.strip(".")
        if len(token) < 3 or token in STOPWORDS or token in seen:
            continue
        seen.add(token)
        out.append(token)
    return out[:8]


def _rate_ok(ip: str) -> bool:
    now = time.time()
    window = 900.0
    limit = 45
    with _rate_lock:
        q = _rate[ip]
        while q and now - q[0] > window:
            q.popleft()
        if len(q) >= limit:
            return False
        q.append(now)
        return True


def _extract_text(name: str, mime_type: str, raw: bytes) -> str:
    try:
        if mime_type.startswith("text/") or mime_type in {"application/json", "application/xml"}:
            return raw.decode("utf-8", errors="replace")
        if mime_type == "application/vnd.openxmlformats-officedocument.wordprocessingml.document" or name.lower().endswith(".docx"):
            doc = Document(BytesIO(raw))
            parts: list[str] = []
            for p in doc.paragraphs:
                if p.text.strip():
                    parts.append(p.text.strip())
            for table in doc.tables:
                for row in table.rows:
                    vals = [cell.text.strip() for cell in row.cells]
                    if any(vals):
                        parts.append(" | ".join(vals))
            return "\n".join(parts)
        if mime_type == "application/pdf" or name.lower().endswith(".pdf"):
            pdf = fitz.open(stream=raw, filetype="pdf")
            return "\n".join(page.get_text("text") for page in pdf)
    except Exception:
        return ""
    return ""


def _drive_list_folder(folder_id: str) -> list[dict[str, Any]]:
    files: list[dict[str, Any]] = []
    token: str | None = None
    while True:
        params: dict[str, Any] = {
            "q": f"'{folder_id}' in parents and trashed = false",
            "fields": "nextPageToken,files(id,name,mimeType,modifiedTime,createdTime,webViewLink)",
            "pageSize": 100,
            "orderBy": "name",
        }
        if token:
            params["pageToken"] = token
        data = _client._drive_request("GET", "files", params=params)
        files.extend(data.get("files") or [])
        token = data.get("nextPageToken")
        if not token:
            return files


def _load_file_text(file_id: str) -> tuple[dict[str, Any], str]:
    meta, raw, actual_mime = _client.download_drive_file(file_id)
    text = _extract_text(str(meta.get("name") or ""), str(actual_mime or meta.get("mimeType") or ""), raw)
    return meta, text


def _load_core_kb(force: bool = False) -> list[dict[str, Any]]:
    now = time.time()
    with _cache_lock:
        if not force and _cache.get("docs") and now - float(_cache.get("loaded_at") or 0) < CACHE_TTL_SECONDS:
            return list(_cache["docs"])

    docs: list[dict[str, Any]] = []
    error: str | None = None
    try:
        for item in _drive_list_folder(KB_FOLDER_ID):
            try:
                meta, text = _load_file_text(str(item["id"]))
                if not text.strip():
                    continue
                docs.append({
                    "id": item.get("id"),
                    "name": item.get("name"),
                    "mimeType": item.get("mimeType"),
                    "modifiedTime": item.get("modifiedTime"),
                    "text": text[:30000],
                })
            except Exception:
                continue
    except Exception as exc:
        error = f"{type(exc).__name__}: {exc}"

    with _cache_lock:
        if docs:
            _cache["docs"] = docs
            _cache["loaded_at"] = now
        _cache["error"] = error
        return list(_cache.get("docs") or [])


def _score_doc(doc: dict[str, Any], query: str) -> int:
    hay = _norm(f"{doc.get('name', '')} {doc.get('text', '')[:12000]}")
    score = 0
    for term in _terms(query):
        if term in hay:
            score += 3
        if term in _norm(str(doc.get("name") or "")):
            score += 5
    name = str(doc.get("name") or "")
    if name.startswith("01 -") or name.startswith("02 -"):
        score += 2
    if any(x in _norm(query) for x in ("horario", "examen", "evaluacion", "evaluación", "feriado", "clase", "semana")) and name.startswith("09 -"):
        score += 20
    if any(x in _norm(query) for x in ("tarea", "actividad", "curso", "libro", "pagina", "página")) and name.startswith("03 -"):
        score += 12
    if any(x in _norm(query) for x in ("evaluacion", "evaluación", "examen")) and name.startswith("04 -"):
        score += 12
    if any(x in _norm(query) for x in ("quien soy", "profe johnny", "profesor")) and name.startswith("01 -"):
        score += 10
    return score


def _core_context(query: str) -> tuple[str, list[str]]:
    docs = _load_core_kb()
    ranked = sorted(docs, key=lambda d: _score_doc(d, query), reverse=True)
    chosen = [d for d in ranked if _score_doc(d, query) > 0][:5]
    if not chosen:
        chosen = ranked[:3]
    blocks: list[str] = []
    names: list[str] = []
    total = 0
    for doc in chosen:
        text = str(doc.get("text") or "").strip()
        if not text:
            continue
        remaining = MAX_CONTEXT_CHARS - total
        if remaining <= 1000:
            break
        piece = text[: min(18000, remaining)]
        name = str(doc.get("name") or "Documento")
        blocks.append(f"### {name}\n{piece}")
        names.append(name)
        total += len(piece)
    return "\n\n".join(blocks), names


def _course_matches(course: dict[str, Any], grade: str) -> bool:
    hay = _norm(" ".join(str(course.get(k) or "") for k in ("name", "section", "descriptionHeading", "description")))
    if "matem" not in hay:
        return False
    if grade.startswith("2"):
        markers = ("2º", "2.º", "2do", "2 do", "2 secundaria", "segundo")
    else:
        markers = ("5º", "5.º", "5to", "5 to", "5 secundaria", "quinto")
    return any(_norm(m) in hay for m in markers) or re.search(rf"(^|\D){grade[0]}(\D|$)", hay) is not None


def _format_due(item: dict[str, Any]) -> str:
    d = item.get("dueDate") or {}
    t = item.get("dueTime") or {}
    if not d:
        return "sin fecha límite registrada"
    base = f"{int(d.get('day', 0)):02d}/{int(d.get('month', 0)):02d}/{int(d.get('year', 0)):04d}"
    if t:
        base += f" {int(t.get('hours', 0)):02d}:{int(t.get('minutes', 0)):02d}"
    return base


def _classroom_context(grade: str, query: str) -> tuple[str, list[str]]:
    wanted = grade.strip()[:1] if grade.strip()[:1] in {"2", "5"} else ""
    if not wanted:
        return "", []
    try:
        courses = [c for c in _client.list_courses(active_only=True) if _course_matches(c, wanted)]
    except Exception:
        return "", []

    blocks: list[str] = []
    names: list[str] = []
    for course in courses[:4]:
        cid = str(course.get("id") or "")
        cname = " - ".join(x for x in [str(course.get("name") or ""), str(course.get("section") or "")] if x).strip(" -")
        if not cid:
            continue
        lines = [f"CURSO: {cname} (Classroom)"]
        try:
            work = _client.list_coursework(cid, include_drafts=False)[:MAX_CLASSROOM_ITEMS_PER_COURSE]
            if work:
                lines.append("TAREAS/PREGUNTAS RECIENTES:")
                for w in work:
                    lines.append(
                        f"- {w.get('title')} | estado={w.get('state')} | tipo={w.get('workType')} | límite={_format_due(w)} | puntos={w.get('maxPoints')} | actualizado={w.get('updateTime')}"
                    )
        except Exception:
            pass
        try:
            mats = _client.list_coursework_materials(cid, include_drafts=False)[:10]
            if mats:
                lines.append("MATERIALES RECIENTES:")
                for m in mats:
                    lines.append(f"- {m.get('title')} | estado={m.get('state')} | actualizado={m.get('updateTime')}")
        except Exception:
            pass
        try:
            anns = _client.list_announcements(cid, include_drafts=False)[:8]
            if anns:
                lines.append("AVISOS RECIENTES DE CLASSROOM:")
                for a in anns:
                    text = str(a.get("text") or "").replace("\n", " ")[:280]
                    lines.append(f"- {text} | actualizado={a.get('updateTime')}")
        except Exception:
            pass
        blocks.append("\n".join(lines))
        names.append(cname or cid)
    return "\n\n".join(blocks), names


def _drive_search_context(query: str) -> tuple[str, list[str]]:
    terms = _terms(query)[:4]
    if not terms:
        return "", []
    clauses = [f"fullText contains '{t.replace(chr(39), '')}'" for t in terms]
    q = "trashed = false and (" + " or ".join(clauses) + ")"
    try:
        data = _client._drive_request(
            "GET",
            "files",
            params={
                "q": q,
                "fields": "files(id,name,mimeType,modifiedTime,createdTime,webViewLink,parents)",
                "pageSize": 20,
                "orderBy": "modifiedTime desc",
            },
        )
    except Exception:
        return "", []

    core_ids = {str(d.get("id")) for d in _load_core_kb()}
    blocks: list[str] = []
    names: list[str] = []
    for item in data.get("files") or []:
        if str(item.get("id")) in core_ids:
            continue
        mime = str(item.get("mimeType") or "")
        if mime == "application/vnd.google-apps.folder":
            continue
        try:
            meta, text = _load_file_text(str(item["id"]))
        except Exception:
            continue
        text = " ".join(str(text).split())
        if not text:
            continue
        name = str(item.get("name") or meta.get("name") or "Documento")
        blocks.append(f"### {name} (Drive, modificado {item.get('modifiedTime')})\n{text[:6500]}")
        names.append(name)
        if len(blocks) >= MAX_DRIVE_RESULTS:
            break
    return "\n\n".join(blocks), names



def _declared_student_hint(message: str) -> str:
    """Extrae una identidad declarada en primera persona: soy / me llamo / mi nombre es."""
    text = str(message or "").strip()
    m = re.search(r"\b(?:soy|me\s+llamo|mi\s+nombre\s+es)\s+(.+)$", text, flags=re.IGNORECASE)
    if not m:
        return ""
    tail = m.group(1).strip()
    tail = re.split(
        r"[,.;?!]|\s+y\s+(?:quiero|quisiera|necesito|deseo|tengo|puedo|me)\b",
        tail,
        maxsplit=1,
        flags=re.IGNORECASE,
    )[0]
    tokens = re.findall(r"[A-Za-zÁÉÍÓÚÜÑáéíóúüñ'’-]+", tail)
    return " ".join(tokens[:6]).strip()


def _redact_other_students(text: str, target_name: str) -> str:
    out = str(text or "")
    try:
        students = _bitacora_load_students()
    except Exception:
        students = []
    for row in students:
        name = str(row.get("nombre") or "").strip()
        if not name or _norm(name) == _norm(target_name):
            continue
        out = re.sub(re.escape(name), "otro estudiante", out, flags=re.IGNORECASE)
    return out


def _bitacora_memory_context(
    message: str,
    grade: str,
    student_hint: str = "",
    section: str = "",
) -> tuple[str, dict[str, Any]]:
    """Carga memoria de bitácora cuando el propio estudiante declara su identidad."""
    hint = str(student_hint or "").strip() or _declared_student_hint(message)
    meta: dict[str, Any] = {
        "requested": bool(hint),
        "resolved": False,
        "records": 0,
        "status": "not_requested" if not hint else "unresolved",
    }
    if not hint:
        return "", meta

    data: dict[str, Any] = {"student": hint}
    if str(grade).startswith("2") or str(grade).startswith("5"):
        data["grado"] = str(grade)[:1]
    if str(section or "").strip():
        data["seccion"] = str(section).strip()

    try:
        resolved = _bitacora_resolve_student(data)
    except Exception as exc:
        meta["status"] = "error"
        meta["error"] = f"{type(exc).__name__}: {exc}"
        return "", meta

    if resolved.get("status") != "resolved":
        meta["status"] = str(resolved.get("status") or "unresolved")
        return (
            "## BITÁCORA DOCENTE\n"
            "La persona declaró un nombre, pero no fue posible resolverlo de forma única en la pestaña ALUMNOS. "
            "No interpretes ausencia en matrícula como buena conducta y no inventes información."
        ), meta

    student = dict(resolved.get("student") or {})
    target_name = str(student.get("nombre") or hint)
    meta["resolved"] = True
    meta["status"] = "resolved"

    try:
        hist = _bitacora_history({"student": str(student.get("alumno_id") or hint), "limit": 40})
    except Exception as exc:
        meta["status"] = "error"
        meta["error"] = f"{type(exc).__name__}: {exc}"
        return "", meta

    records = list(hist.get("bitacora") or [])
    meta["records"] = int((hist.get("counts") or {}).get("bitacora") or len(records))
    if meta["records"] == 0:
        meta["status"] = "no_records_good_behavior"
        return (
            "## BITÁCORA DOCENTE — MEMORIA DEL PROPIO ESTUDIANTE\n"
            f"Estudiante resuelto en ALUMNOS: {target_name}.\n"
            "Registros conductuales encontrados: 0.\n"
            "REGLA DEL DOCENTE: al estar identificado en ALUMNOS y no tener registros en BITÁCORA, "
            "se considera que no existen incidencias u observaciones conductuales registradas y puede comunicarse "
            "que, según la bitácora disponible, se ha portado bien o ha mantenido un comportamiento adecuado."
        ), meta

    lines = [
        "## BITÁCORA DOCENTE — MEMORIA DEL PROPIO ESTUDIANTE",
        f"Estudiante resuelto en ALUMNOS: {target_name}.",
        f"Registros conductuales totales: {meta['records']}.",
        "Usa estos registros solo para responder al propio estudiante. No reveles información de compañeros ni nombres de terceros.",
    ]
    for row in records[-12:]:
        date = str(row.get("Fecha") or "")
        kind = str(row.get("Tipo de registro") or "")
        category = str(row.get("Categoría") or "")
        description = _redact_other_students(str(row.get("Descripción objetiva") or ""), target_name)
        impact = _redact_other_students(str(row.get("Impacto en aprendizaje/convivencia") or ""), target_name)
        action = _redact_other_students(str(row.get("Acción docente") or ""), target_name)
        follow = _redact_other_students(str(row.get("Seguimiento") or ""), target_name)
        lines.append(
            f"- {date} | {kind} | {category} | Hecho: {description[:700]} | "
            f"Impacto: {impact[:400]} | Acción docente: {action[:400]} | Seguimiento: {follow[:400]}"
        )
    meta["status"] = "records_loaded"
    return "\n".join(lines), meta

def _needs_drive_search(message: str) -> bool:
    q = _norm(message)
    markers = (
        "programacion", "programación", "sesion", "sesión", "unidad", "descriptor",
        "documento", "drive", "libro", "pagina", "página", "material", "ficha",
        "calendario", "calendarizacion", "calendarización", "tema", "competencia",
        "desempeno", "desempeño", "trimestre", "quincena", "planificacion", "planificación",
    )
    return any(_norm(m) in q for m in markers)


def _looks_sensitive(message: str) -> bool:
    q = _norm(message)
    patterns = (
        "mi nota", "mis notas", "nota de", "calificacion de", "calificación de", "conducta de",
        "observacion de", "observación de", "bitacora", "bitácora", "correo de", "padres de",
        "porque tiene c", "por que tiene c", "nivel de logro", "desempeno de", "desempeño de",
    )
    return any(_norm(p) in q for p in patterns)


def _openai_reply(message: str, grade: str, context: str) -> str:
    if not OPENAI_API_KEY:
        return ""
    payload = {
        "model": MODEL,
        "instructions": BASE_INSTRUCTIONS,
        "input": (
            f"FECHA/HORA ACTUAL EN LIMA: {_now_lima().isoformat()}\n"
            f"GRADO SELECCIONADO EN LA APP: {grade}\n\n"
            f"PREGUNTA DEL USUARIO:\n{message}\n\n"
            f"FUENTES VERIFICADAS DISPONIBLES:\n{context}"
        ),
        "max_output_tokens": 1100,
    }
    response = requests.post(
        "https://api.openai.com/v1/responses",
        headers={"Authorization": f"Bearer {OPENAI_API_KEY}", "Content-Type": "application/json"},
        json=payload,
        timeout=45,
    )
    if not response.ok:
        raise RuntimeError(f"OpenAI HTTP {response.status_code}: {response.text[:500]}")
    data = response.json()
    direct = str(data.get("output_text") or "").strip()
    if direct:
        return direct
    chunks: list[str] = []
    for item in data.get("output") or []:
        if item.get("type") != "message":
            continue
        for content in item.get("content") or []:
            if content.get("type") in {"output_text", "text"} and content.get("text"):
                chunks.append(str(content["text"]))
    return "\n".join(chunks).strip()


def _fallback(message: str, grade: str, core_context: str) -> str:
    q = _norm(message)
    schedules = {
        "2": "2.º A: lunes 10:10–10:55 y 11:15–12:00, martes 14:20–15:35 y jueves 12:00–13:30. 2.º B: martes 09:25–10:55, jueves 10:10–10:55 y 11:15–12:00, y viernes 10:10–10:55 y 11:15–12:00.",
        "5": "5.º A: lunes 12:00–13:30, miércoles 14:20–15:35 y viernes 12:00–13:30. 5.º B: lunes, jueves y viernes de 08:40–10:10.",
    }
    if "horario" in q or "clase" in q or "que dia" in q or "qué dia" in q or "qué día" in q:
        return schedules.get(grade[:1], schedules["2"] + " " + schedules["5"])
    if _looks_sensitive(message):
        return (
            "Esa consulta puede incluir información académica o personal de un estudiante. Por privacidad, "
            "PROFE JOHNNY APP solo la mostrará cuando implementemos la identificación verificada de la familia/estudiante. "
            "Mientras tanto, consulta esa información directamente con el profesor Johnny o por el canal oficial."
        )
    return (
        "Ya tengo acceso a la base documental verificada del Profe Johnny y a la información general del curso, "
        "pero el motor de IA del servidor todavía necesita quedar habilitado para responder esta consulta de forma completa."
    )


def _status_payload() -> dict[str, Any]:
    docs = _load_core_kb()
    return {
        "ok": True,
        "service": "PROFE JOHNNY APP Brain",
        "model": MODEL,
        "openai_configured": bool(OPENAI_API_KEY),
        "knowledge_folder_configured": bool(KB_FOLDER_ID),
        "knowledge_documents_loaded": len(docs),
        "knowledge_documents": [str(d.get("name") or "") for d in docs],
        "classroom_oauth_configured": bool(settings.google_client_id and settings.google_client_secret and settings.google_refresh_token),
        "bitacora_memory_configured": True,
        "chat_engine_version": "2026-09-10-fast1",
        "privacy_mode": "family_student_read_only",
        "updated_at": _now_lima().isoformat(),
        "cache_error": _cache.get("error"),
    }


def install(mcp: Any) -> None:
    @mcp.custom_route("/profe-johnny/v1/status", methods=["GET"])
    async def profe_johnny_status(request: Request):
        try:
            return JSONResponse(_status_payload())
        except Exception as exc:
            return JSONResponse({"ok": False, "error": f"{type(exc).__name__}: {exc}"}, status_code=500)

    @mcp.custom_route("/profe-johnny/v1/chat", methods=["POST"])
    async def profe_johnny_chat(request: Request):
        ip = str(getattr(request.client, "host", "unknown") or "unknown")
        if not _rate_ok(ip):
            return JSONResponse({"reply": "Se alcanzó temporalmente el límite de consultas. Inténtalo nuevamente en unos minutos."}, status_code=429)
        try:
            body = await request.json()
        except Exception:
            return JSONResponse({"reply": "No pude leer la consulta enviada."}, status_code=400)
        if not isinstance(body, dict):
            return JSONResponse({"reply": "La consulta enviada no tiene un formato válido."}, status_code=400)

        message = str(body.get("message") or "").strip()
        grade = str(body.get("grade") or "").strip()
        student_hint = str(body.get("student") or "").strip()
        section = str(body.get("section") or "").strip()
        if len(message) > MAX_MESSAGE_CHARS:
            return JSONResponse({"reply": "La consulta es demasiado larga. Resume tu pregunta y vuelve a enviarla."}, status_code=400)
        if not message:
            return JSONResponse({"reply": "Escribe tu consulta para poder ayudarte."}, status_code=400)
        if grade.startswith("2"):
            grade = "2.º año"
        elif grade.startswith("5"):
            grade = "5.º año"
        else:
            grade = "grado no especificado"

        # Recupera fuentes independientes en paralelo. Drive se consulta solo cuando
        # la pregunta realmente lo requiere; evita varios segundos de latencia en consultas simples.
        with ThreadPoolExecutor(max_workers=4) as pool:
            core_future = pool.submit(_core_context, message)
            classroom_future = pool.submit(_classroom_context, grade, message)
            bitacora_future = pool.submit(_bitacora_memory_context, message, grade, student_hint, section)
            drive_future = pool.submit(_drive_search_context, message) if _needs_drive_search(message) else None
            core, core_sources = core_future.result()
            classroom, classroom_sources = classroom_future.result()
            bitacora, bitacora_meta = bitacora_future.result()
            if drive_future is not None:
                drive, drive_sources = drive_future.result()
            else:
                drive, drive_sources = "", []

        source_blocks = []
        if bitacora:
            source_blocks.append(bitacora)
        if classroom:
            source_blocks.append("## CLASSROOM (dinámico)\n" + classroom)
        if core:
            source_blocks.append("## BASE PROFE JOHNNY VIRTUAL\n" + core)
        if drive:
            source_blocks.append("## DRIVE INSTITUCIONAL / MATERIALES RECUPERADOS\n" + drive)
        context = "\n\n".join(source_blocks)[:MAX_CONTEXT_CHARS]

        if _looks_sensitive(message) and not bitacora_meta.get("resolved"):
            context += (
                "\n\n## RESTRICCIÓN DE PRIVACIDAD\n"
                "No hay una identidad propia resuelta para esta consulta. No cargues ni reveles notas, conducta, bitácora, mensajes ni datos privados de otro estudiante."
            )

        try:
            reply = _openai_reply(message, grade, context) if OPENAI_API_KEY else ""
        except Exception as exc:
            print(f"PROFE JOHNNY APP OpenAI error: {type(exc).__name__}: {exc}", flush=True)
            reply = ""
        if not reply:
            if bitacora_meta.get("status") == "no_records_good_behavior":
                reply = (
                    "No tienes incidencias ni observaciones conductuales registradas en la bitácora. "
                    "Según la bitácora disponible, has mantenido un buen comportamiento. ¡Sigue así!"
                )
            else:
                reply = _fallback(message, grade, core)

        return JSONResponse({
            "reply": reply,
            "meta": {
                "grade": grade,
                "source_count": len(core_sources) + len(classroom_sources) + len(drive_sources),
                "core_sources": core_sources,
                "classroom_sources": classroom_sources,
                "drive_sources": drive_sources,
                "bitacora_memory": bitacora_meta,
                "private_student_data_used": bool(bitacora_meta.get("resolved") and bitacora_meta.get("records", 0) > 0),
                "updated_at": _now_lima().isoformat(),
            },
        })

    print("PROFE JOHNNY APP: rutas /profe-johnny/v1/status y /chat instaladas.", flush=True)
