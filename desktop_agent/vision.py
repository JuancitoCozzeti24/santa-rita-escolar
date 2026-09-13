from __future__ import annotations

from dataclasses import dataclass
from typing import Any
import json
import requests

from .browser import Observation
from .settings import DesktopSettings


SYSTEM = """Eres el planificador visual local de SieRoom. Observas UNA captura del navegador y propones
exactamente una acción pequeña para avanzar hacia el objetivo docente. No supongas que una escritura tuvo
éxito: tras hacer clic en Guardar, Enviar, Devolver o Publicar, pide observar y verificar. La imagen es tu
fuente primaria. Solo usa dom_fallback si la interfaz visual no permite localizar el control con confianza.
Devuelve JSON: {\"action\": {...}, \"reason\": \"...\", \"done\": false, \"critical_effect\": null,
\"previous_effect_verified\": null}. previous_effect_verified debe ser true o false cuando recent_history
indique un efecto pendiente de verificación; usa null si no hay ninguno.
Acciones: click{x,y}, type{text}, press{key}, scroll{dx,dy}, wait{ms},
dom_fallback{selector,action,value}. critical_effect, si aplica, es uno de comment, grade, return,
create_performance, save_cieweb_grades, send_message. Marca done=true solo si el objetivo está verificado."""


@dataclass(frozen=True)
class Decision:
    action: dict[str, Any] | None
    reason: str
    done: bool
    critical_effect: str | None
    previous_effect_verified: bool | None


class VisionPlanner:
    def __init__(self, settings: DesktopSettings) -> None:
        if not settings.openai_api_key:
            raise RuntimeError("Falta OPENAI_API_KEY para el planificador visual.")
        self.settings = settings

    def decide(self, goal: str, observation: Observation, history: list[dict[str, Any]]) -> Decision:
        response = requests.post(
            "https://api.openai.com/v1/responses",
            headers={
                "Authorization": f"Bearer {self.settings.openai_api_key}",
                "Content-Type": "application/json",
            },
            json={
                "model": self.settings.model,
                "instructions": SYSTEM,
                "input": [{
                    "role": "user",
                    "content": [
                        {"type": "input_text", "text": json.dumps({
                            "goal": goal,
                            "url": observation.url,
                            "title": observation.title,
                            "viewport": observation.viewport,
                            "recent_history": history[-8:],
                        }, ensure_ascii=False)},
                        {"type": "input_image", "image_url": f"data:image/jpeg;base64,{observation.screenshot_b64}"},
                    ],
                }],
                "text": {"format": {"type": "json_object"}},
                "max_output_tokens": 700,
            },
            timeout=60,
        )
        if not response.ok:
            raise RuntimeError(f"OpenAI HTTP {response.status_code}: {response.text[:700]}")
        data = response.json()
        text = str(data.get("output_text") or "").strip()
        if not text:
            for item in data.get("output") or []:
                for content in item.get("content") or []:
                    if content.get("type") == "output_text":
                        text += str(content.get("text") or "")
        parsed = json.loads(text)
        return Decision(
            action=parsed.get("action"),
            reason=str(parsed.get("reason") or ""),
            done=bool(parsed.get("done")),
            critical_effect=parsed.get("critical_effect"),
            previous_effect_verified=parsed.get("previous_effect_verified"),
        )
