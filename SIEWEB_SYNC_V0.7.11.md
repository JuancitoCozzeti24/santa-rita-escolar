# SieRoom SRC 0.7.11 — SIEweb: alta UI-native + escritor adaptativo e0006

## Problema aislado en 0.7.10

La 0.7.10 ya resolvía correctamente el `idAmbito`, el árbol `resCriterios`, el padre de Modela y la LLAVE jerárquica. Sin embargo, todavía construía una fila nueva **clonando un desempeño ya persistido** y anulando sus IDs.

La captura real de `dataInicialPesosCriterios` demuestra que las filas nuevas/no persistidas (`flExiste=false`) son más espartanas: no incluyen campos que el backend agrega después de persistir, como `ID_CLASE`, `ID_CURSO`, `GRUPOCOD`, `ID_CLASE_PERIODO`, `NIVEL`, `TIPO_EVA`, `FL_CONCLUSION` u `ORDEN_PROG`.

Eso dejaba al POST con una fila híbrida: IDs nulos de alta, pero campos de una fila persistida. SIEweb podía rechazarla con `estado=0 / e0006`.

## Corrección 0.7.11

1. El desempeño nuevo se construye **desde cero** con el esquema de una plaza nueva real de la UI.
2. Mantiene únicamente los campos que una fila `flExiste=false` necesita: descripción, abreviatura, programa, padre, índice, orden, LLAVE, peso/flags, marcadores de edición y `children=[]`.
3. Se omiten `ID_CLASE`, `ID_CURSO`, `GRUPOCOD`, `ID_CLASE_PERIODO`, `NIVEL`, `TIPO_EVA`, `FL_CONCLUSION` y `ORDEN_PROG` en la fila nueva. El nivel se infiere internamente por `ID_PROGRAMA=5`.
4. Si no hay réplica interna real, `datosReplica` **no se envía**. La réplica 2.º A ↔ 2.º B sigue haciéndose como escrituras independientes para no reutilizar IDs.
5. El escritor es adaptativo SOLO ante `estado=0/e0006` explícito y después de comprobar por relectura que no se persistió nada:
   - `ui-sparse-full-tree`
   - `ui-sparse-changed-root`
   - `ui-sparse-changed-records`
6. Nunca prueba una segunda forma después de un error ambiguo distinto de `e0006`.
7. Un `estado=1` sigue sin ser suficiente: el desempeño debe aparecer exactamente una vez tanto en el editor como en el Registro de Notas.
8. Si un `estado=0` llegara a persistir realmente, la relectura lo detecta y bloquea cualquier segundo POST.
9. Nivel de Logro permanece protegido; las notas solo continúan después de que el desempeño esté confirmado.

## Pruebas

- 32/32 pruebas automáticas aprobadas.
- Compilación Python correcta.
- Prueba específica del payload sparse/UI-native.
- Prueba de omisión de `datosReplica` vacío.
- Prueba de fallback controlado e0006 -> e0006 -> éxito.
- Prueba de bloqueo inmediato ante un error distinto de e0006.
- Validación adicional contra una captura real de `dataInicialPesosCriterios`: se localizó Modela, se insertó el desempeño bajo `parent.children` y el árbol resultante pasó todas las invariantes sin mezclar IDs de sección.
