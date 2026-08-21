# SieRoom SRC 0.7.4 — guardado verificado de notas SIEweb

La v0.7.4 corrige el guardado académico sin tocar Classroom, Bridge, mensajería ni asesorías.

- Copia la celda real `note_obj` devuelta por SIEweb.
- Conserva sus campos internos.
- Solo fija `notaNue` y la identidad necesaria.
- El preflight exige que todas las notas solicitadas tengan alumno y celda.
- Después del PUT relee el gradebook hasta 3 veces.
- Solo declara éxito si todas las notas quedan persistidas.
- Acción recomendada: `sieweb_academics`, `action="save_grades_verified"`.
- `update_grades` permanece como operación de bajo nivel por compatibilidad.
