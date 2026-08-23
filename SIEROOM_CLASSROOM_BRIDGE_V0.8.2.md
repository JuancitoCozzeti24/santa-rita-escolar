# SieRoom Classroom Bridge 0.8.2

## Problema corregido

Durante la lectura real de la tarea “ÁREAS Y PERÍMETROS (PÁG. 408)”, Classroom podía presentar un editor genérico sin el encabezado privado. La v0.8.1 tomaba entonces elementos de navegación —por ejemplo “Instrucciones”, “Trabajo de los alumnos” o “Más opciones”— como si fueran comentarios.

## Contrato de lectura v2

- El Bridge anuncia `verified_private_comment_read_v2`.
- Una copia anterior no puede reclamar trabajos nuevos de lectura.
- El contenido elimina textos conocidos de navegación y deja de tratar cualquier `li` genérico como comentario.
- Una lectura se acepta si proviene del panel privado verificado o si contiene retroalimentación estructurada con al menos dos marcadores.
- Render exige `dom-v0.8.2-read`, fuente verificada, conteo coherente y objetos con `text`, `markers` y `structuredFeedback`.
- La validación del servidor vuelve a rechazar textos de interfaz aunque el navegador intentara enviarlos.

## Actualización en pestañas abiertas

El Bridge compara la versión devuelta por `SIEROOM_PING` con el manifiesto. Si la pestaña conserva un script anterior, reinyecta `content.js` v0.8.2. El nuevo guard global permite que la reinyección se ejecute después de actualizar la extensión.

## Seguridad

Se conserva el correo docente obligatorio y la verificación de cuenta antes de leer, comentar, calificar o devolver. La lectura no modifica Classroom. Ninguna lectura inválida se transforma en nota de SIEWeb y el Nivel de Logro permanece bloqueado.
