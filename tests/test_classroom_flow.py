from pathlib import Path
from tempfile import TemporaryDirectory
import unittest

from desktop_agent.classroom_flow import ClassroomFlow
from desktop_agent.classroom_review import ExerciseFinding, StudentReview, SubmissionReviewer
from desktop_agent.journal import OperationJournal


class FakeClassroom:
    def __init__(self) -> None:
        self.grade_calls = 0
        self.return_calls = 0
        self.current_grade = None
        self.current_state = "TURNED_IN"

    def list_courses(self, active_only=True):
        return [{"id": "c1", "name": "Matemática", "section": "2.º B"}]

    def list_coursework(self, course_id, include_drafts=False):
        return [{"id": "w1", "title": "C3: Inecuaciones", "workType": "ASSIGNMENT", "maxPoints": 20}]

    def list_students(self, course_id):
        return [
            {"userId": "u2", "name": "Zoila Pérez"},
            {"userId": "u1", "name": "Álvaro Díaz"},
            {"userId": "u3", "name": "Bruno León"},
        ]

    def list_submissions(self, course_id, work_id):
        return [
            {"id": "s1", "userId": "u1", "state": "TURNED_IN", "late": False,
             "updateTime": "2026-09-13T01:00:00Z",
             "alternateLink": "https://classroom.google.com/sub/s1",
             "assignmentSubmission": {"attachments": [{"driveFile": {"id": "f1"}}]}},
            {"id": "s2", "userId": "u2", "state": "TURNED_IN", "late": True,
             "updateTime": "2026-09-13T01:00:00Z",
             "alternateLink": "https://classroom.google.com/sub/s2",
             "assignmentSubmission": {"attachments": []}},
        ]

    def grade_submission(self, course_id, work_id, submission_id, grade, return_to_student=False):
        self.grade_calls += 1
        self.current_grade = grade
        return {}

    def return_submission(self, course_id, work_id, submission_id, finalize_draft=False):
        self.return_calls += 1
        self.current_state = "RETURNED"
        return {}

    def get_submission(self, course_id, work_id, submission_id):
        return {"id": submission_id, "assignedGrade": self.current_grade, "state": self.current_state}


def review() -> StudentReview:
    return StudentReview(
        score=17,
        level="A",
        summary="Buen desarrollo.",
        strengths=("Planteó correctamente",),
        findings=(ExerciseFinding("Pregunta 1", "Resolvió", "Correcto", "Justificar", None),),
        suggestion="Verificar por sustitución.",
        feedback=(
            "Álvaro, buen desarrollo.\nLo que hiciste bien:\nPlanteaste correctamente.\n"
            "Lo que debes mejorar:\nPregunta 1: debes justificar la comprobación.\n"
            "Sugerencia:\nVerifica por sustitución.\nNota cuantitativa: 17/20\nNota cualitativa: A"
        ),
        evidence_files=("c3.pdf",),
    )


class ClassroomFlowTests(unittest.TestCase):
    def test_feedback_is_built_locally_with_required_structure(self) -> None:
        normalized = review().normalized_for("LUCÍA CAROLINA RODRÍGUEZ ALFARO")
        self.assertTrue(normalized.feedback.startswith("Lucía,"))
        self.assertIn("Lo que hiciste bien:", normalized.feedback)
        self.assertIn("Lo que debes mejorar:", normalized.feedback)
        self.assertIn("Pregunta 1:", normalized.feedback)
        self.assertIn("Sugerencia:", normalized.feedback)
        self.assertIn("Nota cuantitativa: 17/20", normalized.feedback)
        self.assertIn("Nota cualitativa: A", normalized.feedback)

    def test_model_feedback_format_does_not_invalidate_review(self) -> None:
        raw = {
            "score": 12, "level": "B", "summary": "Avance parcial.",
            "strengths": ["Identificó la variable"],
            "findings": [{
                "label": "Ejercicio 1", "observed": "Planteó la relación.",
                "correct": "La relación es pertinente.", "improvement": "Concluir el despeje.",
                "error_type": "incompleto",
            }],
            "suggestion": "Comprueba el resultado.", "feedback": "texto libre",
        }
        result = SubmissionReviewer._validate(raw, ("entrega.pdf",)).normalized_for("Ana Pérez")
        self.assertIn("Nota cuantitativa: 12/20", result.feedback)
        self.assertIn("Nota cualitativa: B", result.feedback)

    def test_ambiguous_course_is_blocked(self) -> None:
        with TemporaryDirectory() as directory:
            client = FakeClassroom()
            client.list_courses = lambda active_only=True: [
                {"id": "c1", "name": "Matemática", "section": "2.º B"},
                {"id": "c2", "name": "Tutoría", "section": "2.º B"},
            ]
            flow = ClassroomFlow(client, OperationJournal(Path(directory) / "ops.sqlite3"))
            with self.assertRaises(ValueError):
                flow.prepare("2.º B", "C3: Inecuaciones")

    def test_prepare_resolves_exactly_and_orders_roster(self) -> None:
        with TemporaryDirectory() as directory:
            flow = ClassroomFlow(FakeClassroom(), OperationJournal(Path(directory) / "ops.sqlite3"))
            batch = flow.prepare("2.º B", "C3: Inecuaciones")
            self.assertEqual([row.student_name for row in batch.students], ["Álvaro Díaz", "Zoila Pérez"])
            self.assertEqual([row["name"] for row in batch.without_submission], ["Bruno León"])
            self.assertEqual(batch.students[0].attachment_count, 1)

    def test_no_attachment_is_never_modified(self) -> None:
        with TemporaryDirectory() as directory:
            client = FakeClassroom()
            flow = ClassroomFlow(client, OperationJournal(Path(directory) / "ops.sqlite3"))
            batch = flow.prepare("c1", "w1")
            result = flow.apply_review(batch, batch.students[1], review(), lambda *_: True)
            self.assertEqual(result["status"], "skipped_no_attachment")
            self.assertEqual(client.grade_calls, 0)

    def test_apply_is_verified_and_idempotent(self) -> None:
        with TemporaryDirectory() as directory:
            client = FakeClassroom()
            flow = ClassroomFlow(client, OperationJournal(Path(directory) / "ops.sqlite3"))
            batch = flow.prepare("c1", "w1")
            comment_calls = []

            def publish(*args):
                comment_calls.append(args)
                return True

            first = flow.apply_review(batch, batch.students[0], review(), publish)
            second = flow.apply_review(batch, batch.students[0], review(), publish)
            self.assertEqual(first["status"], "completed")
            self.assertEqual(second["status"], "completed")
            self.assertEqual(len(comment_calls), 1)
            self.assertEqual(client.grade_calls, 1)
            self.assertEqual(client.return_calls, 1)


if __name__ == "__main__":
    unittest.main()
