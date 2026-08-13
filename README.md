# Santa Rita Escolar MCP

Servidor MCP privado para integrar ChatGPT con Google Classroom y SieWeb.

## Seguridad

- No contiene credenciales, cookies ni tokens.
- Se niega a iniciar en remoto si no se configuran `AUTH0_ISSUER` y `AUTH0_AUDIENCE`.
- Los secretos de Google y SieWeb se cargan solo como variables de entorno en Render.
- Las operaciones de escritura exigen confirmación lógica (`confirmed=true`) además de la confirmación de ChatGPT.

## Render

- Runtime: Python 3
- Build command: `pip install -r requirements.txt`
- Start command: `python -m app.server`
- Endpoint MCP: `https://<servicio>.onrender.com/mcp`

## Funciones principales

Google Classroom: cursos, estudiantes, tareas, entregas, pendientes, creación de tareas y calificación.

SieWeb: login automático, mensajes, respuestas, registro de notas, calificaciones, criterios/desempeños y conclusiones descriptivas.

Conclusiones descriptivas: solo B/C, máximo 500 caracteres y con estructura de logro, mejora y sugerencia.
