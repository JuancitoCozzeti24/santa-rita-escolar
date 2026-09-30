# Johnny WhatsApp Assistant — v0.2.0

Complemento privado para trabajar con la **sesión oficial de WhatsApp Web del propio usuario**.

## Novedades de v0.2.0

- Corrige la identificación del chat para evitar confundir el encabezado principal con “Información del perfil”.
- La lectura del chat abierto ya no depende únicamente de los mensajes visibles: desplaza automáticamente el historial hacia arriba.
- Devuelve indicadores de control (`returned`, `collected_unique`, `scrolls`, `reached_history_top`, `truncated`) para no afirmar que una lectura fue completa cuando no lo fue.
- Añade una operación de lectura por chat y rango de fechas: abre el chat por título, recorre el historial y filtra los mensajes entre `from_date` y `to_date`.
- Al terminar una lectura extensa, vuelve al final del chat.
- Mantiene la protección de envío: ningún mensaje se envía sin autorización explícita y sin verificar el título del chat.

## Herramientas

- `whatsapp_bridge_status`
- `whatsapp_read_current_chat`
- `whatsapp_read_chat_history`
- `whatsapp_list_visible_chats`
- `whatsapp_send_message`
- `whatsapp_job_status`

## Lectura del chat abierto

`whatsapp_read_current_chat(limit=500)` puede recorrer automáticamente mensajes anteriores hasta reunir el límite solicitado o detectar el inicio del historial disponible.

El resultado incluye un bloque `history` que permite comprobar cuántos mensajes se recopilaron y si la lectura fue completa o truncada.

## Lectura por grupo y fechas

`whatsapp_read_chat_history(chat_title, from_date, to_date, limit)`

- `chat_title`: título del chat o grupo.
- `from_date`: obligatorio, formato `YYYY-MM-DD`.
- `to_date`: opcional, formato `YYYY-MM-DD`.
- `limit`: máximo de mensajes devueltos, hasta 1500.

La extensión intenta localizar el chat en la barra lateral; si no está visible, utiliza el buscador lateral de WhatsApp Web y lo abre antes de leer.

## Seguridad

El servidor no recibe cookies ni credenciales de sesión de WhatsApp. La extensión actúa únicamente sobre `https://web.whatsapp.com/`.

Para enviar un mensaje:
1. ChatGPT debe haber recibido autorización explícita.
2. El chat abierto debe coincidir con el destinatario esperado.
3. WhatsApp debe confirmar el envío dejando vacío el cuadro de escritura.

## Instalación de la extensión

1. Abrir `chrome://extensions` o `edge://extensions`.
2. Activar **Modo desarrollador**.
3. Elegir **Cargar descomprimida** y seleccionar la carpeta `browser_extension/`.
4. Guardar en el popup el endpoint del servidor y el mismo `WHATSAPP_BRIDGE_SECRET`.
5. Abrir WhatsApp Web normalmente.
6. Abrir la pestaña del puente y mantenerla activa mientras se use el complemento.
