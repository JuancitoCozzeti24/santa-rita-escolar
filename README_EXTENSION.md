# SieRoom Classroom Bridge 0.7.17

Este componente local permite que SieRoom lea y publique **comentarios privados nativos** en entregas de Google Classroom usando la sesión ya iniciada en Chrome.

- No copia ni envía cookies de Google a Render.
- No guarda el `GOOGLE_REFRESH_TOKEN` en la extensión.
- Render solo mantiene una cola temporal de trabajos y recibe el texto leído o la confirmación de que el comentario se publicó.
- La nota y la devolución se siguen haciendo por la API oficial de Classroom después de confirmar el comentario.

## Instalación

1. Descomprime esta carpeta.
2. Chrome/Brave → `chrome://extensions` → activa **Modo de desarrollador**.
3. **Cargar descomprimida** → selecciona la carpeta `browser_extension`.
4. En Render agrega `CLASSROOM_BRIDGE_SECRET` con un valor aleatorio largo.
5. Abre la extensión, pega exactamente el mismo valor en `CLASSROOM_BRIDGE_SECRET` y pulsa **Guardar y probar**.
6. Pulsa **Iniciar puente** y deja abierta la pestaña del puente mientras SieRoom procesa entregas.
7. Mantén iniciada en Classroom la cuenta docente correcta.

Si Google cambia la interfaz de Classroom, el puente puede necesitar una actualización de selectores. Las demás capacidades de SieRoom siguen usando las APIs oficiales.

## Lectura de comentarios privados — protegido en 0.7.17

- La operación `read_private_comments` abre la entrega real y localiza exclusivamente el panel **Comentarios privados**.
- Reconoce retroalimentaciones estructuradas mediante encabezados como “Lo que hizo bien”, “Lo que debe mejorar”, “Sugerencias”, “Nota cuantitativa” y “Calificación cualitativa”.
- Devuelve el texto asociado al `submission_id` sin escribir ni pulsar Enviar.
- El servidor admite lectura individual (`read`) y de todas las entregas de una tarea (`read_all`).
- La extensión anuncia sus capacidades en cada consulta. Las copias antiguas no pueden reclamar trabajos de lectura.
- El servidor rechaza cualquier respuesta que no incluya una lista real de comentarios y un conteo coherente.


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
