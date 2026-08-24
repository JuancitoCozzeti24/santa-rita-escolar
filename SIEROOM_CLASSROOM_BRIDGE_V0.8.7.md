# SieRoom Classroom Bridge 0.8.7

## Falla real corregida

La v0.8.6 leyó correctamente el panel privado vacío. Sin embargo, al encolar inmediatamente la escritura del mismo alumno, `ensureClassroomTab` volvía a asignar la misma URL a la pestaña. Classroom desmontó de forma intermitente el panel lateral y dejó visible únicamente el control global **Ayuda y comentarios**.

## Corrección

- Si la pestaña ya está completa y coincide exactamente con curso, tarea y alumno, el Bridge la activa y la reutiliza sin recargar.
- Si cambia la entrega, conserva la navegación y la verificación estricta de la nueva ruta.
- Después de reutilizar la vista se vuelven a comprobar la cuenta docente y el destino.
- Continúa existiendo un solo reintento por ausencia del editor antes de escribir.
- Nunca se reintenta automáticamente un resultado ambiguo después de pulsar Publicar.
- Nota y devolución solo se ejecutan tras confirmar el comentario privado.

## Evidencia de seguridad

La prueba real fallida de 5.º A se detuvo antes de escribir. La entrega de control permaneció `TURNED_IN`, sin calificación y sin devolución.

