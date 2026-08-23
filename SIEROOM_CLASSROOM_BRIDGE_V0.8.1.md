# SieRoom Classroom Bridge 0.8.1

## Integración realizada

La v0.8.1 combina las protecciones y acciones de v0.8.0 con la lectura privada verificada incorporada después:

- campo obligatorio **Correo docente de Classroom** en el popup;
- almacenamiento local de `teacherEmail` junto con endpoint y secreto;
- apertura de cada entrega con `authuser=<teacherEmail>`;
- detección del correo visible en Classroom mediante texto y atributos accesibles;
- pausa segura si se detecta una cuenta distinta;
- lectura estructurada de comentarios privados;
- publicación idempotente de comentarios;
- calificación y devolución desde el navegador para tareas antiguas;
- negociación de capacidades con Render;
- validación estricta de lectura, nota y devolución en el servidor.

## Garantías

- El correo docente y el secreto permanecen en `chrome.storage.local`.
- Las cookies de Google no se copian ni se envían a Render.
- Una lectura nunca pulsa Enviar ni modifica la calificación.
- Una cuenta distinta detiene el trabajo antes de leer, comentar, calificar o devolver.
- El Nivel de Logro de SIEWeb no participa en este flujo.

## Verificación

La suite completa pasa 59/59 pruebas. También pasan `py_compile`, `node --check` y las comprobaciones de identidad entre las copias raíz y `browser_extension/`.
