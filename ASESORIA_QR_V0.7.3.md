# SieRoom v0.7.3 — Asesoría QR + faltas automáticas + historial Google Sheets

## Qué agrega

1. **Registro de asistencia por QR** con lista limitada a estudiantes de nivelación del II trimestre.
2. **Confirmación visual del docente** antes de consolidar la asistencia y enviar el aviso de asistencia a la familia.
3. **Cierre automático de la sesión** a la hora elegida (por defecto, **4:30 p. m.**, zona horaria `America/Lima`).
4. Al cierre, todo estudiante convocado que **no tenga asistencia confirmada** recibe estado **FALTÓ** y SieRoom envía a su familia un correo de inasistencia por SIEweb.
5. Si un alumno está todavía **PENDIENTE** a la hora de cierre, SieRoom **no envía una falta todavía** para evitar un falso aviso. El docente debe confirmar o rechazar ese registro. Al rechazarlo después del cierre, se envía la inasistencia; al confirmarlo, se conserva como asistencia.
6. Se crea o reutiliza automáticamente un Google Sheets llamado **`SieRoom - Asistencias de asesoría 2026`** en el Drive asociado al OAuth de Google del profesor.

## Estructura del Google Sheets

### Hoja `Asistencias`
Una fila final por alumno y sesión:

- ID sesión
- Fecha
- Sección
- Estudiante
- Código SIEweb
- Hora de ingreso
- Estado (`ASISTIÓ` / `FALTÓ`)
- Aviso a familia
- Hora del aviso
- Observación

### Hoja `Sesiones`
Una fila por asesoría:

- ID sesión
- Fecha
- Sección
- Creada
- Cierre programado
- Cerrada
- Convocados
- Asistieron
- Faltaron
- Pendientes
- Estado

### Hoja `Resumen`
Se reconstruye automáticamente al cerrar una sesión y muestra por estudiante:

- Sección
- Estudiante
- Cantidad de asistencias
- Cantidad de faltas
- Total de sesiones contabilizadas
- Porcentaje de asistencia

Esto permite entregar posteriormente un informe de frecuencia, faltas y asistencia acumulada sin revisar sesión por sesión.

## Correos automáticos

### Asistencia
Se envía cuando el docente confirma visualmente al estudiante.

### Inasistencia
Se envía al cierre de la asesoría a los estudiantes sin asistencia confirmada. El asunto es:

`Inasistencia registrada – Taller de asesoría`

La comunicación indica que el estudiante no asistió y que la inasistencia quedó registrada como falta.

## Variables de Render

Ya necesarias:

- `ATTENDANCE_ADMIN_SECRET`
- `ATTENDANCE_REQUIRE_TEACHER_CONFIRM=true` (recomendado)

Opcional:

- `ATTENDANCE_SHEET_NAME=SieRoom - Asistencias de asesoría 2026`

No hace falta definir `ATTENDANCE_SHEET_NAME` si se desea usar el nombre predeterminado.

## Google

SieRoom reutiliza `GOOGLE_CLIENT_ID`, `GOOGLE_CLIENT_SECRET` y `GOOGLE_REFRESH_TOKEN` ya configurados. El token actual incluye acceso a Drive en la instalación de SieRoom; además, el proyecto de Google Cloud debe tener habilitada la **Google Sheets API** para poder escribir el historial.

Si Sheets no estuviera disponible, la asistencia y los correos SIEweb siguen funcionando y el panel mostrará el error de Google Sheets para poder corregirlo.

## Seguridad y cierre

- Un alumno no puede registrarse dos veces en la misma sesión.
- Un mismo dispositivo no puede registrar a dos estudiantes activos en la misma sesión.
- El IMEI no es accesible desde una web normal y no se utiliza.
- La IP se conserva para auditoría, pero no se usa como bloqueo único porque varios estudiantes pueden compartir la misma IP pública.
- Después de la hora de cierre no se aceptan nuevos check-ins.

## Fiabilidad del cierre

Al crear la asesoría, el servidor programa el cierre para la hora seleccionada. Además, cada consulta del panel verifica si la hora de cierre ya pasó y ejecuta el cierre pendiente como mecanismo de respaldo. Mantener abierto el panel docente durante la asesoría proporciona una comprobación continua del estado de la sesión.
