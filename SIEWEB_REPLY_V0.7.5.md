# SieRoom SRC 0.7.5 — respuesta segura en hilos SIEweb

## Problema corregido

En v0.7.4, `send_reply` construía la respuesta con datos proporcionados por el llamador y convertía `reply_to_message_id` a texto antes de enviarlo como `idEdition`. En intentos reales SIEweb devolvió `estado=0` / `e0001`, por lo que la respuesta no quedaba enviada.

## Cambios de v0.7.5

1. Antes de responder, SieRoom relee el mensaje original con `HyoMensajeria/obtDetalle`.
2. Usa el `idEdition` que venga en el detalle si existe. Si no existe, usa el `idMensaje` original como entero.
3. `idEdition` ya no se serializa deliberadamente como string.
4. El asunto se conserva desde el mensaje original cuando no se indica uno explícitamente.
5. El destinatario puede resolverse desde campos explícitos de remitente/emisor. Nunca se toma un `USUCOD` global al azar del detalle.
6. Se añadió `sieweb_messaging action=prepare_reply` para verificar el contexto del hilo sin enviar.
7. `send_reply` solo devuelve `sent=true` si la respuesta del proveedor tiene `estado=1`.
8. `estado=0`, incluido `e0001`, se convierte en error explícito y jamás se presenta como un envío exitoso.

## Flujo recomendado

- Leer el mensaje exacto.
- Preparar la respuesta con `prepare_reply`.
- Revisar `recipient_codes`, `subject`, `reply_to_message_id` y `edition_id`.
- Enviar con `reply` y `confirmed=true`.

El flujo `reply` mantiene la conversación existente. No usa el flujo de correo nuevo.

## Nota sobre la API privada

Los endpoints de SIEweb usados por SieRoom son una integración privada observada en la cuenta autorizada; SIEweb no publica un contrato estable de esta API. Las pruebas locales validan la construcción del payload y el manejo de respuestas, pero la confirmación definitiva del proveedor sigue siendo `estado=1` en el entorno real.
