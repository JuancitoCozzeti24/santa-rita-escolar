# SieRoom Classroom Bridge 0.8.6

## Falla real corregida

La v0.8.5 resolvió la lectura de un hilo privado vacío, pero la primera escritura real reveló una ambigüedad distinta: el selector de acciones aceptaba la palabra genérica `comentarios` y podía puntuar **Ayuda y comentarios** como si fuera el control de publicación.

## Cambios

- Se rechazan explícitamente **Ayuda y comentarios**, **Help & feedback** y controles equivalentes.
- Solo se admite una acción con verbo explícito **Enviar/Publicar/Send/Post**.
- Antes de pulsar se verifica que el comentario completo esté cargado en el editor.
- Después de pulsar se vuelve a localizar la región privada acotada y se confirma el comentario mediante el texto completo o dos huellas independientes.
- Si el editor no aparece antes de cualquier escritura, el Bridge recarga una sola vez, vuelve a verificar cuenta y entrega, y reintenta.
- Un fallo ambiguo posterior al clic nunca se reintenta automáticamente.
- Nota y devolución continúan ejecutándose únicamente después de confirmar el comentario.

## Seguridad conservada

- Correo docente activo verificado.
- Ruta exacta de curso, tarea y alumno verificada antes y después de navegar.
- Nunca se usa `document.body` como región privada.
- No se guardan cookies ni tokens de Google en Render.

