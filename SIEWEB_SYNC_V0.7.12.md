# SieRoom SRC 0.7.12 — SIEweb: CURSOCOD + lector de alumnos

## Fallos corregidos

### 1. `dataInicialPesosCriterios` devolvía HTTP 500

El preflight de v0.7.11 podía llegar con `idClase`, `idClasePeriodo`, `idContenido` e `idAmbito` correctos, pero sin `CURSOCOD`. La interfaz real de SIEweb necesita ese contexto de curso.

v0.7.12:

1. conserva un `CURSOCOD` explícito si se proporcionó;
2. si falta, consulta `HyoClase/obtListar` para el `idAmbito` exacto;
3. selecciona la fila cuyo `ID_CLASE` coincide con el destino;
4. toma su `CURSOCOD` y lo envía en `dataInicialPesosCriterios`;
5. cachea `(idAmbito, idClase) -> CURSOCOD` durante la sesión.

No se inventa el código de curso ni se mezcla otra sección.

### 2. Registro real con alumnos, pero `students: []`

v0.7.11 resumía el gradebook suponiendo una única envoltura `json`. v0.7.12 incorpora un lector recursivo que localiza el contenedor real del Registro de Notas y busca de forma segura:

- `infoClasePeriodo`;
- `cabeceraNotas`;
- `dataAlumno` y variantes compatibles;
- `datos` del alumno;
- `notas`/celdas reales.

El resumen incorpora `reader_diagnostics` con fuente y conteos para que un futuro cambio del proveedor sea visible en vez de convertirse silenciosamente en `students: []`.

### 3. Classroom puede usar `A+ALUCOD`

El directorio de SIEweb suele identificar estudiantes como `A20180042`, mientras el Registro de Notas usa `20180042`. v0.7.12 considera ambas formas equivalentes únicamente cuando la parte restante es numérica. No hace matching difuso por nombres.

Al escribir, el payload siempre recupera y usa el `alucod` real de la fila de SIEweb.

## Protecciones que se mantienen

- no se escribe Nivel de Logro;
- el destino debe ser un desempeño (`nivelEva=3`);
- no se escriben notas si no existe la celda real del estudiante/desempeño;
- `estado=1` no basta: se vuelve a leer para verificar persistencia;
- `e0006` sigue siendo fallo explícito y bloquea notas;
- cada sección resuelve sus propios IDs e `idAmbito`.
