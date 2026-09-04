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
    if getattr(mcp, "_sieroom_bridge_download_installed", False):
        return

    @mcp.custom_route(DOWNLOAD_PATH, methods=["GET"])
    async def download_bridge(_request):
        payload = _build_zip()
        return Response(
            content=payload,
            media_type="application/zip",
            headers={
                "Content-Disposition": f'attachment; filename="{ARCHIVE_NAME}"',
                "Cache-Control": "no-store",
            },
        )

    setattr(mcp, "_sieroom_bridge_download_installed", True)
