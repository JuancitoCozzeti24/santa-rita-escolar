"""Pruebas sin conexión de red de la pasarela SIEweb con MFA del navegador."""
import threading
import time
import unittest

from sieweb_browser_relay import VerifiedBrowserRelay, SieWebRelayError


class VerifiedBrowserRelayTests(unittest.TestCase):
    def setUp(self):
        self.bridge = VerifiedBrowserRelay()

    def test_no_request_without_verified_browser(self):
        with self.assertRaises(SieWebRelayError):
            self.bridge.request("GET", "/lms/api/HyoMensajeria/obtMensajes")
        self.assertFalse(self.bridge.status()["verified_browser_session"])

    def test_verified_browser_roundtrip(self):
        self.bridge.pulse(verified=True)
        out = {}
        def do_call():
            try:
                out["result"] = self.bridge.request(
                    "GET", "/lms/api/HyoMensajeria/obtMensajes",
                    params={"idCarpeta": 1},
                )
            except Exception as exc:
                out["error"] = repr(exc)

        thread = threading.Thread(target=do_call)
        thread.start()
        job = None
        for _ in range(100):
            job = self.bridge.next_job()
            if job:
                break
            time.sleep(.01)
        self.assertIsNotNone(job)
        self.assertEqual(job["method"], "GET")
        self.assertNotIn("token", job)
        self.assertTrue(self.bridge.complete(
            job["id"], status_code=200, data={"json": {"estado": 1, "mensajes": []}}
        ))
        thread.join(timeout=2)
        self.assertFalse(thread.is_alive())
        self.assertEqual(out.get("result", {}).get("json", {}).get("estado"), 1)
        self.assertEqual(self.bridge.status()["pending_requests"], 0)

    def test_long_poll_wakes_when_new_job_is_queued(self):
        self.bridge.pulse(verified=True)
        claimed = {}
        def waiter():
            claimed["job"] = self.bridge.wait_next_job(2.5)
        consumer = threading.Thread(target=waiter)
        consumer.start()
        time.sleep(.05)
        result = {}
        def producer():
            try:
                result["value"] = self.bridge.request(
                    "GET", "/lms/api/HyoMensajeria/obtMensajes",
                    params={"idCarpeta": 1}
                )
            except Exception as exc:
                result["error"] = str(exc)
        requester = threading.Thread(target=producer)
        requester.start()
        consumer.join(timeout=1)
        self.assertFalse(consumer.is_alive(), "Wake should not wait 2.5s")
        self.assertIsNotNone(claimed.get("job"))
        self.assertTrue(
            self.bridge.complete(claimed["job"]["id"], status_code=200,
                                 data={"json":{"estado":1}})
        )
        requester.join(timeout=2)
        self.assertFalse(requester.is_alive())
        self.assertEqual(result.get("value", {}).get("json", {}).get("estado"), 1)

    def test_no_job_long_poll_returns_empty(self):
        self.bridge.pulse(verified=True)
        self.assertIsNone(self.bridge.wait_next_job(.01))

    def test_does_not_repeat_claimed_write(self):
        self.bridge.pulse(verified=True)
        # The queue has a single job and never reissues an ambiguous POST.
        result = {}
        thread = threading.Thread(
            target=lambda: result.update({
                "ok": self.bridge.request("POST", "/lms/api/HyoMensajeria/enviarMensaje", payload={"asunto":"test"})
            })
        )
        thread.start()
        job = None
        for _ in range(100):
            job = self.bridge.next_job()
            if job:
                break
            time.sleep(.01)
        self.assertIsNotNone(job)
        self.assertIsNone(self.bridge.next_job())
        self.assertTrue(self.bridge.complete(job["id"], status_code=200, data={"json":{"estado":1}}))
        thread.join(timeout=2)
        self.assertFalse(thread.is_alive())

    def test_rejects_other_hosts_and_bypass_paths(self):
        for path in (
            "https://example.com/lms/api/x", "/lms/api/../secret",
            "/lms/api/x?redirect=1", "//lms/api/x", "/lms/api/login/Ingresar",
        ):
            with self.subTest(path=path):
                with self.assertRaises(SieWebRelayError):
                    self.bridge._validate_request("GET", path)

    def test_safe_bridge_diagnostic_codes_without_raw_error(self):
        self.bridge.pulse(verified=True)
        result = {}
        def run():
            try:
                self.bridge.request("GET", "/lms/api/HyoMensajeria/obtMensajes")
            except SieWebRelayError as exc:
                result["error"] = str(exc)
        t = threading.Thread(target=run)
        t.start()
        job = None
        for _ in range(100):
            job = self.bridge.next_job()
            if job:
                break
            time.sleep(.01)
        self.assertIsNotNone(job)
        self.assertTrue(self.bridge.complete(job["id"], status_code=502,
                                             error="unexpected_content_type"))
        t.join(timeout=2)
        self.assertIn("unexpected_content_type", result.get("error", ""))

    def test_unknown_error_cannot_inject_content(self):
        self.bridge.pulse(verified=True)
        result = {}
        def run():
            try:
                self.bridge.request("GET", "/lms/api/HyoMensajeria/obtMensajes")
            except SieWebRelayError as exc:
                result["error"] = str(exc)
        t = threading.Thread(target=run)
        t.start()
        job = None
        for _ in range(100):
            job = self.bridge.next_job()
            if job:
                break
            time.sleep(.01)
        self.assertIsNotNone(job)
        self.assertTrue(self.bridge.complete(job["id"], status_code=502,
                                             error="secret=123456"))
        t.join(timeout=2)
        self.assertNotIn("123456", result.get("error", ""))
        self.assertIn("unspecified", result.get("error", ""))

    def test_failed_http_status_cannot_return_success(self):
        self.bridge.pulse(verified=True)
        result = {}
        def run():
            try:
                self.bridge.request("GET", "/lms/api/HyoMensajeria/obtMensajes")
            except SieWebRelayError as exc:
                result["error"] = str(exc)
        thread = threading.Thread(target=run)
        thread.start()
        job = None
        for _ in range(100):
            job = self.bridge.next_job()
            if job: break
            time.sleep(.01)
        self.assertIsNotNone(job)
        self.assertTrue(self.bridge.complete(job["id"], status_code=401, data={"token":"private"}))
        thread.join(timeout=2)
        self.assertIn("HTTP 401", result.get("error", ""))
        self.assertNotIn("private", result.get("error", ""))


if __name__ == "__main__":
    unittest.main()
