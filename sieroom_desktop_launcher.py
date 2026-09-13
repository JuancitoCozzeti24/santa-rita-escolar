"""Punto de entrada estable para el ejecutable Windows de SieRoom."""

from __future__ import annotations

import traceback


def run() -> None:
    try:
        from desktop_agent.windows_launcher import main
        main()
    except BaseException as exc:
        print("\n" + "=" * 62)
        print("SIEROOM DESKTOP AGENT — ERROR DE ARRANQUE")
        print("=" * 62)
        print(f"{type(exc).__name__}: {exc}")
        print("\nDetalle técnico:")
        traceback.print_exc()
        input("\nPresiona Enter para cerrar...")


if __name__ == "__main__":
    run()
