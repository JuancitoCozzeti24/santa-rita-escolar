# SieRoom Desktop Agent (base visual-first)

Esta es la fuente mantenible del agente local. Abre un perfil exclusivo de Chrome y crea dos pestañas:
Google Classroom y CIEweb. El modelo observa capturas de pantalla y actúa por coordenadas. El DOM queda
limitado a respaldo explícito cuando la interfaz visual no permite ubicar un control con confianza.

## Instalación local

```powershell
py -m venv .venv
.venv\Scripts\activate
pip install -r requirements-desktop.txt
playwright install chromium
set OPENAI_API_KEY=...
set SIEROOM_CIEWEB_URL=https://URL-REAL-DEL-COLEGIO/
```

Primera ejecución (abre ambas páginas, conserva las sesiones y luego pregunta qué trabajar):

```powershell
python -m desktop_agent
```

También admite una orden directa:

```powershell
python -m desktop_agent classroom "Abre el ítem C3 Aplicando lo aprendido, sin modificar datos"
```

Para CIEweb:

```powershell
python -m desktop_agent cieweb "Abre el registro de notas de 2.º B, sin modificar datos"
```

Todo efecto crítico pide autorización y se registra en `.sieroom/operations.sqlite3`. Una operación ya
completada con el mismo destino y contenido queda bloqueada para evitar comentarios o notas duplicados.

## Alcance de esta base

Incluye arranque, sesión persistente, observación visual, acciones, respaldo DOM, confirmación y diario
idempotente. Los flujos pedagógicos específicos (descarga/análisis de cada entrega, rúbrica, equivalencia
numérica-literaria, réplica A/B de desempeños y mensajería) deben implementarse como máquinas de estados
sobre esta base; todavía no deben ejecutarse como una orden genérica sin supervisión.
