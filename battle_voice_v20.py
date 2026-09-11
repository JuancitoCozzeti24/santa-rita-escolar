from __future__ import annotations

import json
import os
import uuid
import urllib.request
import urllib.error

from starlette.requests import Request
from starlette.responses import JSONResponse, Response

SAMPLE_URL = "https://cdn.creativeclaw.co/u/f6c1ef8d/audio/1974d4af-9086-45ba-955b-df66d5af32a8.mp3"
VOICE_NAME = "Profe Johnny - Batalla Matematica"


def _json(data, status=200):
    return JSONResponse(data, status_code=status, headers={
        "Access-Control-Allow-Origin": "*",
        "Access-Control-Allow-Headers": "Content-Type, Authorization, X-Bootstrap-Key",
        "Access-Control-Allow-Methods": "GET, POST, OPTIONS",
        "Cache-Control": "no-store",
    })


def _api_key():
    return (os.getenv("ELEVENLABS_API_KEY") or "").strip()


def _voice_id():
    return (os.getenv("ELEVENLABS_VOICE_ID") or "").strip()


def _el_request(req, timeout=45):
    key = _api_key()
    if not key:
        raise RuntimeError("elevenlabs_key_missing")
    req.add_header("xi-api-key", key)
    with urllib.request.urlopen(req, timeout=timeout) as r:
        return r.status, r.headers, r.read()


def _multipart(fields, files):
    boundary = "----Batalla" + uuid.uuid4().hex
    chunks = []
    for name, value in fields.items():
        chunks += [f"--{boundary}\r\n".encode(),
                   f'Content-Disposition: form-data; name="{name}"\r\n\r\n'.encode(),
                   str(value).encode("utf-8"), b"\r\n"]
    for name, filename, content_type, payload in files:
        chunks += [f"--{boundary}\r\n".encode(),
                   f'Content-Disposition: form-data; name="{name}"; filename="{filename}"\r\n'.encode(),
                   f"Content-Type: {content_type}\r\n\r\n".encode(), payload, b"\r\n"]
    chunks.append(f"--{boundary}--\r\n".encode())
    return boundary, b"".join(chunks)


def install(mcp) -> None:
    @mcp.custom_route("/battle/v1/voice/status", methods=["GET", "OPTIONS"])
    async def voice_status(request: Request):
        if request.method == "OPTIONS":
            return _json({"ok": True})
        key_present = bool(_api_key())
        voice_present = bool(_voice_id())
        api_ok = False
        api_error = None
        if key_present:
            try:
                req = urllib.request.Request("https://api.elevenlabs.io/v1/voices", method="GET")
                status, _, _ = _el_request(req, timeout=20)
                api_ok = status == 200
            except Exception as exc:
                api_error = type(exc).__name__
        return _json({"ok": True, "key_present": key_present, "api_ok": api_ok,
                      "voice_configured": voice_present, "api_error": api_error})

    @mcp.custom_route("/battle/v1/voice/bootstrap", methods=["POST", "OPTIONS"])
    async def voice_bootstrap(request: Request):
        if request.method == "OPTIONS":
            return _json({"ok": True})
        expected = (os.getenv("BATTLE_VOICE_BOOTSTRAP_KEY") or "").strip()
        supplied = (request.headers.get("x-bootstrap-key") or "").strip()
        if not expected or supplied != expected:
            return _json({"ok": False, "error": "forbidden"}, 403)
        if _voice_id():
            return _json({"ok": True, "already_configured": True, "voice_id": _voice_id()})
        try:
            with urllib.request.urlopen(SAMPLE_URL, timeout=30) as src:
                sample = src.read()
            boundary, body = _multipart(
                {"name": VOICE_NAME, "description": "Voz autorizada del Profe Johnny para Batalla Matematica"},
                [("files", "profe-johnny.mp3", "audio/mpeg", sample)],
            )
            req = urllib.request.Request("https://api.elevenlabs.io/v1/voices/add", data=body, method="POST")
            req.add_header("Content-Type", f"multipart/form-data; boundary={boundary}")
            _, _, payload = _el_request(req, timeout=90)
            data = json.loads(payload.decode("utf-8"))
            voice_id = str(data.get("voice_id") or "").strip()
            if not voice_id:
                return _json({"ok": False, "error": "voice_id_missing", "provider": data}, 502)
            return _json({"ok": True, "voice_id": voice_id,
                          "requires_verification": bool(data.get("requires_verification"))})
        except urllib.error.HTTPError as exc:
            try:
                detail = json.loads(exc.read().decode("utf-8", "replace"))
            except Exception:
                detail = {"status": exc.code}
            return _json({"ok": False, "error": "elevenlabs_http_error", "detail": detail}, 502)
        except Exception as exc:
            return _json({"ok": False, "error": type(exc).__name__}, 500)

    @mcp.custom_route("/battle/v1/voice/speak", methods=["POST", "OPTIONS"])
    async def voice_speak(request: Request):
        if request.method == "OPTIONS":
            return _json({"ok": True})
        voice_id = _voice_id()
        if not voice_id:
            return _json({"ok": False, "error": "voice_not_configured"}, 503)
        try:
            data = await request.json()
        except Exception:
            data = {}
        text = str(data.get("text") or "").strip()
        if not text or len(text) > 220:
            return _json({"ok": False, "error": "invalid_text"}, 400)
        body = json.dumps({
            "text": text,
            "model_id": "eleven_multilingual_v2",
            "language_code": "es",
            "voice_settings": {"stability": 0.45, "similarity_boost": 0.82, "style": 0.35, "use_speaker_boost": True},
        }).encode("utf-8")
        req = urllib.request.Request(
            f"https://api.elevenlabs.io/v1/text-to-speech/{voice_id}?output_format=mp3_44100_128",
            data=body, method="POST",
            headers={"Content-Type": "application/json", "Accept": "audio/mpeg"},
        )
        try:
            _, _, audio = _el_request(req, timeout=45)
            return Response(audio, media_type="audio/mpeg", headers={
                "Access-Control-Allow-Origin": "*", "Cache-Control": "no-store"})
        except urllib.error.HTTPError as exc:
            return _json({"ok": False, "error": "elevenlabs_tts_error", "status": exc.code}, 502)
        except Exception as exc:
            return _json({"ok": False, "error": type(exc).__name__}, 500)

    print("BATALLA MATEMÁTICA v20: voz ElevenLabs instalada.", flush=True)
