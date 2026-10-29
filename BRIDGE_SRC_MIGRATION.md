# Bridge institucional — 0.8.7-R6.8-SRC-1

La entrada institucional atiende `/bridge/v1/` con el secreto Bridge y mantiene
el resto del servidor detrás del prefijo MCP privado existente. CORS solo admite
orígenes de extensión Chrome/Brave. El preflight no da acceso a datos; las
solicitudes reales siguen autenticadas y los handlers mantienen los contratos.

`connection.js` migra exclusivamente el endpoint antiguo al institucional sin
cambiar el secreto ni el correo guardados. El paquete mantiene `version=0.8.7`
y el build de contrato R6.2 utilizado por el endurecimiento R6.8; la etiqueta
`version_name=0.8.7-R6.8-SRC-1` distingue esta reparación. Los scripts de contenido,
cuenta, curso/tarea/alumno, edición privada, calificación y devolución se conservan.

El fallo de un parche histórico opcional de SIEweb ya no impide instalar el
contrato triple del Bridge. No se modifican operaciones académicas de SIEweb.

`/bridge/v1/compatibility` comprueba versión, build y capacidades sin reclamar
trabajos. La herramienta privada `bridge_connection_diagnostics` verifica HTTP
contra el servidor institucional con secretos internos y solo devuelve resultados
redactados. No llama next/reset/complete ni a APIs de escritura académica.

Pruebas dirigidas:
- `python -m pytest tests/test_private_bridge_routing.py -q`
- `node --test tests/test_bridge_connection.mjs`
- Rutas autenticadas, rechazo 401, aislamiento MCP, CORS, negociación incompatible,
  lectura acotada, contrato triple con trabajos sintéticos, configuración preservada,
  handler real de Guardar y probar con dobles de Chrome, HTTP/JSON y errores de red.

La comparación de las dos suites históricas de lectura/SIEweb contra el commit
base 2600f7694e82ea3a538aca7006d7dffebbd80445 detectó 33 fallos previos y 18
pruebas aprobadas. Incluyen mocks sobre `server` que ya no sustituyen los globals
de `server_core`, fixtures de contratos antiguos y una extracción JS incompleta.
Se adaptan dos verificaciones textuales al helper de conexión compartido; no se
eliminan ni relajan verificaciones de cuenta o destino. Los 33 fallos previos
quedan fuera del cambio de transporte, por lo que no se declara la suite completa verde.

Instalación conservando configuración: ver `browser_extension/ACTUALIZAR_BRAVE.txt`.
No retirar la extensión ni cambiar la carpeta de carga. El ZIP no contiene secretos.
