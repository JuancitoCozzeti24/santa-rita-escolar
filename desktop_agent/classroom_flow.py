from __future__ import annotations

from dataclasses import dataclass, asdict
from typing import Any, Protocol, TYPE_CHECKING
import unicodedata

from .classroom_review import StudentReview
from .journal import OperationJournal

if TYPE_CHECKING:
    from classroom import ClassroomClient


def _norm(value: object) -> str:
    text = unicodedata.normalize("NFKD", str(value or ""))
    return " ".join("".join(c for c in text if not unicodedata.combining(c)).casefold().split())


@dataclass(frozen=True)
class StudentWork:
    user_id: str
    submission_id: str
    student_name: str
    state: str
    late: bool
    submission_url: str
    attachment_count: int
    existing_grade: float | None
    updated_at: str


@dataclass(frozen=True)
class ClassroomBatch:
    course: dict[str, Any]
    coursework: dict[str, Any]
    students: tuple[StudentWork, ...]
    without_submission: tuple[dict[str, Any], ...]


class CommentPublisher(Protocol):
    def __call__(self, submission_url: str, student_name: str, feedback: str) -> bool: ...


class ClassroomFlow:
    def __init__(self, classroom: "ClassroomClient", journal: OperationJournal) -> None:
        self.classroom = classroom
        self.journal = journal

    @staticmethod
    def _one_exact(items: list[dict[str, Any]], query: str, fields: tuple[str, ...], kind: str) -> dict[str, Any]:
        wanted = _norm(query)
        matches = [item for item in items if any(_norm(item.get(field)) == wanted for field in fields)]
        if not matches:
            raise ValueError(f"No se encontró {kind} con coincidencia exacta: {query!r}")
        if len(matches) > 1:
            ids = [str(item.get("id")) for item in matches]
            raise ValueError(f"Hay varias coincidencias para {kind} {query!r}: {ids}")
        return matches[0]

    def prepare(self, course_query: str, coursework_query: str) -> ClassroomBatch:
        courses = self.classroom.list_courses(active_only=True)
        course = self._one_exact(courses, course_query, ("id", "name", "section"), "el curso")
        course_id = str(course["id"])
        works = self.classroom.list_coursework(course_id, include_drafts=False)
        coursework = self._one_exact(works, coursework_query, ("id", "title"), "la tarea")
        if str(coursework.get("workType")) != "ASSIGNMENT":
            raise ValueError("El ítem localizado no es una tarea con entregas.")
        if float(coursework.get("maxPoints") or 0) != 20:
            raise ValueError("La tarea debe estar configurada sobre 20 puntos antes de calificarla.")

        roster = {str(row["userId"]): row for row in self.classroom.list_students(course_id)}
        submissions = {
            str(row["userId"]): row
            for row in self.classroom.list_submissions(course_id, str(coursework["id"]))
        }
        students: list[StudentWork] = []
        missing: list[dict[str, Any]] = []
        for user_id, profile in roster.items():
            submission = submissions.get(user_id)
            if not submission:
                missing.append(profile)
                continue
            attachments = (submission.get("assignmentSubmission") or {}).get("attachments") or []
            students.append(StudentWork(
                user_id=user_id,
                submission_id=str(submission["id"]),
                student_name=str(profile.get("name") or user_id),
                state=str(submission.get("state") or ""),
                late=bool(submission.get("late")),
                submission_url=str(submission.get("alternateLink") or ""),
                attachment_count=len(attachments),
                existing_grade=float(submission["assignedGrade"]) if submission.get("assignedGrade") is not None else None,
                updated_at=str(submission.get("updateTime") or ""),
            ))
        students.sort(key=lambda row: _norm(row.student_name))
        missing.sort(key=lambda row: _norm(row.get("name")))
        return ClassroomBatch(course, coursework, tuple(students), tuple(missing))

    def apply_review(
        self,
        batch: ClassroomBatch,
        student: StudentWork,
        review: StudentReview,
        publish_comment: CommentPublisher,
    ) -> dict[str, Any]:
        if student.attachment_count == 0:
            return {"student": student.student_name, "status": "skipped_no_attachment"}
        target = {
            "course_id": str(batch.course["id"]),
            "coursework_id": str(batch.coursework["id"]),
            "submission_id": student.submission_id,
            "user_id": student.user_id,
        }
        result: dict[str, Any] = {"student": student.student_name, "score": review.score}

        comment, inserted = self.journal.reserve("classroom_comment", target, {"text": review.feedback})
        if inserted or comment.status != "completed":
            self.journal.transition(comment.key, "executing")
            try:
                verified = publish_comment(student.submission_url, student.student_name, review.feedback)
            except Exception as exc:
                self.journal.transition(comment.key, "failed", {"error": str(exc)})
                raise
            if not verified:
                self.journal.transition(comment.key, "failed", {"error": "Comentario no verificado"})
                raise RuntimeError("Classroom no confirmó el comentario privado.")
            self.journal.transition(comment.key, "completed", {"verified": True})
        result["comment"] = "verified"

        grade, inserted = self.journal.reserve("classroom_grade", target, {"grade": review.score})
        if inserted or grade.status != "completed":
            self.journal.transition(grade.key, "executing")
            try:
                self.classroom.grade_submission(
                    str(batch.course["id"]), str(batch.coursework["id"]), student.submission_id,
                    grade=review.score, return_to_student=False,
                )
                after_grade = self.classroom.get_submission(
                    str(batch.course["id"]), str(batch.coursework["id"]), student.submission_id
                )
            except Exception as exc:
                self.journal.transition(grade.key, "failed", {"error": str(exc)})
                raise
            if float(after_grade.get("assignedGrade", -1)) != float(review.score):
                self.journal.transition(grade.key, "failed", {"observed": after_grade.get("assignedGrade")})
                raise RuntimeError("La nota no quedó verificada en Classroom.")
            self.journal.transition(grade.key, "completed", {"assignedGrade": review.score})
        result["grade"] = "verified"

        returned, inserted = self.journal.reserve("classroom_return", target, {"return": True, "grade": review.score})
        if inserted or returned.status != "completed":
            self.journal.transition(returned.key, "executing")
            try:
                self.classroom.return_submission(
                    str(batch.course["id"]), str(batch.coursework["id"]), student.submission_id,
                    finalize_draft=False,
                )
                after_return = self.classroom.get_submission(
                    str(batch.course["id"]), str(batch.coursework["id"]), student.submission_id
                )
            except Exception as exc:
                self.journal.transition(returned.key, "failed", {"error": str(exc)})
                raise
            if str(after_return.get("state")) != "RETURNED":
                self.journal.transition(returned.key, "failed", {"observed": after_return.get("state")})
                raise RuntimeError("La devolución no quedó verificada en Classroom.")
            self.journal.transition(returned.key, "completed", {"state": "RETURNED"})
        result["return"] = "verified"
        result["status"] = "completed"
        return result

    @staticmethod
    def batch_summary(batch: ClassroomBatch) -> dict[str, Any]:
        return {
            "course": batch.course,
            "coursework": batch.coursework,
            "roster_count": len(batch.students) + len(batch.without_submission),
            "submission_count": len(batch.students),
            "with_attachments": sum(row.attachment_count > 0 for row in batch.students),
            "without_attachments": [asdict(row) for row in batch.students if row.attachment_count == 0],
            "without_submission": list(batch.without_submission),
            "students": [asdict(row) for row in batch.students],
        }
