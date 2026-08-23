# SieRoom SRC 0.7.9 — `idAmbito` enlazado al guardado real de criterios

## Fallo encontrado en v0.7.8

El preflight y la escritura no estaban usando necesariamente el mismo contexto.

`criteria_write_preflight` recibía `id_ambito`, pero `upsert_criteria_verified()` no tenía ese parámetro. Cuando el guardado volvía a llamar a `dataInicialPesosCriterios`, `get_criteria()` aplicaba su valor por defecto (`SIEWEB_ID_AMBITO_REGISTRO_NOTAS`, normalmente 518/2.º A).

Por tanto, un flujo destinado a 2.º B podía quedar así:

1. preflight: 2.º B + su `idAmbito` correcto;
2. guardado: `idClase`/`idClasePeriodo` de 2.º B;
3. relectura del editor: ámbito 518/2.º A;
4. POST `HyoClaseContenido/insertar`: mezcla de identidades de dos secciones;
5. respuesta de SIEweb: `estado=0 / e0006`.

Esto explica por qué el preflight podía informar una estructura coherente y el POST real fallar después.

## Corrección v0.7.9

- `upsert_criteria_verified()` exige `id_ambito` y no acepta 0/vacío.
- Todas las llamadas a `get_criteria()` del mismo guardado reciben ese `id_ambito`: lectura previa y verificaciones posteriores.
- `sieweb_academics action=criteria_write_preflight` y `action=upsert_criteria_verified` bloquean la operación si falta `id_ambito`; ya no sustituyen silenciosamente por 518.
- `workflow_school action=replicate_performances` pasa `ctx["idAmbito"]` independientemente para cada sección.
- Antes del POST se comprueba el contexto del Registro de Notas (`idClase`, `idClasePeriodo`, `idContenidoPrin`).
- Si las filas editables contienen `idClase` o `idClasePeriodo`, también se valida que pertenezcan al mismo destino.
- Si cualquier identidad no coincide, no se realiza el POST.
- Se mantienen las comprobaciones de persistencia en editor + Registro de Notas y la protección de `nivelEva=3`.

## Pruebas añadidas

La suite v0.7.9 comprueba explícitamente que:

1. el mismo `idAmbito` llega a la lectura anterior y posterior al POST;
2. una colección de filas perteneciente a otra sección se bloquea antes de escribir;
3. no existe fallback silencioso de ámbito en escrituras;
4. una discrepancia de `idClase` en el Registro de Notas bloquea el POST;
5. continúan funcionando las pruebas de v0.7.4–v0.7.8 sobre notas, falsos `estado:1`, `e0006`, respuestas de mensajería y protección de Nivel de Logro.
