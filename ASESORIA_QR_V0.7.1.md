# Asistencia QR a asesorías — v0.7.1

En Render agrega `ATTENDANCE_ADMIN_SECRET` con una contraseña larga y privada. Tras desplegar abre `https://TU-SERVICIO.onrender.com/asesoria?key=TU_SECRETO`.

Elige la sección, pulsa **Nueva asesoría** y proyecta el QR. El alumno escanea, selecciona su nombre y registra su asistencia. SieRoom registra la hora, resuelve su familia mediante SIEweb y envía el aviso automáticamente. El panel se actualiza cada 3 segundos.

**Primera prueba:** usa un estudiante/familia autorizada porque el correo se envía inmediatamente.

Limitación del MVP: las sesiones están en memoria y se pierden si Render reinicia. La siguiente versión debería persistirlas en una base de datos y autenticar al alumno con su cuenta institucional.
