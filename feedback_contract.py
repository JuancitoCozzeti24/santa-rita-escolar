"""Contrato permanente para la retroalimentación pedagógica de Matemática en SieRoom."""
from __future__ import annotations

import math
import re
import unicodedata

POLICY_VERSION = "matematica-feedback-r7-2026-11-11"

DEFAULT_TEMPLATE = """{Nombre de uso}, revisé {número de páginas/archivos} de {nombre exacto de tarea}, {grado y sección}, y valoré {número de ejercicios} con crédito parcial cuando el procedimiento fue pertinente.

*LO QUE HICISTE BIEN*
{Fortalezas reales y específicas observadas en los ejercicios. Reconocer el crédito parcial y los avances.}

*LO QUE DEBES MEJORAR:*
1. {Ejercicio y tema}: {qué escribió o hizo el alumno, si fue correcto, error o precisión pendiente, explicación matemática y cómo corregirlo}.
2. {Ejercicio y tema}: {análisis individual verificable y procedimiento correcto}.
{Continuar, en orden, con TODOS los ejercicios de la tarea, incluso los incompletos; no inventar respuestas de ejercicios que no se ven.}

*SUGERENCIAS:*
{Estrategias concretas y aplicables para superar las dificultades identificadas.}

Nota cuantitativa: {nota}/20.
Calificación por capacidades:
{Capacidad 1 de la competencia real}: {A/B/C} ({justificación basada en evidencias de esta capacidad}).
{Capacidad 2}: {A/B/C} ({justificación concreta}).
{Capacidad 3}: {A/B/C} ({justificación concreta}).
{Capacidad 4}: {A/B/C} ({justificación concreta})."""

RULES = [
    "Esta es la plantilla predeterminada obligatoria de retroalimentación de Matemática 2.º A/B y 5.º A/B; solo cambia si el docente pide expresamente otro formato.",
    "Usar nombre de trato real del estudiante; conservar nombres compuestos como Ana Paula. Personalizar tarea, sección, páginas y ejercicios solo si están verificados.",
    "Revisar de manera individual TODOS los ejercicios esperados, en orden. Si un ejercicio no aparece, señalar falta de evidencia sin inventar procedimiento.",
    "Cada ejercicio requiere observación verificable, acierto/error/omisión y explicación didáctica de la operación, regla, representación o corrección pertinente.",
    "Bajo LO QUE DEBES MEJORAR puede explicarse también un ejercicio correcto, indicando sus aciertos y cómo justificarlo mejor; no fabricar fallas.",
    "Dar crédito parcial razonable cuando el planteamiento es pertinente, aun con error aritmético; diferenciar errores conceptuales, procedimentales, aritméticos y notacionales.",
    "Respetar el CNEB y seleccionar las cuatro capacidades REALES de la competencia evaluada; no copiar Traduce/Comunica/Usa estrategias/Argumenta para tareas de otra competencia.",
    "Evaluar cada capacidad por su propia evidencia, sin convertir automáticamente la nota global en A/B/C idéntica para todas. A=15–20, B=11–14, C=0–10 son solo los rangos generales.",
    "Mantener tono pedagógico, respetuoso, minucioso y no infantilizante; explicar operaciones, desigualdades, unidades, límites y justificaciones cuando correspondan.",
    "No inventar archivos, contenido, resultados ni criterios. Si una imagen es ilegible o un archivo es de otra tarea, no afirmar que se revisó ese ejercicio.",
    "No reutilizar las soluciones, la nota 15/20 ni las calificaciones A/A/B/A del ejemplo de Ana Paula para otros estudiantes.",
    "Antes de publicar, verificar curso, tarea, estudiante, evidencia, escala /20, coherencia del comentario y duplicados; después, confirmar publicación real.",
    "Los comentarios administrativos sin calificación no son retroalimentaciones evaluativas y no están sujetos al formato completo.",
]

INSTRUCTIONS = (
    "POLÍTICA DOCENTE PERMANENTE DE RETROALIMENTACIÓN MATEMÁTICA SIERoom "
    f"({POLICY_VERSION}). En toda revisión evaluativa de Classroom, aplica literalmente "
    "los títulos y el orden de DEFAULT_TEMPLATE. La longitud del comentario debe "
    "corresponder a la cantidad de ejercicios reales: si el examen contiene 20, "
    "explica los 20 de manera individual y extensa. Incluye nota cuantitativa /20 "
    "y cuatro capacidades de la competencia con letra y justificación propias. "
    "No omitas análisis por ejercicio, no inventes evidencia, no copies las "
    "respuestas ni calificación de un estudiante a otro. Consulta "
    "classroom_feedback_policy para recuperar la plantilla y las reglas completas. "
    "Antes de escribir, el puente valida automáticamente la estructura de una "
    "retroalimentación evaluativa y la concordancia de su nota /20."
)


def _plain(value: str) -> str:
    """Normalizar únicamente para comprobar encabezados, no para editar el comentario."""
    text = unicodedata.normalize("NFKD", str(value or ""))
    return "".join(ch for ch in text if not unicodedata.combining(ch)).upper()


def validate_structured_feedback(comment: str, grade: float | None = None) -> list[str]:
    """Preflight estructural; NO sustituye la inspección de la evidencia matemática."""
    original = str(comment or "").strip()
    normalized = _plain(original)
    errors: list[str] = []
    headers = [
        ("LO QUE HICISTE BIEN", "LO QUE HICISTE BIEN"),
        ("LO QUE DEBES MEJORAR", "LO QUE DEBES MEJORAR"),
        ("SUGERENCIAS", "SUGERENCIAS"),
        ("NOTA CUANTITATIVA", "Nota cuantitativa"),
        ("CALIFICACION POR CAPACIDADES", "Calificación por capacidades"),
    ]
    positions = []
    for phrase, label in headers:
        index = normalized.find(phrase)
        if index < 0:
            errors.append(f"Falta el apartado {label}.")
        else:
            positions.append(index)
    if len(positions) == len(headers) and positions != sorted(positions):
        errors.append("Los apartados no siguen el orden de la plantilla.")

    # Cualquier ejercicio que figure realmente debe poder comentarse; su
    # número total se contrasta con la ficha y sus archivos, no se adivina aquí.
    enumerated = re.findall(r"(?m)^\s*\d{1,3}\.\s+\S", original)
    if not enumerated:
        errors.append("Falta el análisis individual y numerado de ejercicios.")

    note = re.search(r"(?im)^\s*Nota\s+cuantitativa\s*:\s*(\d+(?:[.,]\d+)?)\s*/\s*20\b", original)
    if not note:
        errors.append("Falta la nota cuantitativa escrita como X/20.")
    else:
        note_value = float(note.group(1).replace(",", "."))
        if not 0 <= note_value <= 20:
            errors.append("La nota del comentario está fuera del rango 0–20.")
        if grade is not None:
            try:
                numeric_grade = float(grade)
                if not math.isfinite(numeric_grade) or not math.isclose(
                    numeric_grade, note_value, rel_tol=0.0, abs_tol=0.001
                ):
                    errors.append("La nota X/20 del comentario no coincide con la nota enviada a Classroom.")
            except (TypeError, ValueError):
                errors.append("La nota enviada a Classroom no es válida.")

    if "CALIFICACION POR CAPACIDADES" in normalized:
        start = normalized.index("CALIFICACION POR CAPACIDADES")
        section = original[start:]
        capabilities = re.findall(
            r"(?m)^\s*([^:\n]{3,95})\s*:\s*([ABC])\s*\(\s*(\S[^\n]{12,})\s*$",
            section,
        )
        unique_names = {_plain(row[0]).strip() for row in capabilities}
        if len(unique_names) < 4:
            errors.append(
                "Se requieren las cuatro capacidades de la competencia, cada una con A/B/C "
                "y una justificación específica entre paréntesis."
            )
    return errors


def should_validate(comment: str, grade: float | None = None) -> bool:
    """No bloquear avisos administrativos sin nota; sí validar feedback evaluativo."""
    if grade is not None:
        return True
    text = _plain(comment)
    return any(
        marker in text
        for marker in ("LO QUE HICISTE BIEN", "LO QUE DEBES MEJORAR", "CALIFICACION POR CAPACIDADES")
    )
