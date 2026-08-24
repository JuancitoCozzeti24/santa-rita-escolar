from __future__ import annotations

# Núcleo completo de SieRoom v0.8.7 conservado sin cambios.
from server_core import *  # noqa: F401,F403

# Reactiva el módulo de asistencia/asesoría que ya existe en el repositorio.
from attendance import install as install_attendance

install_attendance(mcp, sieweb, settings, classroom)
setattr(mcp, "_sieroom_attendance_installed", True)
print("SieRoom Asistencia: rutas /asesoria restauradas.", flush=True)


if __name__ == "__main__":
    mcp.run(transport="streamable-http")
