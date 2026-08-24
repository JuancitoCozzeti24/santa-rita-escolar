# SieRoom SRC 0.8.5 — panel privado vacío verificado

## Falla real corregida

Classroom puede ocultar el encabezado **Comentarios privados** cuando una entrega aún no tiene comentarios, aunque mantenga visibles el editor **Añade un comentario privado…** y el botón **Publicar**. La v0.8.4 encontraba el editor, pero exigía además comentarios existentes dentro del contenedor y terminaba rechazando una entrega válida.

## Guardia nueva

Sin encabezado visible, el Bridge solo acepta la región cuando:

1. el editor se identifica explícitamente como comentario privado;
2. existe un botón Publicar/Enviar visible dentro de un ancestro cercano y acotado;
3. el botón está espacialmente asociado al editor;
4. la región no es `document.body` ni `documentElement`;
5. la ruta de curso, tarea y alumno y la cuenta docente continúan verificadas.

La ruta anterior de hilos con comentarios existentes se conserva. La deduplicación sigue comprobando el texto dentro de la misma región privada antes de publicar.

## Pruebas

La tabla de regresión valida cinco estados: panel vacío correcto, panel sin acción verificable, editor no privado, región global prohibida e hilo privado existente. Además se ejecutan las pruebas de cuenta, alumno destino, cronología, publicación, calificación, devolución, guardado SIEWEB y protección de Nivel de Logro.
