from __future__ import annotations

import json
import re
import unicodedata
from dataclasses import asdict, dataclass
from datetime import datetime
from pathlib import Path
from typing import Any
from urllib.parse import urljoin

from playwright.sync_api import Page


@dataclass
class AttachmentEvidence:
    label: str
    url: str
    screenshot: str | None
    title: str
    text_sample: str
    error: str | None = None


@dataclass
class StudentEvidence:
    student: str
    detail_url: str
    screenshot: str
    page_title: str
    visible_text_sample: str
    attachments: list[AttachmentEvidence]


_LAST_PAGE: Page | None = None
_INSTALLED = False
_ORIGINAL_INSPECT = None
_ORIGINAL_PRINT_SUMMARY = None


def _norm(value: Any) -> str:
    text = unicodedata.normalize("NFD", str(value or ""))
    text = "".join(ch for ch in text if unicodedata.category(ch) != "Mn")
    return " ".join(text.lower().split())


def _safe_text(locator, timeout: int = 500) -> str:
    try:
        return " ".join(locator.inner_text(timeout=timeout).split())
    except Exception:
        return ""


def _body_text(page: Page, max_chars: int = 12000) -> str:
    try:
        text = page.locator("body").inner_text(timeout=1500)
    except Exception:
        return ""
    return "\n".join(line.strip() for line in text.splitlines() if line.strip())[:max_chars]


def _safe_title(page: Page) -> str:
    try:
        return page.title().strip()
    except Exception:
        return ""


def _save_json(path: Path, payload: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")


def _safe_screenshot(page: Page, path: Path) -> str:
    path.parent.mkdir(parents=True, exist_ok=True)
    try:
        page.screenshot(path=str(path), full_page=False)
        return str(path)
    except Exception:
        return ""


def _wait_settle(page: Page, ms: int = 900) -> None:
    try:
        page.wait_for_timeout(ms)
    except Exception:
        pass


def _visible_links(page: Page, limit: int = 600) -> list[dict[str, str]]:
    result: list[dict[str, str]] = []
    seen: set[tuple[str, str]] = set()
    try:
        locators = page.locator("a[href]").all()[:limit]
    except Exception:
        return result
    for locator in locators:
        try:
            if not locator.is_visible(timeout=100):
                continue
            href = locator.get_attribute("href") or ""
            if not href:
                continue
            text = _safe_text(locator, 250)
            absolute = urljoin(page.url, href)
            key = (text, absolute)
            if key in seen:
                continue
            seen.add(key)
            result.append({"text": text[:500], "href": absolute[:2000]})
        except Exception:
            continue
    return result


def _choose_from(items: list[dict[str, str]], prompt_func, label: str) -> dict[str, str] | None:
    if not items:
        return None
    if len(items) == 1:
        return items[0]
    print(f"\n{label}:")
    for index, item in enumerate(items[:30], start=1):
        print(f"  {index}. {item.get('text') or '(sin texto)'}")
    raw = prompt_func(f"Elige [1-{min(len(items),30)}] o ENTER para cancelar: ").strip()
    if not raw:
        return None
    try:
        pos = int(raw) - 1
    except Exception:
        return None
    if 0 <= pos < min(len(items), 30):
        return items[pos]
    return None


def _find_course(page: Page, query: str, prompt_func) -> dict[str, str] | None:
    wanted = _norm(query)
    links = [item for item in _visible_links(page) if "/c/" in item["href"]]
    if wanted:
        matches = [item for item in links if wanted in _norm(item.get("text"))]
    else:
        matches = links
    # Un mismo curso puede aparecer varias veces en el DOM. Deduplicamos por URL.
    unique: dict[str, dict[str, str]] = {}
    for item in matches:
        unique[item["href"].split("?")[0]] = item
    return _choose_from(list(unique.values()), prompt_func, "Cursos coincidentes")


def _click_classwork(page: Page) -> bool:
    names = ["Trabajo de clase", "Classwork"]
    for name in names:
        for strategy in (
            lambda: page.get_by_role("link", name=name, exact=True),
            lambda: page.get_by_text(name, exact=True),
        ):
            try:
                loc = strategy()
                if loc.count() and loc.first.is_visible(timeout=400):
                    loc.first.click(timeout=2500)
                    _wait_settle(page, 1100)
                    return True
            except Exception:
                continue
    # Fallback: los enlaces de classwork suelen usar /w/.
    for item in _visible_links(page):
        if "/w/" in item["href"]:
            try:
                page.goto(item["href"], wait_until="domcontentloaded", timeout=15000)
                _wait_settle(page, 900)
                return True
            except Exception:
                continue
    return False


def _find_assignment(page: Page, query: str, prompt_func) -> dict[str, str] | None:
    wanted = _norm(query)
    links = [item for item in _visible_links(page) if "/a/" in item["href"]]
    matches = [item for item in links if wanted in _norm(item.get("text"))] if wanted else links
    unique: dict[str, dict[str, str]] = {}
    for item in matches:
        unique[item["href"].split("?")[0]] = item
    return _choose_from(list(unique.values()), prompt_func, "Actividades coincidentes")


def _open_student_work(page: Page) -> None:
    # Classroom cambia los textos según idioma/estado. Probamos únicamente controles
    # docentes explícitos; nunca botones de enviar/devolver/calificar en esta fase.
    candidates = [
        "Ver tarea", "View assignment", "Trabajo de los alumnos", "Trabajo de alumnos",
        "Student work", "Ver todos", "View all",
    ]
    for text in candidates:
        for role in ("link", "button"):
            try:
                loc = page.get_by_role(role, name=text, exact=False)
                if loc.count() and loc.first.is_visible(timeout=300):
                    loc.first.click(timeout=2500)
                    _wait_settle(page, 1000)
                    return
            except Exception:
                continue


def _student_links(page: Page) -> list[dict[str, str]]:
    links = []
    for item in _visible_links(page, 1000):
        if "/student/" not in item["href"]:
            continue
        text = item.get("text") or ""
        if not text:
            continue
        links.append(item)
    unique: dict[str, dict[str, str]] = {}
    for item in links:
        unique[item["href"].split("?")[0]] = item
    return list(unique.values())


def _attachment_links(page: Page) -> list[dict[str, str]]:
    out: list[dict[str, str]] = []
    for item in _visible_links(page, 700):
        href = item["href"].lower()
        text = _norm(item.get("text"))
        if any(host in href for host in (
            "drive.google.com", "docs.google.com", "slides.google.com", "sheets.google.com",
        )) or re.search(r"\.(pdf|png|jpe?g|webp)(?:$|[?#])", href):
            out.append(item)
        elif any(token in text for token in ("pdf", "jpg", "jpeg", "png", "archivo", "file", "adjunto")):
            out.append(item)
    unique: dict[str, dict[str, str]] = {}
    for item in out:
        unique[item["href"]] = item
    return list(unique.values())


def _inspect_attachment(page: Page, item: dict[str, str], folder: Path, index: int) -> AttachmentEvidence:
    label = item.get("text") or f"Adjunto {index}"
    url = item.get("href") or ""
    tab = None
    try:
        tab = page.context.new_page()
        tab.goto(url, wait_until="domcontentloaded", timeout=18000)
        _wait_settle(tab, 1200)
        shot = folder / f"adjunto_{index:02d}.png"
        screenshot = _safe_screenshot(tab, shot)
        return AttachmentEvidence(
            label=label,
            url=tab.url or url,
            screenshot=screenshot or None,
            title=_safe_title(tab),
            text_sample=_body_text(tab, 7000),
        )
    except Exception as exc:
        return AttachmentEvidence(
            label=label,
            url=url,
            screenshot=None,
            title="",
            text_sample="",
            error=str(exc)[:500],
        )
    finally:
        if tab is not None:
            try:
                tab.close()
            except Exception:
                pass


def _inspect_student(page: Page, item: dict[str, str], root: Path, position: int) -> StudentEvidence:
    detail_url = item.get("href") or ""
    student = item.get("text") or f"Estudiante {position}"
    page.goto(detail_url, wait_until="domcontentloaded", timeout=18000)
    _wait_settle(page, 1200)

    safe_name = re.sub(r"[^A-Za-z0-9_-]+", "_", student).strip("_")[:60] or f"student_{position}"
    folder = root / f"{position:02d}_{safe_name}"
    folder.mkdir(parents=True, exist_ok=True)
    screenshot = _safe_screenshot(page, folder / "entrega.png")

    attachments = []
    for index, attachment in enumerate(_attachment_links(page)[:12], start=1):
        attachments.append(_inspect_attachment(page, attachment, folder, index))

    evidence = StudentEvidence(
        student=student,
        detail_url=page.url,
        screenshot=screenshot,
        page_title=_safe_title(page),
        visible_text_sample=_body_text(page, 10000),
        attachments=attachments,
    )
    _save_json(folder / "evidencia.json", asdict(evidence))
    return evidence


def run_visual_review(page: Page, evidence_dir: Path, prompt_func) -> None:
    print("\n============================================================")
    print(" SIEROOM — CLASSROOM: REVISIÓN VISUAL FASE 1 (SOLO LECTURA)")
    print("============================================================")
    print("Esta fase navega Classroom, abre entregas y adjuntos y guarda evidencia visual.")
    print("NO publica comentarios, NO escribe notas y NO devuelve trabajos todavía.")

    if "classroom.google.com" not in page.url.lower():
        print("No estás en una pestaña real de Classroom.")
        return

    # Empezar desde Inicio hace la búsqueda de curso predecible, pero sin cerrar la sesión.
    try:
        page.goto("https://classroom.google.com/u/0/h", wait_until="domcontentloaded", timeout=18000)
    except Exception:
        pass
    _wait_settle(page, 1000)

    course_query = prompt_func("Curso/sección a revisar (ej. MATE 2DO - B): ").strip()
    if not course_query:
        print("Cancelado.")
        return
    course = _find_course(page, course_query, prompt_func)
    if not course:
        print("No pude localizar de forma única ese curso en la pantalla de Classroom.")
        return

    print(f"Curso elegido: {course.get('text')}")
    page.goto(course["href"], wait_until="domcontentloaded", timeout=18000)
    _wait_settle(page, 900)
    if not _click_classwork(page):
        print("No pude abrir 'Trabajo de clase' de forma segura.")
        return

    task_query = prompt_func("Título o parte del título de la tarea: ").strip()
    if not task_query:
        print("Cancelado.")
        return
    task = _find_assignment(page, task_query, prompt_func)
    if not task:
        print("No pude localizar de forma única esa tarea en Trabajo de clase.")
        return

    print(f"Tarea elegida: {task.get('text')}")
    page.goto(task["href"], wait_until="domcontentloaded", timeout=18000)
    _wait_settle(page, 1000)
    _open_student_work(page)

    students = _student_links(page)
    if not students:
        # Una vista puede requerir un segundo clic a Trabajo de alumnos.
        _open_student_work(page)
        students = _student_links(page)
    if not students:
        print("No se detectaron enlaces individuales de estudiantes todavía.")
        print(f"URL actual: {page.url}")
        return

    print(f"Estudiantes/enlaces de entrega detectados: {len(students)}")
    for index, item in enumerate(students[:12], start=1):
        print(f"  {index}. {item.get('text')}")

    raw_count = prompt_func(
        f"¿Cuántas entregas inspeccionar ahora? [1-{len(students)}] (ENTER=2): "
    ).strip()
    try:
        count = int(raw_count) if raw_count else min(2, len(students))
    except Exception:
        count = min(2, len(students))
    count = max(1, min(count, len(students)))

    stamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    root = evidence_dir / "classroom_visual" / stamp
    root.mkdir(parents=True, exist_ok=True)
    task_page_url = page.url
    results: list[StudentEvidence] = []

    for position, student in enumerate(students[:count], start=1):
        print(f"\n[{position}/{count}] Inspeccionando: {student.get('text')}")
        try:
            result = _inspect_student(page, student, root, position)
            results.append(result)
            print(f"  Captura: {result.screenshot}")
            print(f"  Adjuntos detectados/abiertos: {len(result.attachments)}")
        except Exception as exc:
            print(f"  AVISO: no se pudo completar esta entrega: {exc}")
        finally:
            # Volvemos a la lista sin tocar acciones de entrega.
            try:
                page.goto(task_page_url, wait_until="domcontentloaded", timeout=18000)
                _wait_settle(page, 800)
                _open_student_work(page)
            except Exception:
                pass

    summary = {
        "mode": "classroom_visual_read_only_phase_1",
        "course": course,
        "task": task,
        "students_detected": len(students),
        "students_inspected": len(results),
        "results": [asdict(item) for item in results],
    }
    summary_path = root / "resumen.json"
    _save_json(summary_path, summary)

    print("\n============================================================")
    print(" REVISIÓN VISUAL FASE 1 TERMINADA")
    print("============================================================")
    print(f"Entregas inspeccionadas: {len(results)}/{count}")
    print(f"Evidencia maestra: {summary_path}")
    print("No se publicó ningún comentario, nota ni devolución.")


def install(legacy_module) -> None:
    """Integra la revisión visual en el bucle estable sin reescribir main.py."""
    global _INSTALLED, _ORIGINAL_INSPECT, _ORIGINAL_PRINT_SUMMARY
    if _INSTALLED:
        return

    _ORIGINAL_INSPECT = legacy_module.inspect_semantics
    _ORIGINAL_PRINT_SUMMARY = legacy_module.print_semantic_summary

    def inspect_wrapper(page: Page):
        global _LAST_PAGE
        report = _ORIGINAL_INSPECT(page)
        try:
            if report.site == "classroom":
                _LAST_PAGE = page
        except Exception:
            pass
        return report

    def print_wrapper(semantic):
        _ORIGINAL_PRINT_SUMMARY(semantic)
        if getattr(semantic, "site", "") != "classroom":
            return
        page = _LAST_PAGE
        if page is None or page.is_closed():
            return
        answer = legacy_module.prompt(
            "\nR = iniciar revisión visual de una tarea (SOLO LECTURA) | ENTER = continuar: "
        ).strip().lower()
        if answer != "r":
            return
        try:
            run_visual_review(page, legacy_module.app_data_root() / "evidence", legacy_module.prompt)
        except Exception as exc:
            print(f"\nAVISO: la revisión visual se detuvo de forma segura: {exc}")
            print("No se publicó ningún comentario, nota ni devolución.")

    legacy_module.inspect_semantics = inspect_wrapper
    legacy_module.print_semantic_summary = print_wrapper
    _INSTALLED = True
