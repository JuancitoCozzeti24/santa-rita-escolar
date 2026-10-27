# Preparación para Cloud Run

Esta rama agrega un contenedor de prueba para el servicio MCP principal. No cambia el servicio de Render ni la extensión activa.

## Inicio

- Imagen: `Dockerfile.cloudrun`
- Comando: `python server.py`
- El servidor lee `PORT` y `MCP_HOST`; Cloud Run proporciona `PORT` y el host predeterminado ya es `0.0.0.0`.
- `/mcp` es el endpoint MCP del servidor FastMCP.

## Configuración requerida

Configurar los valores fuera del repositorio, preferentemente como secretos del servicio:

- `AUTH0_ISSUER`, `AUTH0_AUDIENCE`, `AUTH0_REQUIRED_SCOPE`
- `GOOGLE_CLIENT_ID`, `GOOGLE_CLIENT_SECRET`, `GOOGLE_REFRESH_TOKEN`
- `CLASSROOM_BRIDGE_SECRET`
- `SIEWEB_USER`, `SIEWEB_PASSWORD`; solo si el cliente necesita también las credenciales opcionales de sesión, `SIEWEB_COOKIE` y `SIEWEB_AUTHORIZATION`
- `BITACORA_SPREADSHEET_ID`, `SIEWEB_BASE_URL`

No guardar secretos en GitHub ni en archivos de imagen. La audiencia de Auth0 y el host de la extensión Classroom deberán cambiarse después de conocer la URL real de Cloud Run.

## Riesgo de estado que bloquea el uso real

La cola de trabajos del puente Classroom está en memoria de proceso (`bridge.py`). Cloud Run puede apagar instancias cuando escala a cero y no garantiza que las solicitudes futuras vayan al mismo proceso. Una cola pendiente podría perderse o quedar invisible tras un reinicio. Antes de habilitar operaciones reales de comentarios, notas o devolución, hay que sustituir la cola por almacenamiento persistente y probar su recuperación. Esta preparación no incluye un servicio de almacenamiento externo.

## Costos y despliegue

Usar facturación por solicitud, mínimo de instancias 0 y un máximo bajo de instancias; esos límites reducen consumo, pero no garantizan gasto cero. Crear el servicio de prueba requiere un proyecto con facturación configurada. No desplegar hasta resolver el almacenamiento de la cola, verificar los secretos fuera del repositorio y validar que el costo de todos los recursos asociados es aceptable.
