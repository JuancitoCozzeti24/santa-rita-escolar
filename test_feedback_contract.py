"""Regresiones de la política de retroalimentación R7 sin acceso a alumnos."""
import unittest
from feedback_contract import validate_structured_feedback, should_validate, POLICY_VERSION

VALID = """Estudiante de prueba, revisé dos páginas de un examen de ejemplo y valoré dos ejercicios con crédito parcial.

*LO QUE HICISTE BIEN*
Identificas desigualdades y varias correspondencias de funciones.

*LO QUE DEBES MEJORAR:*
1. Inecuación: x+7<19 implica x<12; el extremo 12 no está incluido.
2. Tarifa: C(x)=3+0,40x, incluye el costo fijo.

*SUGERENCIAS:*
Separa siempre el costo fijo y el variable y justifica la recta.

Nota cuantitativa: 15/20.
Calificación por capacidades:
Traduce: A (reconoce los datos y el modelo adecuado).
Comunica: A (representa las relaciones con claridad).
Usa estrategias: B (resuelve inecuaciones con algunos vacíos).
Argumenta: A (justifica soluciones con ejemplos concretos)."""


class PolicyTests(unittest.TestCase):
    def test_sample_format_passes(self):
        self.assertEqual([], validate_structured_feedback(VALID, 15))
        self.assertTrue(should_validate(VALID, 15))

    def test_grade_mismatch_rejected(self):
        self.assertIn("no coincide", " ".join(validate_structured_feedback(VALID, 14)))

    def test_missing_capacities_rejected(self):
        incomplete = VALID.split("Calificación por capacidades:")[0]
        self.assertIn("capacidades", " ".join(validate_structured_feedback(incomplete, 15)))

    def test_admin_message_without_grade_not_blocked(self):
        self.assertFalse(should_validate("He recibido tu archivo, gracias.", None))


if __name__ == "__main__":
    unittest.main()
