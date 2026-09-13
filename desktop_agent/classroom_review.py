from __future__ import annotations

from dataclasses import dataclass, asdict
from typing import Any, TYPE_CHECKING
import base64
import json
from io import BytesIO

from .settings import DesktopSettings

if TYPE_CHECKING:
    from classroom import ClassroomClient


@dataclass(frozen=True)
class ExerciseFinding:
    label: str
    observed: str
    correct: str
    improvement: str
    error_type: str | None


@dataclass(frozen=True)
class StudentReview:
    score: int
    level: str
    summary: str
    strengths: tuple[str, ...]
    findings: tuple[ExerciseFinding, ...]
    suggestion: str
    feedback: str
    evidence_files: tuple[str, ...]

    def public(self) -> dict[str, Any]:
        return asdict(self)

    @classmethod
    def from_public(cls, raw: dict[str, Any]) -> "StudentReview":
        return cls(
            score=int(raw["score"]), level=str(raw["level"]), summary=str(raw["summary"]),
            strengths=tuple(str(value) for value in raw.get("strengths") or []),
            findings=tuple(ExerciseFinding(**item) for item in raw.get("findings") or []),
            suggestion=str(raw["suggestion"]), feedback=str(raw["feedback"]),
            evidence_files=tuple(str(value) for value in raw.get("evidence_files") or []),
        )


REVIEW_INSTRUCTIONS = """Actúa como docente peruano de Matemática y evalúa únicamente la evidencia visible.
Resuelve por ti mismo los ejercicios del enunciado original antes de contrastar la respuesta del estudiante.
Revisa ejercicio por ejercicio: planteamiento, procedimiento, operaciones, unidades, representación,
justificación y respuesta. Da crédito parcial a procedimientos pertinentes. Distingue error conceptual,
procedimental, aritmético, notación, incompleto o falta de evidencia. No inventes contenido ilegible.
Devuelve JSON con score entero 0..20, level A/B/C, summary, strengths (lista), findings (lista de objetos
label, observed, correct, improvement, error_type), suggestion y feedback. feedback debe quedar listo para
Classroom y usar: nombre y síntesis; Lo que hiciste bien; Lo que debes mejorar, detallado por pregunta;
Sugerencia; Nota cuantitativa X/20; Nota cualitativa A/B/C. Escala: A 15–20, B 11–14, C 0–10."""


class SubmissionReviewer:
    def __init__(self, settings: DesktopSettings, classroom: "ClassroomClient") -> None:
        if not settings.openai_api_key:
            raise RuntimeError("Falta OPENAI_API_KEY para revisar entregas.")
        self.settings = settings
        self.classroom = classroom

    def review(
        self,
        *,
        course_id: str,
        coursework: dict[str, Any],
        submission: dict[str, Any],
        student_name: str,
        criteria: str = "",
        max_pages_per_file: int = 12,
    ) -> StudentReview:
        submission_id = str(submission["id"])
        attachments = self.classroom.list_submission_attachments(
            course_id, str(coursework["id"]), submission_id, include_drive_metadata=True
        )
        if not attachments["count"]:
            raise RuntimeError("La entrega no tiene archivos; no se puede evaluar.")

        content: list[dict[str, Any]] = [{
            "type": "input_text",
            "text": json.dumps({
                "student": student_name,
                "assignment": {
                    "title": coursework.get("title"),
                    "description": coursework.get("description"),
                    "maxPoints": coursework.get("maxPoints"),
                },
                "teacher_criteria_or_expected_work": criteria,
                "important": "Si falta evidencia o algo es ilegible, decláralo; no lo reconstruyas.",
            }, ensure_ascii=False),
        }]
        self._append_assignment_materials(content, coursework, max_pages_per_file)
        evidence_files: list[str] = []
        for row in attachments["attachments"]:
            index = int(row["index"])
            metadata = row.get("drive_metadata") or {}
            name = str(metadata.get("name") or f"adjunto-{index + 1}")
            evidence_files.append(name)
            content.append({"type": "input_text", "text": f"ARCHIVO {index + 1}: {name}"})
            rendered = 0
            for page_number in range(1, max_pages_per_file + 1):
                try:
                    info, image = self.classroom.render_submission_attachment_image(
                        course_id, str(coursework["id"]), submission_id, index, page=page_number
                    )
                except (IndexError, ValueError, RuntimeError):
                    break
                content.append({
                    "type": "input_image",
                    "image_url": "data:image/png;base64," + base64.b64encode(image).decode("ascii"),
                })
                rendered += 1
                if page_number >= int(info.get("page_count") or page_number):
                    break
            if rendered == 0:
                extracted = self.classroom.inspect_submission_attachment_text(
                    course_id, str(coursework["id"]), submission_id, index
                )
                text = str(extracted.get("extracted_text") or "")
                if text:
                    content.append({"type": "input_text", "text": text})

        import requests

        response = requests.post(
            "https://api.openai.com/v1/responses",
            headers={"Authorization": f"Bearer {self.settings.openai_api_key}", "Content-Type": "application/json"},
            json={
                "model": self.settings.model,
                "instructions": REVIEW_INSTRUCTIONS,
                "input": [{"role": "user", "content": content}],
                "text": {"format": {"type": "json_object"}},
                "max_output_tokens": 3500,
            },
            timeout=180,
        )
        if not response.ok:
            raise RuntimeError(f"OpenAI HTTP {response.status_code}: {response.text[:700]}")
        raw = json.loads(self._output_text(response.json()))
        return self._validate(raw, tuple(evidence_files))

    def _append_assignment_materials(
        self, content: list[dict[str, Any]], coursework: dict[str, Any], max_pages: int
    ) -> None:
        """Añade los enunciados originales para que el modelo pueda resolverlos y comparar."""
        materials = list(coursework.get("materials") or [])
        if not materials:
            content.append({
                "type": "input_text",
                "text": "La tarea no tiene material original adjunto; usa únicamente el enunciado y la evidencia legible.",
            })
            return
        for index, material in enumerate(materials, 1):
            wrapped = material.get("driveFile") or {}
            drive = wrapped.get("driveFile") or wrapped
            file_id = str(drive.get("id") or "")
            title = str(drive.get("title") or f"material-{index}")
            if file_id:
                try:
                    meta, data, mime_type = self.classroom.download_drive_file(file_id)
                    title = str(meta.get("name") or title)
                    images = self._render_reference(data, mime_type, title, max_pages)
                except Exception as exc:
                    content.append({
                        "type": "input_text",
                        "text": f"No se pudo leer el material original {title}: {exc}. No inventes su contenido.",
                    })
                    continue
                content.append({"type": "input_text", "text": f"ENUNCIADO ORIGINAL {index}: {title}"})
                for image in images:
                    content.append({
                        "type": "input_image",
                        "image_url": "data:image/png;base64," + base64.b64encode(image).decode("ascii"),
                    })
            elif material.get("link"):
                content.append({
                    "type": "input_text",
                    "text": f"MATERIAL ORIGINAL ENLAZADO: {(material.get('link') or {}).get('url') or ''}",
                })

    @staticmethod
    def _render_reference(data: bytes, mime_type: str, name: str, max_pages: int) -> list[bytes]:
        if mime_type.startswith("image/"):
            from PIL import Image
            out = BytesIO()
            image = Image.open(BytesIO(data)).convert("RGB")
            image.thumbnail((1800, 1800))
            image.save(out, format="PNG", optimize=True)
            return [out.getvalue()]
        if mime_type == "application/pdf" or name.lower().endswith(".pdf"):
            import fitz
            document = fitz.open(stream=data, filetype="pdf")
            images: list[bytes] = []
            for page in document[:max_pages]:
                scale = min(1800 / max(page.rect.width, page.rect.height), 3.0)
                images.append(page.get_pixmap(matrix=fitz.Matrix(scale, scale), alpha=False).tobytes("png"))
            return images
        return []

    @staticmethod
    def _output_text(data: dict[str, Any]) -> str:
        direct = str(data.get("output_text") or "").strip()
        if direct:
            return direct
        chunks: list[str] = []
        for item in data.get("output") or []:
            for content in item.get("content") or []:
                if content.get("type") == "output_text":
                    chunks.append(str(content.get("text") or ""))
        return "".join(chunks)

    @staticmethod
    def _validate(raw: dict[str, Any], evidence_files: tuple[str, ...]) -> StudentReview:
        score = int(raw["score"])
        if not 0 <= score <= 20:
            raise ValueError("La revisión devolvió una nota fuera de 0–20.")
        expected_level = "A" if score >= 15 else "B" if score >= 11 else "C"
        if str(raw.get("level") or "").upper() != expected_level:
            raise ValueError("La nota cualitativa no coincide con la cuantitativa.")
        findings = tuple(
            ExerciseFinding(
                label=str(item.get("label") or "Pregunta sin identificar"),
                observed=str(item.get("observed") or ""),
                correct=str(item.get("correct") or ""),
                improvement=str(item.get("improvement") or ""),
                error_type=str(item["error_type"]) if item.get("error_type") else None,
            )
            for item in raw.get("findings") or []
        )
        if not findings:
            raise ValueError("La revisión no contiene análisis por ejercicio.")
        feedback = str(raw.get("feedback") or "").strip()
        required = (
            "Lo que hiciste bien", "Lo que debes mejorar", "Sugerencia", f"{score}/20",
            f"Nota cualitativa: {expected_level}",
        )
        if any(part.casefold() not in feedback.casefold() for part in required):
            raise ValueError("La retroalimentación no cumple la estructura pedagógica requerida.")
        return StudentReview(
            score=score,
            level=expected_level,
            summary=str(raw.get("summary") or ""),
            strengths=tuple(str(value) for value in raw.get("strengths") or []),
            findings=findings,
            suggestion=str(raw.get("suggestion") or ""),
            feedback=feedback,
            evidence_files=evidence_files,
        )
