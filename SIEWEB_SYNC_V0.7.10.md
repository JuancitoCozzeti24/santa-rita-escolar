# SieRoom SRC 0.7.10 — escritura jerárquica real de criterios SIEweb

## Error aislado

El preflight de v0.7.9 ya resolvía correctamente la sección, pero el constructor de criterios trataba la colección editable como una lista plana. La respuesta real de SIEweb muestra que `json.resCriterios` es un árbol: cada competencia contiene capacidades en `children` y cada capacidad contiene desempeños en otro `children`.

Los campos observados que gobiernan esa jerarquía son:

- `ID_CONTENIDO`: identidad del nodo dentro del árbol;
- `ID_CONTENIDO_REF`: identidad `ID_CONTENIDO` del padre;
- `NIVEL`: 1 competencia, 2 capacidad, 3 desempeño;
- `LLAVE`: ruta jerárquica codificada con programa e índice;
- `flExiste`: `true` para nodos persistidos y `false` para un alta todavía no persistida;
- `EDITOREG`: 0 sin edición; 1 cuando se modifica una fila existente.

## Alta de un desempeño

Para **AREAS PERIM.** bajo **Modela**:

1. se resuelve Modela por `ID_CONTENIDO`;
2. se inspeccionan únicamente sus `children` de nivel 3;
3. se calcula el siguiente `INDICE`;
4. se crea la fila como alta (`IDs=null`, `flExiste=false`, `EDITOREG=1`);
5. se genera una `LLAVE` nueva a partir de la llave del padre;
6. se inserta dentro de `Modela.children`;
7. la cantidad de filas raíz no cambia;
8. se envía el árbol completo a `HyoClaseContenido/insertar`;
9. si el proveedor confirma, se releen editor y Registro de Notas y ambos deben contener exactamente un desempeño nuevo.

## Ediciones

Una edición ya no se confunde con un alta. Se preservan `ID_CONTENIDO`, `ID_CLASE_CONTENIDO`, `ID_CONTENIDO_REF` y `LLAVE`, y se marca `EDITOREG=1` para que SIEweb detecte que la fila existente cambió.

## Réplica y seguridad

`datosReplica` vacío se normaliza a `[]`. SieRoom no utiliza la réplica interna del proveedor para copiar IDs entre secciones: 2.º A y 2.º B se procesan independientemente con sus propios `idAmbito`, `idClase`, `idClasePeriodo`, capacidad y desempeño.

La creación fallida de un criterio detiene las notas. La escritura automática de calificaciones solo admite columnas de desempeño (`nivelEva=3`) y no escribe Nivel de Logro.
