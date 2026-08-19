# SieRoom SRC 0.7.3 — Comentarios privados de Classroom

## Qué resuelve

Google Classroom no expone una operación pública para escribir el comentario privado nativo de una entrega. SieRoom 0.7.3 añade un **puente local de navegador** para esa única acción y conserva las APIs oficiales para lectura de entregas, Drive, notas y devolución.

## Arquitectura

1. ChatGPT/SieRoom revisa el adjunto con las herramientas existentes.
2. ChatGPT redacta la retroalimentación individual.
3. `classroom_private_feedback(action="queue")` obtiene el `alternateLink` real de `StudentSubmission` y crea un trabajo temporal.
4. La extensión local consulta `/bridge/v1/next` usando `CLASSROOM_BRIDGE_SECRET`.
5. La extensión abre el `alternateLink`, localiza **Comentarios privados**, escribe el texto y pulsa el botón de publicar/enviar.
6. La extensión confirma a `/bridge/v1/jobs/{id}/complete`.
7. Si se indicó `grade` o `return_after_comment`, Render ejecuta esas operaciones por la API oficial **después** de confirmar el comentario.

## Herramienta MCP

### `classroom_private_feedback`

Acciones:

- `status`: diagnóstico del puente y de la cola.
- `queue`: un comentario privado, con nota/devolución opcional.
- `queue_batch`: varios comentarios ya revisados/aprobados.
- `job`: estado de un trabajo.
- `list`: trabajos recientes.
- `retry`: reencola un trabajo fallido.
- `cancel`: cancela un trabajo todavía no procesado.

Las escrituras mantienen el patrón de confirmación de SieRoom: `confirmed=false` produce previsualización y `confirmed=true` encola.

## Variable nueva de Render

`CLASSROOM_BRIDGE_SECRET`

Debe ser un secreto aleatorio largo y diferente de las credenciales de Google/Auth0/SieWeb. El mismo valor se configura localmente en la extensión.

## Limitaciones deliberadas

- El puente depende de la interfaz web de Classroom; Google puede cambiar sus selectores.
- No se guardan cookies ni tokens web en Render.
- La cola está en memoria y se pierde si Render reinicia; por seguridad está diseñada para ejecución inmediata.
- Si Classroom cambia la interfaz, solo el puente de comentarios puede fallar; tareas, archivos, notas y devolución oficiales continúan independientes.
