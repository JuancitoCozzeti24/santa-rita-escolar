# Santa Rita Escolar v0.5.0

Servidor MCP remoto para **Google Classroom + SieWeb**. Esta versión amplía Classroom hacia un control docente integral dentro de lo que expone la API oficial y mantiene las funciones SieWeb de v0.3.2.

## Diseño de herramientas

La v0.5.0 agrupa acciones por recurso (`classroom_courses`, `classroom_coursework`, `classroom_grades`, etc.) para no inundar a ChatGPT con decenas de herramientas casi idénticas. Se conservan aliases de alta frecuencia como `classroom_create_assignment`, `classroom_create_material`, `classroom_list_submissions` y `classroom_grade_submission`.

Todas las escrituras piden confirmación antes de ejecutarse. Las eliminaciones y el borrado de nota se marcan como destructivos.

## Classroom — cobertura v0.5.0

### Cursos y configuración
- Listar, leer, crear, actualizar y eliminar cursos.
- Aliases de curso.
- Leer `gradebookSettings`.
- Leer y actualizar períodos de calificación cuando la cuenta/licencia sea elegible.

### Personas
- Listar/leer/agregar/quitar alumnos.
- Listar/leer/agregar/quitar docentes.
- Crear/listar/aceptar/cancelar invitaciones al curso.
- Leer perfiles y comprobar capacidades elegibles del usuario.
- Listar/leer/eliminar tutores (guardians).
- Crear/listar/leer/cancelar invitaciones de tutor.

### Stream / Trabajo de clase
- Temas: listar, crear, renombrar y borrar.
- Anuncios: listar, leer, crear/publicar/programar, editar, cambiar destinatarios y borrar.
- Tareas y preguntas: listar, leer, crear/publicar/programar, editar, cambiar destinatarios y borrar.
- Tipos soportados: `ASSIGNMENT`, `SHORT_ANSWER_QUESTION`, `MULTIPLE_CHOICE_QUESTION`.
- Material de clase (`CourseWorkMaterial`): listar, leer, crear/publicar/programar, editar y borrar.
- Adjuntos normales al crear: archivos de Google Drive y enlaces web, máximo 20 por publicación según Classroom.
- En tareas, Drive acepta `VIEW`, `EDIT` y `STUDENT_COPY`; en anuncios/material de clase se usa `VIEW`.

### Entregas y CALIFICACIONES
- Listar y leer `StudentSubmission`.
- Estado, retraso, fecha de actualización, historial y archivos/submisión cuando Google los devuelve.
- Leer `draftGrade` (nota provisional, solo docente).
- Leer `assignedGrade` (nota asignada/visible al alumno).
- Poner/cambiar **nota provisional** sin publicarla al alumno.
- Poner/cambiar **nota final** (`draftGrade` + `assignedGrade`).
- **Calificar y devolver** en una sola orden.
- **Devolver sin cambiar la nota** existente; opcionalmente finaliza primero la nota provisional para imitar el flujo de la UI.
- Calificación por lote y devolución por lote.
- Intento seguro de **quitar nota** usando FieldMask; si Google rechaza el vaciado, se devuelve un error explícito y no se sustituye por otra acción destructiva.
- Detectar alumnos pendientes y generar progreso por estudiante.
- Diagnóstico `associatedWithDeveloper` antes de intentar editar/calificar/devolver una tarea.

### Rúbricas
- Listar, leer, crear, editar y borrar rúbricas cuando Google/licencia/proyecto lo permitan.
- Leer `draftRubricGrades` / `assignedRubricGrades` desde entregas.
- La API oficial **no permite escribir los puntajes por criterio** de una rúbrica.

### Grupos de estudiantes
- Listar, crear, renombrar y borrar grupos.
- Listar, agregar y quitar miembros.
- Algunas cuentas pueden requerir elegibilidad/licencia o Preview Version.

## Adjuntos: formato JSON

```json
[
  {"type":"drive","url":"https://drive.google.com/file/d/ID/view","share_mode":"VIEW"},
  {"type":"link","url":"https://example.com/recurso"}
]
```

Si el usuario nombra un archivo de Drive sin ID/URL, ChatGPT debe resolverlo primero con su conector Google Drive y pasar luego el ID/URL a Santa Rita Escolar.

## Scopes Google recomendados

La acción `classroom_google_auth_status` comprueba estos permisos sin revelar tokens:

- `https://www.googleapis.com/auth/classroom.courses`
- `https://www.googleapis.com/auth/classroom.rosters`
- `https://www.googleapis.com/auth/classroom.profile.emails`
- `https://www.googleapis.com/auth/classroom.profile.photos`
- `https://www.googleapis.com/auth/classroom.topics`
- `https://www.googleapis.com/auth/classroom.announcements`
- `https://www.googleapis.com/auth/classroom.coursework.students`
- `https://www.googleapis.com/auth/classroom.courseworkmaterials`
- `https://www.googleapis.com/auth/classroom.guardianlinks.students`

Si el refresh token actual no contiene alguno, el diagnóstico lo mostrará y habrá que emitir un refresh token nuevo con el conjunto ampliado de scopes.

## Límites reales de la API oficial

1. **Comentarios privados de entregas:** Classroom no expone actualmente esos comentarios mediante la API oficial. No se simulan con anuncios ni mensajes.
2. **Tareas creadas fuera de este proyecto OAuth:** Google puede impedir editar/eliminar el CourseWork o modificar/devolver sus StudentSubmissions. Usa `classroom_coursework(action="diagnose", ...)` antes de escribir.
3. **Rúbricas:** los puntajes por criterio de una entrega son de solo lectura mediante API.
4. **Nota global calculada del curso:** no se expone como un campo general editable; el conector puede calcular métricas a partir de las notas disponibles, pero no fingirá modificar una nota global inexistente en la API.
5. **Adjuntos normales después de crear una tarea:** la lista `materials` no es un campo patchable del `CourseWork` estable. Los AddOnAttachments son otra arquitectura de Classroom Add-ons y requieren configuración/scopes específicos.
6. **Push notifications:** Classroom soporta `registrations` hacia Google Cloud Pub/Sub, pero este paquete no activa ese subsistema porque requiere un topic Pub/Sub y un consumidor adicional.
7. **Funciones con licencia/elegibilidad:** rúbricas, períodos de calificación y grupos pueden depender de licencia/capacidad del usuario. `classroom_profiles_guardians(action="check_capability", ...)` permite comprobar capacidades cuando el endpoint Preview esté disponible.

## SieWeb

Se conserva la integración ya capturada para:
- login automático remoto;
- mensajería y destinatarios;
- registro/notas;
- criterios/desempeños;
- conclusiones descriptivas;
- resolución natural de 2.º A y 5.º A 2026 y períodos;
- flujos Classroom ↔ SieWeb existentes.

## Pruebas recomendadas después del deploy

1. `Verifica mis scopes y capacidades de Classroom. No modifiques nada.`
2. `Lista mis cursos activos y dime cuántos alumnos tiene cada uno. No modifiques nada.`
3. `Diagnostica si esta tarea puede ser editada, calificada y devuelta por el complemento. No modifiques nada.`
4. En una tarea de prueba creada por Santa Rita Escolar: poner una nota provisional, comprobarla, convertirla a final y devolverla.
5. Crear un Material de clase con título, descripción y un archivo de Drive de prueba.

## Referencias oficiales auditadas para v0.5.0

- Classroom REST: https://developers.google.com/workspace/classroom/reference/rest
- Calificaciones: https://developers.google.com/workspace/classroom/guides/classroom-api/manage-grades
- StudentSubmission.patch: https://developers.google.com/workspace/classroom/reference/rest/v1/courses.courseWork.studentSubmissions/patch
- StudentSubmission.return: https://developers.google.com/workspace/classroom/reference/rest/v1/courses.courseWork.studentSubmissions/return
- Rúbricas: https://developers.google.com/workspace/classroom/rubrics/limitations
- Períodos de calificación: https://developers.google.com/workspace/classroom/grading-periods/manage-grading-periods
- Tutores: https://developers.google.com/workspace/classroom/guides/manage-guardians
- Scopes: https://developers.google.com/workspace/classroom/guides/auth
