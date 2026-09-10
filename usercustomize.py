from __future__ import annotations

import functools


def _install_battle_accounts_bootstrap() -> None:
    try:
        from mcp.server.fastmcp import FastMCP
    except Exception:
        return

    original_init = FastMCP.__init__
    if getattr(original_init, "_battle_accounts_bootstrap", False):
        return

    @functools.wraps(original_init)
    def init_with_battle_accounts(self, *args, **kwargs):
        original_init(self, *args, **kwargs)
        try:
            from battle_accounts import install as install_battle_accounts
            install_battle_accounts(self)
            print("BATALLA MATEMÁTICA: bootstrap de cuentas online activo.", flush=True)
        except Exception as exc:
            print(f"BATALLA MATEMÁTICA: error instalando cuentas online: {exc}", flush=True)

    setattr(init_with_battle_accounts, "_battle_accounts_bootstrap", True)
    FastMCP.__init__ = init_with_battle_accounts


_install_battle_accounts_bootstrap()
