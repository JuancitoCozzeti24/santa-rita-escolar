# Instalación SieRoom SRC 0.7.3

## A. Subir servidor a GitHub/Render

1. Sube todos los archivos de este paquete a la raíz del repositorio, reemplazando los anteriores.
2. Haz Commit.
3. En Render agrega una variable nueva:
   - Nombre: `CLASSROOM_BRIDGE_SECRET`
   - Valor: un secreto aleatorio largo. Puedes obtenerlo ejecutando `py generar_bridge_secret.py` en tu PC.
4. Guarda cambios y espera a que Render quede `LIVE`.
5. En ChatGPT → Complementos → SieRoom → `Actualizar` para volver a leer las acciones.

## B. Instalar el puente en Chrome/Brave

1. Copia/descomprime la carpeta `browser_extension` en un lugar fijo del PC.
2. Abre `chrome://extensions` (en Brave también funciona esa dirección).
3. Activa `Modo de desarrollador`.
4. Pulsa `Cargar descomprimida`.
5. Selecciona la carpeta `browser_extension` (la que contiene `manifest.json`).
6. Abre la extensión `SieRoom Classroom Bridge`.
7. Servidor: deja `https://santa-rita-escolar-tcpb.onrender.com`.
8. En `CLASSROOM_BRIDGE_SECRET`, pega exactamente el mismo secreto guardado en Render.
9. Pulsa `Guardar y probar`. Debe indicar conexión correcta y versión 0.7.3.
10. Pulsa `Iniciar puente` y deja abierta esa pestaña mientras procesas entregas.
11. Asegúrate de estar iniciado en `classroom.google.com` con la cuenta docente correcta.

## C. Prueba segura

En ChatGPT:

`@SieRoom SRC ejecuta classroom_private_feedback con action=status. No modifiques nada.`

Debe indicar `bridge_configured: true`.

Después prueba con una sola entrega y un comentario inocuo. Primero pide previsualización (`confirmed=false`). Tras aprobarlo, encola (`confirmed=true`). El navegador publicará el comentario privado y SieRoom informará el estado del trabajo.

## D. Flujo completo

Para una entrega revisada:

1. SieRoom abre/revisa adjunto.
2. Redacta comentario privado individual.
3. Encola `classroom_private_feedback` con el comentario.
4. Opcionalmente incluye `grade` y `return_after_comment=true`.
5. El puente publica el comentario.
6. Solo después SieRoom pone la nota y devuelve por API oficial.

## Seguridad

No pegues cookies de Google, `SAPISID`, `SID`, tokens de sesión ni el `GOOGLE_REFRESH_TOKEN` en la extensión. El puente solo necesita `CLASSROOM_BRIDGE_SECRET`.
