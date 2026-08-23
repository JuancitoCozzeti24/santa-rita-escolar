# SieRoom SRC 0.7.13 — reparación del `e0006`

## Evidencia del fallo real

Con la versión desplegada `0.7.12`, la lectura de `dataInicialPesosCriterios` para Matemática de 2.º A devolvió HTTP 500. El proveedor informó un binding indefinido para `CG.CURSOCOD` aunque la solicitud incluía `CURSOCOD=05`.

La diferencia relevante es el nombre del parámetro: el controlador real consume `cursocod` en minúsculas. Las pruebas anteriores solo comprobaban el alias mayúsculo y por eso no reproducían el contrato del proveedor.

## Contrato corregido

La lectura envía los dos alias compatibles:

```text
CURSOCOD=05
cursocod=05
```

El guardado en `HyoClaseContenido/insertar` incluye:

```text
registros
idClase
idClasePeriodo
idContenido
idAmbito
CURSOCOD
cursocod
datosReplica
```

`datosReplica` siempre es una lista. Para una escritura independiente es `[]`; solo contiene elementos cuando el editor entrega destinos reales de réplica.

## Protecciones

- Se exige coincidencia exacta de clase, período, contenido y ámbito entre la lectura y el POST.
- Solo se admite un desempeño `nivelEva=3` bajo una capacidad real.
- Un rechazo `e0006` permite avanzar a la siguiente forma del payload únicamente después de releer y confirmar que no hubo persistencia.
- Un `estado=1` tampoco basta: el desempeño debe aparecer una sola vez tanto en el editor como en el Registro de Notas.
- Las notas no se escriben si el desempeño no está confirmado.
- Nivel de Logro permanece bloqueado.

## Estrategias de compatibilidad

1. árbol completo de la UI;
2. raíz que contiene el cambio;
3. fila nueva o modificada.

Las tres usan el mismo contexto completo y el mismo contrato de réplica.
