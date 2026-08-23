# SieRoom SRC 0.7.7 — alta persistente de desempeños SIEweb

Corrige el caso observado en v0.7.6 donde `HyoClaseContenido/insertar` respondía `estado: 1`, pero el desempeño nuevo no aparecía al releer SIEweb.

## Cambio principal
- Para crear un desempeño ya no se manda como plantilla un registro procedente de otra sección.
- Se consulta `dataInicialPesosCriterios` de la sección destino y se clona el esquema de un desempeño hermano REAL de la misma capacidad.
- Solo se limpian/reinician identidades persistidas y se cambian padre, nivel y descripción.
- La confirmación inmediata se hace contra `dataInicialPesosCriterios`, que es la fuente del editor de criterios/desempeños.
- También se consulta `obtRegistroNotas`; si su cabecera todavía no se regeneró, no se confunde ese retraso con un fallo de creación.
- Sigue prohibido escribir en Nivel de Logro: el flujo Classroom→SIEweb solo acepta `nivelEva=3`.
- La réplica 2.º A / 2.º B resuelve y clona estructuras de cada sección independientemente.

## C3
La versión no obliga a crear cuatro capacidades. El llamador puede trabajar únicamente con los desempeños que realmente evalúa la evidencia (por ejemplo Modela, Usa estrategias y Argumenta) y omitir Comunica.
