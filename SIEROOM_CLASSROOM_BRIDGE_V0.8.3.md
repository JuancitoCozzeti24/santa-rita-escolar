# SieRoom Classroom Bridge 0.8.3

## Problema corregido

Durante una lectura real de 2.º B, Chrome conservó momentáneamente la entrega de 2.º A. La pestaña antigua ya estaba marcada como `complete`, de modo que el Bridge v0.8.2 podía leer una estructura válida pero perteneciente a otra aula.

## Contrato de destino v3

- El Bridge anuncia `verified_private_comment_read_v3` y `target_submission_guard`.
- La pestaña solo queda lista cuando `status=complete` y la ruta de Classroom coincide con la entrega solicitada.
- Se tolera el prefijo de cuenta `/u/N` y se ignora `authuser`, pero se exige la misma ruta de curso, tarea y alumno.
- El destino se comprueba después de la navegación, justo antes de la operación y otra vez contra la URL que devuelve el content script.
- Render vuelve a comparar esa URL con `submission_url`; una diferencia produce `bridge_target_mismatch` y nunca un falso `completed`.
- Las lecturas válidas usan `dom-v0.8.3-read`.

## Seguridad preservada

Siguen activos el correo docente obligatorio, el rechazo de textos de interfaz y la validación estructural de comentarios. Una lectura fallida no se convierte en nota de SIEWeb y Nivel de Logro permanece protegido.
