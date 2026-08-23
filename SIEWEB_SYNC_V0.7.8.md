# SieRoom SRC 0.7.8 — guardado real del modelo completo de criterios SIEweb

Corrige el fallo observado en v0.7.7: `HyoClaseContenido/insertar` podía devolver `estado: 1` sin persistir el desempeño, y en otros intentos devolver `e0006`.

## Causa corregida

Las versiones 0.7.6/0.7.7 construían el alta a partir de un nodo individual encontrado dentro de `dataInicialPesosCriterios` y enviaban a `insertar` únicamente ese registro. La pantalla de criterios de SIEweb trabaja como un editor por lote: el guardado se realiza sobre la colección completa de registros que alimenta esa pantalla, junto con sus datos de réplica.

## Nuevo comportamiento

- Relee `dataInicialPesosCriterios` inmediatamente antes de escribir.
- Detecta la colección editable completa de criterios/desempeños y evita confundirla con cabeceras o metadatos similares.
- Para un alta, clona un desempeño hermano real dentro de esa misma colección y de la misma capacidad/sección.
- Inserta el nuevo desempeño dentro del modelo completo y conserva todos los demás registros intactos.
- Para una edición, modifica la fila real existente dentro del modelo completo, preservando sus IDs y campos internos.
- Obtiene `datosReplica` desde el propio modelo devuelto por SIEweb cuando está disponible, en lugar de depender de un objeto inventado por el llamador.
- Envía una sola escritura; no reintenta POST a ciegas para evitar duplicados.
- `e0006` o cualquier estado diferente de 1 detiene inmediatamente el flujo.
- Un `estado: 1` ya no se acepta como éxito por sí solo: el desempeño debe aparecer exactamente una vez tanto en el editor (`dataInicialPesosCriterios`) como en el Registro de Notas (`obtRegistroNotas`).
- Si aparece solo en una fuente o en ninguna, se devuelve `FALSO ÉXITO SIEWEB` y no se escriben calificaciones.
- El flujo Classroom → SIEweb sigue protegido para escribir únicamente en desempeños `nivelEva=3`; Nivel de Logro no se modifica.
- La réplica entre secciones resuelve la capacidad padre en cada sección y aplica el cambio sobre el modelo completo de esa sección; no copia IDs de 2.º A a 2.º B.

## Pruebas

La suite incluye pruebas de extracción del modelo completo, alta, edición, conservación de campos internos, uso de `datosReplica`, rechazo de `e0006`, rechazo de `estado: 1` falso y protección de Nivel de Logro.
