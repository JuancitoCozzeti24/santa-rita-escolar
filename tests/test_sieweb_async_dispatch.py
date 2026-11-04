"""Asegura que las llamadas MCP de SIEweb nunca bloquean el loop ASGI.

La sesión MFA vive en el navegador; el trabajo de SieWeb es síncrono y
espera por threading.Event. Debe ejecutarse en un hilo aparte para que
/bridge/v1/sieweb/next y /result puedan responder durante esa espera.
"""
from pathlib import Path
import ast
import asyncio
import inspect
import threading
import unittest

from sieweb_browser_relay import VerifiedBrowserRelay


class AcademicDispatchNonblockingTests(unittest.IsolatedAsyncioTestCase):
    def test_registration_wrapper_is_async_and_offloaded(self):
        root = Path(__file__).resolve().parents[1]
        tree = ast.parse((root / "config.py").read_text(encoding="utf-8"))
        matches = [node for node in ast.walk(tree)
                   if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef))
                   and node.name == "sieweb_academics_with_bitacora"]
        self.assertEqual(len(matches), 1)
        wrapper = matches[0]
        self.assertIsInstance(wrapper, ast.AsyncFunctionDef)
        awaits = [n for n in ast.walk(wrapper) if isinstance(n, ast.Await)]
        self.assertGreaterEqual(len(awaits), 1)
        self.assertTrue(any(
            isinstance(n.value, ast.Call) and
            isinstance(n.value.func, ast.Attribute) and
            n.value.func.attr == "to_thread"
            for n in awaits
        ))
        self.assertIn("import asyncio", (root / "config.py").read_text(encoding="utf-8"))

    async def test_browser_can_complete_request_while_sync_client_waits(self):
        relay = VerifiedBrowserRelay()
        relay.pulse(verified=True)
        # Simulates async MCP wrapper calling a blocking SieWebClient.
        pending = asyncio.create_task(
            asyncio.to_thread(
                relay.request, "GET", "/lms/api/HyoMensajeria/obtMensajes",
                params={"idCarpeta": 1}
            )
        )
        job = None
        for _ in range(100):
            await asyncio.sleep(.005)
            job = relay.next_job()
            if job:
                break
        self.assertIsNotNone(job, "The event loop must still run during wait()")
        self.assertTrue(
            relay.complete(job["id"], status_code=200, data={"json":{"estado":1}})
        )
        self.assertEqual((await asyncio.wait_for(pending, timeout=2))["json"]["estado"], 1)


if __name__ == "__main__":
    unittest.main()
