# SieRoom v0.7.4 — Inicio y finalización manual de asesoría

## Cambio principal

La asesoría ya no depende de una hora de cierre.

1. El docente selecciona 2A, 2B, 5A o 5B y pulsa **▶ Iniciar asesoría**.
2. SieRoom genera el QR y abre el registro de asistencia.
3. Los estudiantes convocados escanean y se registran.
4. El docente confirma visualmente cada registro. Al confirmar, se envía el aviso de asistencia por SIEweb.
5. Cuando el docente decida terminar, pulsa **■ Finalizar asesoría**.
6. El QR queda cerrado inmediatamente.
7. SieRoom identifica a todos los convocados que no tienen asistencia confirmada, registra **FALTÓ** y envía el aviso de inasistencia por SIEweb.
8. Google Sheets actualiza las pestañas **Asistencias**, **Sesiones** y **Resumen**.

## Protección antes de finalizar

Si existe algún registro en estado **PENDIENTE**, SieRoom no permite finalizar hasta que el docente lo confirme o lo rechace. Esto evita marcar como ausente a un estudiante que sí está en el aula pero aún no fue validado.

## Recuperación de sesión

Si el panel se recarga y el docente vuelve a pulsar **Iniciar asesoría** para la misma sección, SieRoom recupera la sesión que ya está en curso en vez de crear una segunda.

## Google Sheets

La pestaña **Sesiones** usa ahora estas columnas:

- ID sesión
- Fecha
- Sección
- Iniciada
- Tipo de cierre
- Finalizada
- Convocados
- Asistieron
- Faltaron
- Pendientes
- Estado

Las hojas creadas por v0.7.3 conservan sus datos y sus encabezados se normalizan al nuevo esquema cuando SieRoom vuelve a acceder a ellas.

## Variables de entorno

No se necesita una variable nueva. Continúa usando:

- `ATTENDANCE_ADMIN_SECRET`
- `ATTENDANCE_REQUIRE_TEACHER_CONFIRM` (opcional; por defecto activado)
- `ATTENDANCE_SHEET_NAME` (opcional)
