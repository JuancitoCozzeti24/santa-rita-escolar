from __future__ import annotations

import unittest
from types import SimpleNamespace
from unittest.mock import patch

import bitacora


STUDENTS = [
    ["Alumno_ID", "Apellidos y nombres", "Grado", "Sección", "Código/ID externo", "Estado", "Fecha de alta"],
    ["ALU-001", "PÉREZ RAMOS, ANA", "2.º", "A", "EXT-1", "Activo", "01/03/2026"],
]

BEHAVIOR_HEADERS = [
    "Registro_ID", "Fecha", "Hora", "Alumno_ID", "Estudiante", "Grado", "Sección",
    "Tipo de registro", "Categoría", "Descripción objetiva",
    "Impacto en aprendizaje/convivencia", "Acción docente", "Seguimiento",
    "Nivel de importancia", "Comunicación a familia",
    "Comunicación a tutor/orientación", "Evidencia o referencia", "Registrado por",
]

BEHAVIOR = [
    BEHAVIOR_HEADERS,
    ["BIT-1", "09/09/2026", "", "ALU-001", "PÉREZ RAMOS, ANA", "2.º", "A", "Positivo", "Esfuerzo destacado", "Participó.", "", "", "", "Baja", "", "", "", "Docente"],
    ["BIT-2", "10/09/2026", "09:00", "ALU-001", "PÉREZ RAMOS, ANA", "2.º", "A", "Observación", "Trabajo incompleto", "No concluyó.", "", "", "Revisar", "Media", "", "", "", "Docente"],
    ["BIT-3", "11/09/2026", "08:30", "ALU-001", "PÉREZ RAMOS, ANA", "2.º", "A", "Seguimiento", "Mejora observada", "Completó el trabajo.", "", "", "", "Baja", "", "", "", "Docente"],
]

ACADEMIC_HEADERS = [
    "Registro_ID", "Fecha", "Alumno_ID", "Estudiante", "Grado", "Sección",
    "Actividad/Evidencia", "Competencia", "Capacidad/Desempeño", "Nota /20",
    "Nivel cualitativo", "Fuente", "Observaciones",
]

ACADEMIC = [
    ACADEMIC_HEADERS,
    ["ACD-1", "10/09/2026", "ALU-001", "PÉREZ RAMOS, ANA", "2.º", "A", "Ficha", "Competencia", "Desempeño", 16, "A", "Classroom", "Resolvió la ficha."],
]


def fake_sheets_get(a1_range: str):
    if a1_range.startswith("ALUMNOS!"):
        return STUDENTS
    if a1_range.startswith("BITÁCORA!"):
        return BEHAVIOR
    if a1_range.startswith("ACADÉMICO!"):
        return ACADEMIC
    raise AssertionError(f"Rango inesperado: {a1_range}")


class FakeMcp:
    def __init__(self):
        self.instructions = "Base"
        self._mcp_server = SimpleNamespace(instructions="Base")
        self.registered = []

    def tool(self):
        def decorator(fn):
            self.registered.append(fn.__name__)
            return fn

        return decorator


class BitacoraIntegrationTests(unittest.TestCase):
    @patch.object(bitacora, "_sheets_get", side_effect=fake_sheets_get)
    def test_student_history_filters_inclusive_date_range(self, _mock_get):
        result = bitacora.dispatch(
            "bitacora_student_history",
            {
                "student": "Ana Pérez Ramos",
                "fecha_desde": "10/09/2026",
                "fecha_hasta": "2026-09-11",
            },
        )

        self.assertEqual([row["Registro_ID"] for row in result["bitacora"]], ["BIT-2", "BIT-3"])
        self.assertEqual([row["Registro_ID"] for row in result["academico"]], ["ACD-1"])
        self.assertEqual(result["counts"]["bitacora_total_sin_filtro"], 3)
        self.assertEqual(result["scope"]["fecha_desde"], "10/09/2026")
        self.assertEqual(result["scope"]["fecha_hasta"], "11/09/2026")

    @patch.object(bitacora, "_sheets_get", side_effect=fake_sheets_get)
    def test_student_report_returns_evidence_and_summary(self, _mock_get):
        result = bitacora.dispatch("bitacora_student_report", {"student": "ALU-001"})

        self.assertEqual(result["student"]["nombre"], "PÉREZ RAMOS, ANA")
        self.assertEqual(result["summary"]["tipos_bitacora"]["Positivo"], 1)
        self.assertEqual(result["summary"]["niveles_academicos"]["A"], 1)
        self.assertTrue(result["report_rules"])

    def test_invalid_inverted_date_range_is_blocked(self):
        with patch.object(bitacora, "_sheets_get", side_effect=fake_sheets_get):
            with self.assertRaisesRegex(ValueError, "fecha_desde"):
                bitacora.dispatch(
                    "student_history",
                    {"student": "ALU-001", "fecha_desde": "12/09/2026", "fecha_hasta": "11/09/2026"},
                )

    @patch.object(bitacora, "_sheets_get", side_effect=fake_sheets_get)
    def test_append_without_confirmation_only_previews(self, _mock_get):
        result = bitacora.dispatch(
            "bitacora_append_observation",
            {"student": "ALU-001", "descripcion": "Trabajó de manera sostenida."},
            confirmed=False,
        )

        self.assertTrue(result["requires_confirmation"])
        self.assertEqual(result["preview"]["Alumno_ID"], "ALU-001")

    def test_install_is_idempotent(self):
        fake = FakeMcp()

        bitacora.install(fake)
        bitacora.install(fake)

        self.assertEqual(fake.registered, ["bitacora_docente"])
        self.assertIn("POLÍTICA PERMANENTE DE BITÁCORA", fake._mcp_server.instructions)

    def test_batch_blocks_entire_write_when_a_student_is_unresolved(self):
        records = [
            {
                "student": "Estudiante inexistente",
                "grado": "2.º",
                "seccion": "A",
                "descripcion": "No presentó evidencia.",
                "evidencia": "Classroom; course_work_id=1; submission_id=1; estado=MISSING",
            }
        ]
        with patch.object(bitacora, "_sheets_get", side_effect=fake_sheets_get), patch.object(
            bitacora, "_sheets_append_rows"
        ) as append_rows:
            result = bitacora.dispatch(
                "bitacora_append_observations_batch", {"records": records}, confirmed=True
            )

        self.assertTrue(result["blocked"])
        self.assertEqual(len(result["unresolved"]), 1)
        append_rows.assert_not_called()

    def test_batch_skips_existing_reference_and_verifies_new_rows(self):
        existing_reference = "Classroom; course_work_id=1; submission_id=1; estado=MISSING"
        new_reference = "Classroom; course_work_id=2; submission_id=2; estado=LATE"
        existing_row = [
            "BIT-OLD", "10/09/2026", "", "ALU-001", "PÉREZ RAMOS, ANA", "2.º", "A",
            "Observación", "Incumplimiento", "No presentó.", "", "", "", "Media", "", "",
            existing_reference, "Docente",
        ]

        def batch_sheets_get(a1_range: str):
            if a1_range.startswith("ALUMNOS!"):
                return STUDENTS
            if a1_range == "BITÁCORA!A1:R3000":
                return [BEHAVIOR_HEADERS, existing_row]
            raise AssertionError(f"Rango inesperado: {a1_range}")

        records = [
            {
                "student": "Ana Pérez Ramos",
                "grado": "2.º",
                "seccion": "A",
                "descripcion": "No presentó evidencia.",
                "evidencia": existing_reference,
            },
            {
                "student": "Ana Pérez Ramos",
                "grado": "2.º",
                "seccion": "A",
                "descripcion": "Presentó después del plazo.",
                "categoria": "Tardanza",
                "evidencia": new_reference,
            },
        ]
        verification = {"verified": True, "count": 1}
        with patch.object(bitacora, "_sheets_get", side_effect=batch_sheets_get), patch.object(
            bitacora, "_sheets_append_rows", return_value="BITÁCORA!A90:R90"
        ) as append_rows, patch.object(
            bitacora, "_verify_saved_rows", return_value=verification
        ):
            result = bitacora.dispatch(
                "bitacora_append_observations_batch", {"records": records}, confirmed=True
            )

        self.assertTrue(result["saved"])
        self.assertEqual(result["saved_count"], 1)
        self.assertEqual(result["skipped_existing"], 1)
        self.assertEqual(result["verification"], verification)
        self.assertEqual(len(append_rows.call_args.args[1]), 1)


if __name__ == "__main__":
    unittest.main()
