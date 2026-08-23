# SieRoom SRC 0.7.16 — lectura de comentarios privados

## Objetivo

SieRoom Classroom Bridge ya publicaba comentarios privados en la interfaz autenticada de Google Classroom. La v0.7.16 añade el camino inverso: recuperar los comentarios existentes y devolverlos a ChatGPT vinculados con la entrega correcta.

## Flujo

1. SieRoom obtiene el `alternateLink` oficial de cada `StudentSubmission`.
2. El servidor encola un trabajo `read_private_comments` sin texto para publicar.
3. La extensión abre la entrega con la sesión docente local.
4. El content script localiza el panel **Comentarios privados** y excluye el editor y los controles de interfaz.
5. Prioriza retroalimentación estructurada con marcadores pedagógicos y elimina contenedores DOM duplicados.
6. La extensión devuelve `count`, `comments`, `submission_id` y el método de lectura.
7. El servidor conserva temporalmente el resultado en el trabajo completado para que `action=list` o `action=job` puedan recuperarlo.

## Herramientas

- `classroom_private_feedback action=read`: una entrega.
- `classroom_private_feedback action=read_all`: todas las entregas de una tarea.
- `classroom_private_feedback action=list`: resultados filtrables por curso, tarea, operación y estado.

## Protecciones

- La lectura no escribe comentarios, notas ni estados de devolución.
- Las cookies de Google permanecen en el navegador local.
- Render solo recibe el texto que la extensión extrajo del panel privado.
- La ruta de publicación previa conserva la exigencia de confirmación y la secuencia comentario → nota → devolución.
