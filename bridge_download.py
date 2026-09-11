from __future__ import annotations

from io import BytesIO
from pathlib import Path
from zipfile import ZIP_DEFLATED, ZipFile

from starlette.responses import Response


DOWNLOAD_PATH = "/downloads/SieRoom-Classroom-Bridge-0.8.7-R6.2-TRIPLE-CONTRACT.zip"
ARCHIVE_NAME = "SieRoom-Classroom-Bridge-0.8.7-R6.2-TRIPLE-CONTRACT.zip"


def _build_zip() -> bytes:
    root = Path(__file__).resolve().parent / "browser_extension"
    if not root.exists():
        raise RuntimeError("No existe la carpeta browser_extension en el despliegue.")

    buffer = BytesIO()
    with ZipFile(buffer, "w", ZIP_DEFLATED) as zf:
        for path in sorted(root.rglob("*")):
            if not path.is_file():
                continue
            arcname = Path("SieRoom_Classroom_Bridge_0.8.7_R6.2_TRIPLE_CONTRACT") / path.relative_to(root)
            zf.write(path, arcname.as_posix())
    return buffer.getvalue()


def install(mcp) -> None:
    if not getattr(mcp, "_sieroom_bridge_download_installed", False):
        @mcp.custom_route(DOWNLOAD_PATH, methods=["GET"])
        async def download_bridge(_request):
            payload = _build_zip()
            return Response(content=payload, media_type="application/zip", headers={"Content-Disposition": f'attachment; filename="{ARCHIVE_NAME}"', "Cache-Control": "no-store"})
        setattr(mcp, "_sieroom_bridge_download_installed", True)

    if not getattr(mcp, "_battle_identity_v17_installed", False):
        from battle_identity_v17 import install as install_battle_identity
        install_battle_identity(mcp)
        setattr(mcp, "_battle_identity_v17_installed", True)

    if not getattr(mcp, "_battle_simple_access_installed", False):
        from battle_simple_access import install as install_battle_simple_access
        install_battle_simple_access(mcp)
        setattr(mcp, "_battle_simple_access_installed", True)

    if not getattr(mcp, "_battle_quick_school_login_installed", False):
        from battle_quick_school_login import install as install_battle_quick_school_login
        install_battle_quick_school_login(mcp)
        setattr(mcp, "_battle_quick_school_login_installed", True)

    if not getattr(mcp, "_battle_ranking_live_fix_installed", False):
        from battle_ranking_live_fix import install as install_battle_ranking_live_fix
        install_battle_ranking_live_fix(mcp)
        setattr(mcp, "_battle_ranking_live_fix_installed", True)

    if not getattr(mcp, "_battle_voice_v20_installed", False):
        from battle_voice_v20 import install as install_battle_voice
        install_battle_voice(mcp)
        from battle_voice_bootstrap import run_once as run_battle_voice_bootstrap
        run_battle_voice_bootstrap()
        setattr(mcp, "_battle_voice_v20_installed", True)

    if not getattr(mcp, "_profe_johnny_mobile_v2_installed", False):
        from profe_johnny_mobile_v2 import install as install_profe_johnny_mobile_v2
        install_profe_johnny_mobile_v2(mcp)

    if not getattr(mcp, "_profe_johnny_identity_v4_installed", False):
        from profe_johnny_identity_v4 import install as install_profe_johnny_identity_v4
        install_profe_johnny_identity_v4(mcp)
