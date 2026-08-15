# SieRoom Classroom Bridge 0.7.0

Este componente local permite que SieRoom publique **comentarios privados nativos** en entregas de Google Classroom usando la sesión ya iniciada en Chrome.

- No copia ni envía cookies de Google a Render.
- No guarda el `GOOGLE_REFRESH_TOKEN` en la extensión.
- Render solo mantiene una cola temporal de trabajos y recibe la confirmación de que el comentario se publicó.
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
