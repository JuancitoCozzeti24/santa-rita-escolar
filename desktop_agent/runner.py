from __future__ import annotations

from typing import Callable

from .browser import SchoolBrowser
from .journal import OperationJournal
from .settings import DesktopSettings
from .vision import VisionPlanner


CRITICAL = {"comment", "grade", "return", "create_performance", "save_cieweb_grades", "send_message"}


class AgentRunner:
    def __init__(self, settings: DesktopSettings, confirm: Callable[[str], bool] | None = None) -> None:
        self.settings = settings
        self.confirm = confirm or (lambda prompt: input(f"{prompt} [s/N]: ").strip().lower() in {"s", "si", "sí"})
        self.journal = OperationJournal(settings.data_dir / "operations.sqlite3")

    def run(self, tab: str, goal: str, max_steps: int = 80) -> None:
        with SchoolBrowser(self.settings) as browser:
            self.run_with_browser(browser, tab, goal, max_steps)

    def run_with_browser(self, browser: SchoolBrowser, tab: str, goal: str, max_steps: int = 80) -> None:
        history: list[dict[str, object]] = []
        pending_key: str | None = None
        if self.settings.backend_url:
            from .backend import BackendConnection, BackendVisionPlanner
            planner = BackendVisionPlanner(BackendConnection(self.settings))
        else:
            planner = VisionPlanner(self.settings)
        for step in range(1, max_steps + 1):
            observation = browser.observe(tab)
            decision = planner.decide(goal, observation, history)
            print(f"[{step}] {decision.reason}", flush=True)
            if pending_key is not None:
                if decision.previous_effect_verified is True:
                    self.journal.transition(pending_key, "completed", {"verified_at_step": step})
                    pending_key = None
                elif decision.previous_effect_verified is False:
                    self.journal.transition(
                        pending_key, "failed", {"reason": "La captura posterior no confirmó el efecto."}
                    )
                    raise RuntimeError("La interfaz no confirmó la última operación crítica.")
                else:
                    raise RuntimeError("El modelo omitió verificar la última operación crítica.")
            if decision.done:
                print("Objetivo verificado.", flush=True)
                return
            if not decision.action:
                raise RuntimeError("El planificador no devolvió una acción.")
            effect = decision.critical_effect
            if effect:
                if effect not in CRITICAL:
                    raise RuntimeError(f"Efecto crítico desconocido: {effect}")
                target = {"tab": tab, "url": observation.url, "goal": goal}
                operation, inserted = self.journal.reserve(effect, target, decision.action)
                if not inserted and operation.status == "completed":
                    raise RuntimeError("Operación crítica ya completada; se bloqueó su repetición.")
                if not self.confirm(f"Autorizar efecto crítico '{effect}': {decision.reason}"):
                    self.journal.transition(operation.key, "cancelled")
                    raise RuntimeError("Operación cancelada por el docente.")
                self.journal.transition(operation.key, "executing")
                try:
                    browser.execute(tab, decision.action)
                except Exception as exc:
                    self.journal.transition(operation.key, "failed", {"error": str(exc)})
                    raise
                self.journal.transition(operation.key, "verifying", {"executed_at_step": step})
                pending_key = operation.key
            else:
                browser.execute(tab, decision.action)
            history.append({
                "step": step,
                "url": observation.url,
                "action": decision.action,
                "reason": decision.reason,
                "pending_effect_key": pending_key,
            })
        raise RuntimeError(f"El objetivo no terminó después de {max_steps} pasos.")
