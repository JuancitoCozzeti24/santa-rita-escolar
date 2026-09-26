# Johnny WhatsApp Assistant — v0.1.0

Prototipo privado de lectura/escritura para la **sesión oficial de WhatsApp Web del propio usuario**.

## Alcance de esta primera versión

- Leer los mensajes actualmente cargados del chat abierto.
- Listar chats actualmente visibles/cargados en la barra lateral.
- Enviar un mensaje al chat abierto únicamente cuando:
  1. ChatGPT recibió autorización explícita (`confirmed=true`).
  2. El título del chat abierto coincide con el `chat_title` esperado.
  3. El bridge confirma que WhatsApp vació el cuadro de escritura tras pulsar Enviar.
- Autenticación entre extensión y servidor con `WHATSAPP_BRIDGE_SECRET`.
- Cola con lease para evitar que una orden quede reclamada para siempre si se cierra el navegador.

## Lo que todavía NO hace

- No recorre automáticamente todo el historial de todos los contactos, grupos y canales.
- No cambia todavía de chat por sí solo.
- No descarga adjuntos, audios ni imágenes.
- No responde de forma autónoma sin autorización.
- No intenta iniciar sesión mediante clientes no oficiales.

Estas limitaciones son deliberadas para validar primero lectura y escritura seguras sobre la interfaz oficial de WhatsApp Web.

## Servidor

Variables:

- `WHATSAPP_BRIDGE_SECRET`: secreto largo y aleatorio compartido con la extensión.
- `PORT`: puerto del servicio.
- `MCP_HOST`: normalmente `0.0.0.0`.

Inicio local:

`python server.py`

Endpoint MCP: `/mcp`

Endpoints del bridge:

- `GET /wa/v1/status`
- `GET /wa/v1/next`
- `POST /wa/v1/jobs/{job_id}/complete`
- `POST /wa/v1/jobs/{job_id}/fail`

## Herramientas MCP

- `whatsapp_bridge_status`
- `whatsapp_read_current_chat`
- `whatsapp_list_visible_chats`
- `whatsapp_send_message`
- `whatsapp_job_status`

## Extensión Chrome/Edge

1. Abrir `chrome://extensions` o `edge://extensions`.
2. Activar **Modo desarrollador**.
3. Elegir **Cargar descomprimida** y seleccionar `browser_extension/`.
4. En el popup guardar el endpoint del servidor y el mismo `WHATSAPP_BRIDGE_SECRET`.
5. Abrir WhatsApp Web normalmente y vincularlo solo mediante el procedimiento oficial de WhatsApp.
6. En la extensión pulsar **Abrir puente** y mantener esa pestaña abierta.

## Seguridad v0.1

El servidor nunca recibe cookies ni claves de sesión de WhatsApp. La extensión actúa sobre la pestaña oficial `https://web.whatsapp.com/`. El envío se bloquea si el nombre del chat abierto no coincide con el destinatario solicitado.
