from __future__ import annotations

import json
import os
import uuid
import urllib.request
import urllib.error

import requests
from bitacora import _google_token

VOICE_NAME = "Profe Johnny - Batalla Matematica"
DRIVE_FILE_ID = (os.getenv("BATTLE_VOICE_SAMPLE_DRIVE_ID") or "19hMqYiJfowvxqVQF9Wk3fScCkaYE84J-").strip()


def _multipart(sample: bytes):
    boundary = "----Batalla" + uuid.uuid4().hex
    chunks = [
        f"--{boundary}\r\n".encode(),
        b'Content-Disposition: form-data; name="name"\r\n\r\n',
        VOICE_NAME.encode("utf-8"), b"\r\n",
        f"--{boundary}\r\n".encode(),
        b'Content-Disposition: form-data; name="description"\r\n\r\n',
        b"Voz autorizada del Profe Johnny para Batalla Matematica", b"\r\n",
        f"--{boundary}\r\n".encode(),
        b'Content-Disposition: form-data; name="files"; filename="profe-johnny.mp3"\r\n',
        b"Content-Type: audio/mpeg\r\n\r\n", sample, b"\r\n",
        f"--{boundary}--\r\n".encode(),
    ]
    return boundary, b"".join(chunks)


def _download_sample() -> bytes:
    if not DRIVE_FILE_ID:
        raise RuntimeError("drive_sample_id_missing")
    url = f"https://www.googleapis.com/drive/v3/files/{DRIVE_FILE_ID}?alt=media"
    headers = {"Authorization": f"Bearer {_google_token()}"}
    response = requests.get(url, headers=headers, timeout=45)
    if response.status_code == 401:
        headers["Authorization"] = f"Bearer {_google_token(force=True)}"
        response = requests.get(url, headers=headers, timeout=45)
    if not response.ok:
        raise RuntimeError(f"drive_sample_download_{response.status_code}:{response.text[:300]}")
    if len(response.content) < 10000:
        raise RuntimeError("drive_sample_too_small")
    return response.content


def run_once() -> None:
    if (os.getenv("BATTLE_VOICE_AUTO_BOOTSTRAP") or "").strip() != "1":
        return
    if (os.getenv("ELEVENLABS_VOICE_ID") or "").strip():
        print("BATTLE_VOICE_BOOTSTRAP_SKIPPED=voice_already_configured", flush=True)
        return
    key = (os.getenv("ELEVENLABS_API_KEY") or "").strip()
    if not key:
        print("BATTLE_VOICE_BOOTSTRAP_ERROR=api_key_missing", flush=True)
        return
    try:
        sample = _download_sample()
        print(f"BATTLE_VOICE_SAMPLE_BYTES={len(sample)}", flush=True)
        boundary, body = _multipart(sample)
        req = urllib.request.Request("https://api.elevenlabs.io/v1/voices/add", data=body, method="POST")
        req.add_header("xi-api-key", key)
        req.add_header("Content-Type", f"multipart/form-data; boundary={boundary}")
        req.add_header("User-Agent", "BatallaMatematica/1.0")
        with urllib.request.urlopen(req, timeout=90) as r:
            data = json.loads(r.read().decode("utf-8"))
        voice_id = str(data.get("voice_id") or "").strip()
        if voice_id:
            print(f"BATTLE_VOICE_BOOTSTRAP_RESULT={voice_id}", flush=True)
            print(f"BATTLE_VOICE_REQUIRES_VERIFICATION={bool(data.get('requires_verification'))}", flush=True)
        else:
            print("BATTLE_VOICE_BOOTSTRAP_ERROR=voice_id_missing", flush=True)
    except urllib.error.HTTPError as exc:
        try:
            detail = exc.read().decode("utf-8", "replace")[:1200]
        except Exception:
            detail = str(exc.code)
        print(f"BATTLE_VOICE_BOOTSTRAP_HTTP_ERROR={exc.code}:{detail}", flush=True)
    except Exception as exc:
        print(f"BATTLE_VOICE_BOOTSTRAP_ERROR={type(exc).__name__}:{exc}", flush=True)
