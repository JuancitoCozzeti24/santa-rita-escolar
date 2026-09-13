from __future__ import annotations

from pathlib import Path
from typing import Any
import argparse
import json

from classroom import ClassroomClient
from .browser import SchoolBrowser
from .classroom_flow import ClassroomFlow, StudentWork
from .classroom_review import StudentReview, SubmissionReviewer
from .journal import OperationJournal
from .runner import AgentRunner
from .settings import DesktopSettings


class VisualCommentPublisher:
    def __init__(self, browser: SchoolBrowser, runner: AgentRunner) -> None:
        self.browser = browser
        self.runner = runner

    def __call__(self, submission_url: str, student_name: str, feedback: str) -> bool:
        if not submission_url.startswith("https://classroom.google.com/"):
            raise RuntimeError("La entrega no tiene una URL válida de Classroom.")
        self.browser.page("classroom").goto(submission_url, wait_until="domcontentloaded")
        goal = (
            f"Trabaja SOLO en la entrega actualmente abierta de {student_name}. "
            "Localiza Comentarios privados. Comprueba si ya existe exactamente el comentario indicado; "
            "si existe, termina sin publicarlo otra vez. Si no existe, publícalo una sola vez. "
            "No pongas nota, no devuelvas la entrega y no modifiques ningún otro dato. Después de publicar, "
            f"verifica visualmente que aparece en el hilo privado.\n\nCOMENTARIO EXACTO:\n{feedback}"
        )
        self.runner.run_with_browser(self.browser, "classroom", goal, max_steps=45)
        return True


def _review_target(batch: Any, student: StudentWork) -> dict[str, object]:
    return {
        "course_id": str(batch.course["id"]),
        "coursework_id": str(batch.coursework["id"]),
        "submission_id": student.submission_id,
        "submission_updated_at": student.updated_at,
    }


def main() -> None:
    parser = argparse.ArgumentParser(description="Revisión completa y reanudable de una tarea de Classroom")
    parser.add_argument("--course", required=True, help="ID, nombre o sección exacta del curso")
    parser.add_argument("--task", required=True, help="ID o título exacto de la tarea")
    parser.add_argument("--criteria-file", help="Texto con ejercicios esperados, solucionario o criterios")
    parser.add_argument("--apply", action="store_true", help="Publica comentario, nota y devolución")
    parser.add_argument("--include-returned", action="store_true", help="Incluye entregas ya devueltas")
    args = parser.parse_args()

    settings = DesktopSettings.from_env()
    settings.data_dir.mkdir(parents=True, exist_ok=True)
    journal = OperationJournal(settings.data_dir / "operations.sqlite3")
    classroom = ClassroomClient()
    flow = ClassroomFlow(classroom, journal)
    batch = flow.prepare(args.course, args.task)
    summary = flow.batch_summary(batch)
    print(json.dumps({k: v for k, v in summary.items() if k != "students"}, ensure_ascii=False, indent=2))

    criteria = Path(args.criteria_file).read_text(encoding="utf-8") if args.criteria_file else ""
    reviewer = SubmissionReviewer(settings, classroom)
    reviews: list[tuple[StudentWork, StudentReview]] = []
    for student in batch.students:
        if student.attachment_count == 0:
            print(f"OMITIDO sin archivo: {student.student_name}")
            continue
        if student.state == "RETURNED" and not args.include_returned:
            print(f"OMITIDO ya devuelto: {student.student_name}")
            continue
        target = _review_target(batch, student)
        cached, inserted = journal.reserve("classroom_review", target, {"criteria": criteria})
        if not inserted and cached.status == "completed" and cached.result:
            review = StudentReview.from_public(cached.result)
            print(f"REVISIÓN REUTILIZADA: {student.student_name} — {review.score}/20")
        else:
            journal.transition(cached.key, "executing")
            try:
                raw_submission = classroom.get_submission(
                    str(batch.course["id"]), str(batch.coursework["id"]), student.submission_id
                )
                review = reviewer.review(
                    course_id=str(batch.course["id"]), coursework=batch.coursework,
                    submission=raw_submission, student_name=student.student_name, criteria=criteria,
                )
            except Exception as exc:
                journal.transition(cached.key, "failed", {"error": str(exc)})
                print(f"ERROR de revisión: {student.student_name}: {exc}")
                continue
            journal.transition(cached.key, "completed", review.public())
            print(f"REVISADO: {student.student_name} — {review.score}/20 ({review.level})")
        reviews.append((student, review))

    report = {
        "summary": summary,
        "reviews": [{"student": student.student_name, **review.public()} for student, review in reviews],
    }
    report_path = settings.data_dir / f"classroom-review-{batch.coursework['id']}.json"
    report_path.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"Informe previo: {report_path}")
    if not args.apply:
        print("No se modificó Classroom. Revisa el informe y vuelve a ejecutar con --apply para publicar.")
        return

    runner = AgentRunner(settings, confirm=lambda _: True)
    with SchoolBrowser(settings) as browser:
        publisher = VisualCommentPublisher(browser, runner)
        for student, review in reviews:
            try:
                result = flow.apply_review(batch, student, review, publisher)
                print(f"APLICADO Y VERIFICADO: {student.student_name}: {json.dumps(result, ensure_ascii=False)}")
            except Exception as exc:
                print(f"DETENIDO en {student.student_name}: {exc}")
                print("Repite el comando para reanudar; no se repetirán operaciones verificadas.")
                raise SystemExit(1) from exc


if __name__ == "__main__":
    main()
