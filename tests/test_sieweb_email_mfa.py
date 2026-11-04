"""Regresión: diagnóstico de login con segundo factor sin exposición de secretos."""
import json
import unittest
from unittest.mock import MagicMock, patch

from sieweb import SieWebClient, SieWebError


class SieWebMFAChallengeTests(unittest.TestCase):
    def test_email_verification_detected_and_redacted(self):
        raw = {
            "json": {
                "estado": 2,
                "mensaje": "Se ha enviado un código de seguridad a su correo.",
                "correo": "privado@ejemplo.edu.pe",
                "codigo": "873641",
                "token": "",
            }
        }
        safe = SieWebClient._safe_login_response_shape(raw)
        self.assertTrue(safe["email_code_challenge_hint"])
        self.assertIn("json", safe["outer_keys"])
        encoded = json.dumps(safe)
        self.assertNotIn("873641", encoded)
        self.assertNotIn("privado@ejemplo.edu.pe", encoded)

    def test_unrelated_login_error_is_not_mfa(self):
        safe = SieWebClient._safe_login_response_shape({
            "json": {"estado": 0, "mensaje": "Usuario o clave incorrecta."}
        })
        self.assertFalse(safe["email_code_challenge_hint"])

    def test_login_does_not_claim_success_before_token(self):
        client = SieWebClient()
        response = MagicMock()
        response.ok = True
        response.json.return_value = {
            "json": {
                "mensaje": "Se ha enviado un código de seguridad a su correo",
                "codigo": "873641",
            }
        }
        with patch.object(type(client), "has_login_credentials", new_callable=lambda: property(lambda _: True)):
            with patch.object(client.session, "post", return_value=response):
                with self.assertRaises(SieWebError) as error:
                    client.login()
        self.assertIn("código de seguridad", str(error.exception))
        self.assertNotIn("873641", str(error.exception))
        self.assertFalse(client._logged_in)


if __name__ == "__main__":
    unittest.main()
