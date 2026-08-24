# SieRoom Classroom Bridge 0.8.7

Este componente local permite que SieRoom lea y publique **comentarios privados nativos** en entregas de Google Classroom usando la sesión ya iniciada en Chrome.

- No copia ni envía cookies de Google a Render.
- No guarda el `GOOGLE_REFRESH_TOKEN` en la extensión.
- Render solo mantiene una cola temporal de trabajos y recibe el texto leído o la confirmación de que el comentario se publicó.
- La nota y la devolución pueden confirmarse en la misma sesión local del navegador, sin exponer la sesión de Google a Render.

## Instalación

1. Descomprime esta carpeta.
2. Chrome/Brave → `chrome://extensions` → activa **Modo de desarrollador**.
3. **Cargar descomprimida** → selecciona la carpeta `browser_extension`.
4. En Render agrega `CLASSROOM_BRIDGE_SECRET` con un valor aleatorio largo.
5. Abre la extensión, pega exactamente el mismo valor en `CLASSROOM_BRIDGE_SECRET` y pulsa **Guardar y probar**.
6. Pulsa **Iniciar puente** y deja abierta la pestaña del puente mientras SieRoom procesa entregas.
7. Mantén iniciada en Classroom la cuenta docente correcta.

Si Google cambia la interfaz de Classroom, el puente puede necesitar una actualización de selectores. Las demás capacidades de SieRoom siguen usando las APIs oficiales.

## Cuenta docente, lectura privada y destino — protegido en 0.8.7

- La operación `read_private_comments` abre la entrega real y localiza exclusivamente el panel **Comentarios privados**.
- Nunca busca comentarios en `document.body`: exige una región acotada que contenga el editor privado del alumno actual.
- Reconoce retroalimentaciones estructuradas mediante encabezados como “Lo que hizo bien”, “Lo que debe mejorar”, “Sugerencias”, “Nota cuantitativa” y “Calificación cualitativa”.
- Devuelve el texto asociado al `submission_id` sin escribir ni pulsar Enviar.
- El servidor admite lectura individual (`read`) y de todas las entregas de una tarea (`read_all`).
- El popup exige y guarda el correo docente de Classroom.
- Cada entrega se abre con `authuser=<correo>` y se verifica la cuenta activa antes de cualquier lectura o escritura. Que el correo aparezca como cuenta secundaria ya no es suficiente.
- Si aparece una cuenta diferente, la cola se pausa sin publicar, calificar ni devolver.
- Los flujos de comentario, calificación y devolución de v0.8.0 permanecen disponibles.
- La extensión anuncia `verified_private_comment_read_v4`, `student_scoped_private_comment_read` y `target_submission_guard`. Las copias antiguas no pueden reclamar trabajos.
- El lector descarta “Instrucciones”, “Trabajo de los alumnos”, “Más opciones” y otros textos de navegación.
- Chrome no acepta `status=complete` hasta que la ruta coincida con curso, tarea y alumno solicitados.
- El servidor exige URL de destino, fuente verificada, método v0.8.7 y objetos de comentario estructuralmente válidos.
- Si Classroom oculta el encabezado en un hilo todavía vacío, se exige el editor explícitamente privado y su botón Publicar/Enviar cercano dentro de una región acotada.
- “Ayuda y comentarios” nunca se acepta como botón de publicación; el texto completo se valida antes de pulsar y el comentario se relee antes de calificar o devolver.
- Si lectura y escritura son del mismo alumno, se conserva la vista validada; solo se navega al cambiar de entrega.
- Si una pestaña conserva un `content.js` anterior, el Bridge compara versiones y reinyecta el archivo actual.
- La versión del servidor debe coincidir exactamente con la extensión antes de procesar la cola.
- Si se abren varias pestañas del Bridge, solo la primera actúa como líder; las demás quedan en espera.
- Pulsar **Procesar cola ahora** durante un trabajo no lo cancela ni deja el `claim` atascado.


## Cambios en 0.7.2

- Detecta el editor aunque Classroom muestre primero un contenedor `Añade un comentario…`.
- Amplía la detección de `textarea`, `input`, `role=textbox` y `contenteditable`.
- Mantiene como condición de seguridad la presencia de la sección `Comentarios privados`.
- Añade diagnóstico de selectores si Google vuelve a cambiar la interfaz.


## RESET / DESATASCAR COLA — nuevo en 0.7.3

El botón **RESET / DESATASCAR COLA** no borra trabajos pendientes. Hace tres cosas:

1. Libera inmediatamente cualquier trabajo que quedó `claimed` por una pestaña/bridge bloqueado y lo devuelve a `queued`.
2. Reinicia el estado local `busy` del bridge.
3. Empieza a procesar la cola inmediatamente y de forma continua, sin esperar 3 segundos entre cada trabajo.

También hay un watchdog: si un trabajo local supera aproximadamente 120 segundos, el puente intenta un RESET automático para que un único caso no bloquee todos los siguientes.

Los trabajos `failed` NO se reintentan automáticamente con RESET; se conservan para revisión y pueden reintentarse de manera explícita desde SieRoom.
