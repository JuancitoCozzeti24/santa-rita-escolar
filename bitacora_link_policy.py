from __future__ import annotations

BITACORA_LINK_POLICY = """
POLÍTICA DE ENLACE DE VERIFICACIÓN DE BITÁCORA:
1. Cada vez que bitacora_docente complete correctamente una escritura en BITÁCORA o ACADÉMICO, la respuesta al docente debe incluir siempre el enlace directo al Google Sheet maestro para verificación visual opcional.
2. Enlace oficial de la bitácora: https://docs.google.com/spreadsheets/d/13QYo-Dx23LPzKbY7szrz1HWyOMgQwKP5_oriGKKCNnA/edit
3. Presenta el enlace con una etiqueta clara, por ejemplo: “Verificar visualmente en la bitácora”.
4. No omitas el enlace aunque la escritura ya haya sido verificada automáticamente por API. La verificación visual es opcional para el docente, pero el enlace debe ofrecerse siempre.
5. Esta regla aplica tanto a registros conductuales/convivencia como a registros académicos.
""".strip()


def install(mcp) -> None:
    current = str(getattr(mcp, "instructions", "") or "").strip()
    if BITACORA_LINK_POLICY in current:
        return
    combined = (current + "\n\n" + BITACORA_LINK_POLICY).strip()
    try:
        setattr(mcp, "instructions", combined)
    except Exception:
        pass
    if hasattr(mcp, "_mcp_server"):
        mcp._mcp_server.instructions = combined
    print("SieRoom Bitácora: política de enlace de verificación instalada.", flush=True)
