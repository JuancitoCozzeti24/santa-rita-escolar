# SieRoom v0.7.2 — Asistencia QR reforzada

## Cambios principales

- La lista pública de cada sección queda limitada a estudiantes convocados a nivelación de Matemática del II trimestre 2026.
- Un alumno solo puede tener un registro activo por sesión.
- Un dispositivo solo puede registrar un alumno por sesión mediante tres señales combinadas: cookie de primera parte, identificador persistente del navegador y huella técnica del navegador.
- Se registra la IP como dato de auditoría, pero NO se bloquea una asistencia por IP porque varios alumnos pueden compartir la misma IP pública al usar el Wi‑Fi del colegio.
- Una web no puede leer el IMEI del teléfono. No se usa IMEI.
- `ATTENDANCE_REQUIRE_TEACHER_CONFIRM=true` (valor recomendado y predeterminado) deja cada registro como PENDIENTE. El docente debe confirmar visualmente al alumno desde el panel; recién entonces se envía el correo SIEweb a la familia.
- Si el docente rechaza un registro equivocado, el alumno y el dispositivo quedan liberados para volver a registrarse correctamente.

## Fuente de la lista

`SECUNDARIA 2026/NIVELACIÓN/MATEMÁTICA/II Trimestre/LISTA DE ALUMNOS QUE REQUIEREN NIVELACIÓN DE MATEMÁTICAdocx.docx`

La configuración editable está en `attendance_roster.json`.

## Variables de Render

Ya existente:

- `ATTENDANCE_ADMIN_SECRET`: clave privada del panel.

Opcional:

- `ATTENDANCE_REQUIRE_TEACHER_CONFIRM=true` (recomendado). Si se establece en `false`, la asistencia confirmará y notificará automáticamente al registrar, manteniendo los bloqueos por alumno y dispositivo.

## Flujo recomendado

1. Docente crea la sesión en `/asesoria?key=...`.
2. Proyecta el QR.
3. Alumno escanea y solo ve la lista autorizada de su sección.
4. Alumno registra su nombre.
5. El dispositivo queda bloqueado para registrar otro alumno.
6. El mismo alumno queda bloqueado para volver a registrarse desde otro dispositivo mientras esté pendiente o confirmado.
7. En el panel el docente verifica que el alumno está físicamente presente y pulsa **Confirmar**.
8. Solo en ese momento SieRoom envía el mensaje SIEweb a la familia.

## Limitación importante

Ningún QR web, IP o huella de navegador puede demostrar por sí solo presencia física de manera infalible. La confirmación visual del docente es la barrera que evita que un alumno presente registre a un compañero ausente usando otro teléfono. Una futura versión puede sustituir esta confirmación por autenticación individual con cuentas institucionales de Google si se dispone de los correos de cada estudiante y se configura OAuth para el dominio escolar.
