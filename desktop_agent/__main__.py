from __future__ import annotations

import argparse

from .browser import SchoolBrowser
from .runner import AgentRunner
from .settings import DesktopSettings


def main() -> None:
    parser = argparse.ArgumentParser(description="SieRoom Desktop Agent visual-first")
    parser.add_argument("tab", nargs="?", choices=("classroom", "cieweb"))
    parser.add_argument("goal", nargs="?", help="Orden docente concreta para la pestaña")
    parser.add_argument("--max-steps", type=int, default=80)
    args = parser.parse_args()
    settings = DesktopSettings.from_env()
    runner = AgentRunner(settings)
    if args.tab and args.goal:
        runner.run(args.tab, args.goal, args.max_steps)
        return
    with SchoolBrowser(settings) as browser:
        print("Classroom y CIEweb están abiertos.")
        tab = args.tab or input("¿Qué pestaña trabajaremos? [classroom/cieweb]: ").strip().lower()
        if tab not in {"classroom", "cieweb"}:
            raise SystemExit("Elige classroom o cieweb.")
        goal = args.goal or input("Orden para el agente: ").strip()
        if not goal:
            raise SystemExit("La orden no puede estar vacía.")
        runner.run_with_browser(browser, tab, goal, args.max_steps)


if __name__ == "__main__":
    main()
