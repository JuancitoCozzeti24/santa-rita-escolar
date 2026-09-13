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

## Flujo específico de Classroom

Primero genera una revisión previa sin modificar Classroom:

```powershell
python -m desktop_agent.classroom_cli --course "2.º B" --task "C3: Nuestro avance en inequaciones" --criteria-file solucionario.txt
```

El curso y la tarea deben coincidir exactamente. Se omiten entregas sin archivo y entregas ya devueltas.
Después de revisar el informe JSON generado en `.sieroom`, se aplica el lote explícitamente:

```powershell
python -m desktop_agent.classroom_cli --course "2.º B" --task "C3: Nuestro avance en inequaciones" --criteria-file solucionario.txt --apply
```

El comentario privado se publica visualmente, sin Bridge. La nota y devolución usan la API oficial de
Classroom y se releen después de cada escritura. Si Google rechaza el permiso o la verificación no coincide,
el lote se detiene en ese alumno. Al repetir el comando, reutiliza revisiones y operaciones ya verificadas.

### Configuración junto al EXE

El ejecutable de prueba lee un archivo `.env` local ubicado en la carpeta desde la que se abre:

```text
OPENAI_API_KEY=...
GOOGLE_CLIENT_ID=...
GOOGLE_CLIENT_SECRET=...
GOOGLE_REFRESH_TOKEN=...
SIEROOM_CIEWEB_URL=https://URL-REAL-DEL-COLEGIO/
```

La compilación nueva muestra un asistente y permite reutilizar el backend de SieRoom con solo
`SIEROOM_BACKEND_URL` y `SIEROOM_BACKEND_SECRET`. El secreto es el mismo configurado en el complemento
Classroom Bridge y se guarda en el Administrador de credenciales de Windows. Se reutiliza automáticamente
aunque el EXE sea reemplazado o movido. Las cuatro credenciales anteriores quedan como
modo alternativo para desarrollo. No se deben subir credenciales a GitHub ni enviarlas dentro del EXE.
