# SieRoom SRC 0.8.4 — flujo consolidado Classroom → SIEWeb

## Fallas corregidas

1. La lectura de comentarios ya no usa un fallback global sobre `document.body`, que podía mezclar retroalimentaciones de otros alumnos.
2. La cuenta docente solo se acepta desde el control de la cuenta activa. Encontrar el correo entre cuentas secundarias no autoriza el trabajo.
3. Navegador y servidor exigen la misma versión 0.8.4, las capacidades v4 y la ruta exacta de curso, tarea y alumno.
4. Una sola pestaña del Bridge procesa la cola. **Procesar ahora** no cancela un trabajo activo y el lease cubre el tiempo máximo normal del navegador.
5. El valor de una nota de Classroom debe quedar visible después de la edición para declararse aplicado.
6. Los comentarios conservan orden DOM y marca de tiempo. Si hay varias notas y no se puede demostrar cuál es la más reciente, el traspaso se bloquea.
7. La conversión cualitativa admite únicamente A/B/C: A=15–20, B=11–14 y C=0–10. Una contradicción entre nota numérica y letra bloquea al alumno.
8. Un código institucional asociado a dos usuarios o una nota asignada sin calificación verificable en el comentario bloquea el lote completo.
9. Una única nota no se duplica en varios desempeños salvo autorización explícita.
10. El guardado de varios desempeños usa un único PUT, preflight completo y verificación posterior de cada celda.
11. Solo se aceptan columnas `nivelEva=3`. La escritura académica de bajo nivel quedó deshabilitada y **Nivel de Logro no se toca**.
12. Los parámetros auxiliares no pueden sustituir clase, período, contenido o ámbito.
13. El alta nativa de desempeños valida `defaultDataContenido`, selecciona de forma inequívoca el programa 5 y exige un `paramDatosReplica` común para todo el lote antes del único POST. Un `e0006` nunca genera reintentos de escritura ni habilita notas.

## Flujo autorizado

1. Leer cada entrega con el Bridge 0.8.4 y cuenta docente verificada.
2. Extraer la nota cuantitativa/cualitativa desde el comentario privado estructurado.
3. Resolver los desempeños de cada sección de forma independiente.
4. Confirmar que todos los destinos son nivel 3 y que no hay alumnos, notas o cronologías ambiguas.
5. Mostrar la previsualización.
6. Tras confirmación explícita, enviar un solo lote de notas y releer todas las celdas.

No se publican comentarios, no se crean desempeños y no se guardan notas durante una previsualización.
