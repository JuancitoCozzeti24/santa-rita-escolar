# SieRoom SRC 0.7.14 — contrato nativo del modal de criterios

## Causa raíz

El cliente de SIEWeb no guarda una fila nueva reenviando `resCriterios`. Al abrir el modal crea `defaultDataContenido`, completa el programa hijo, calcula `INDICE` y `LLAVE`, y llama:

```json
{
  "registros": ["defaultDataContenido completado"],
  "idClase": 2030,
  "datosReplica": "paramDatosReplica"
}
```

Las versiones anteriores enviaban el árbol completo, la rama o una plaza `flExiste=false`, junto con campos superiores adicionales y `datosReplica=[]`. El proveedor podía responder `e0006` o incluso `estado=1` sin persistir.

## Contrato implementado

Cada desempeño nuevo se construye con los campos exactos del modal: identidades nuevas en `0`, clase/período, flags, peso, descripción/abreviatura, programa `5`, capacidad en `ID_CONTENIDO_REF`, orden, base, primer índice libre, `NIVEL_PADRE`, LLAVE y `COLORP`/`DESCP`/`ICONOP` obtenidos de `dataPrograma.objProgramas`.

`datosReplica` se deriva de fuentes autenticadas:

- `periodo`, `idCurso` y `cursocod` del Registro de Notas;
- `grupocod` de la capacidad real;
- `limiteReplica` de `nivelReplicaAnual`;
- `replicar=false` para impedir réplicas implícitas.

No se aceptan listas de destinos ni overrides que cambien la identidad de la clase.

## Seguridad

- Solo admite `nivelEva=3` con una capacidad padre de nivel 2.
- Comprueba clase, período, contenido, ámbito y código de curso antes del POST.
- La operación es idempotente si el desempeño ya existe y está visible en ambas lecturas.
- Hace como máximo un POST; un error nunca habilita otra forma de payload.
- Requiere persistencia exacta en editor y Registro de Notas.
- Si falla la verificación, bloquea las notas y no toca Nivel de Logro.

## Cobertura

La suite contiene 42 pruebas, incluidas regresiones del objeto modal exacto, `paramDatosReplica`, falsa confirmación `estado=1`, idempotencia, protección de contexto y bloqueo de réplicas ambiguas.
