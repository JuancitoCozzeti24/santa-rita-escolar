# SieRoom Classroom Bridge 0.7.3 — RESET de cola

## Problema que resuelve

Un trabajo podía quedar en estado `claimed` si la pestaña de Classroom, el content script o la propia pestaña del bridge se bloqueaban. Aunque el lease vencía después, durante ese tiempo parecía que la cola estaba atascada. Además, la UI mostraba también estados históricos, lo que podía confundirse con trabajos realmente pendientes.

## Solución

- Nuevo endpoint autenticado: `POST /bridge/v1/reset`.
- Devuelve todos los `claimed` a `queued` inmediatamente.
- Conserva los trabajos que ya estaban `queued`.
- No borra `completed`, `cancelled` ni el historial.
- Por defecto no reintenta `failed`.
- Nuevo botón **RESET / DESATASCAR COLA** en popup y pestaña del bridge.
- Watchdog local de 120 s.
- Procesamiento continuo de hasta 50 trabajos por ciclo sin pausa artificial de 3 s entre trabajos.
- El estado muestra `work_remaining`, que solo cuenta trabajo real: `queued + claimed`.

## API

`POST /bridge/v1/reset`

Body opcional:

```json
{
  "retry_failed": false
}
```

También puede invocarse desde la herramienta MCP:

`classroom_private_feedback(action="reset", confirmed=true)`

Esto permite que ChatGPT y la extensión compartan la misma lógica de recuperación.
