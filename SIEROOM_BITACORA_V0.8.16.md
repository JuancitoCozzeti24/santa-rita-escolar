# SieRoom 0.8.16 — Bitácora Docente

Esta versión convierte la integración de **BITÁCORA DOCENTE – MATEMÁTICA 2026** en una capacidad explícita y comprobable del complemento.

## Comportamiento

- La palabra **BITÁCORA** dirige la consulta al módulo de bitácora de SieRoom.
- El estudiante se resuelve siempre contra la pestaña `ALUMNOS`.
- `student_history` recupera únicamente los registros cuyo `Alumno_ID` coincide con el estudiante resuelto.
- `student_report` devuelve los registros de `BITÁCORA` y `ACADÉMICO`, recuentos y reglas de redacción basadas en evidencia.
- Los rangos `fecha_desde` y `fecha_hasta` son inclusivos y aceptan `DD/MM/YYYY` o `YYYY-MM-DD`.
- Los registros generales de sección con `Alumno_ID` vacío no se atribuyen a un estudiante.
- Las escrituras continúan siendo append-only y se verifican releyendo el `Registro_ID` guardado.

## Compatibilidad

La herramienta nativa es `bitacora_docente`. Como respaldo, `sieweb_academics` expone:

- `bitacora_policy`
- `bitacora_status`
- `bitacora_resolve_student`
- `bitacora_student_history`
- `bitacora_student_report`
- `bitacora_append_observation`
- `bitacora_append_academic`

El registro se realiza explícitamente al iniciar el servidor y también conserva el bootstrap de compatibilidad. La instalación es idempotente para impedir herramientas duplicadas.

## Alcance

No se modificó el Bridge de Classroom ni sus flujos de comentarios privados, calificaciones o devoluciones.
