# SieRoom SRC 0.7.15 — matrícula completa en Registro de Notas

## Causa raíz

La lectura general incluía:

```text
objInfoRegIndividual[alucod]=False
```

SIEWeb lo trataba como un filtro individual. La respuesta mantenía `infoClasePeriodo` y `cabeceraNotas`, pero omitía `dataAlumno`; por eso el resumen mostraba 51 criterios y 0 alumnos.

La interfaz oficial llama `obtRegistroNotas` con `objInfoRegIndividual.tipoRegistro` y solo incorpora `alucod` cuando existe un alumno seleccionado.

## Corrección

La lectura general ahora envía:

```text
objInfoRegIndividual[tipoRegistro]=registroNotas
```

y no envía `objInfoRegIndividual[alucod]`. Las lecturas individuales pueden proporcionar un código real mediante `extra_params`.

## Verificación real

En Matemática de 2.º A, período 2:

- antes: 51 criterios, 0 alumnos;
- después: 51 criterios, 28 alumnos;
- `AREAS PERIM.` permanece visible con `ID_CONTENIDO=135924`, padre `133735` y nivel 3.

La corrección es de solo lectura y no introduce notas. El guardado de notas continúa requiriendo previsualización, autorización, cruce exacto de matrícula y verificación posterior.
