# Auditoría de cobertura Classroom — v0.6.0

## Qué añade esta versión

- Alias explícito para **crear anuncios** en el tablón (`classroom_create_announcement`).
- Revisión de archivos entregados por estudiantes desde `StudentSubmission.assignmentSubmission.attachments`.
- Descarga/exportación de archivos de Drive accesibles por el profesor.
- Extracción de texto de **PDF, DOCX, XLSX, PPTX y archivos de texto**.
- Revisión visual de **fotos/imágenes** y de páginas de PDF mediante `classroom_attachment_image`.
- Comentarios, listado de comentarios y respuestas sobre el **archivo de Google Drive entregado**.
- Alias explícito `sieweb_new_message` para crear y enviar mensajes NUEVOS en SieWeb, con resolución opcional del destinatario por nombre.

## Comentarios de Classroom: límite oficial

La API oficial de Google Classroom **no expone los comentarios privados de StudentSubmission ni los comentarios nativos del tablón/anuncios**. Por eso esta versión no inventa un endpoint inexistente.

Para retroalimentación se ofrecen dos canales reales:

1. **Comentario en el archivo de Drive entregado** (cuando el adjunto es un archivo de Drive y la cuenta tiene permiso para comentar).
2. **Mensaje nuevo de SieWeb** al alumno/familia, después de revisar el archivo.

Los comentarios de Drive NO son lo mismo que un comentario privado de Classroom. En Google Workspace Docs aparecen en la vista de comentarios del archivo. En PDFs, los comentarios no anclados pueden no mostrarse en el visor aunque Drive los conserve.

## Recursos oficiales cubiertos directamente

- courses + aliases + gradingPeriodSettings
- announcements
- courseWork
- courseWork.rubrics
- courseWork.studentSubmissions
- courseWorkMaterials
- studentGroups + studentGroupMembers
- students
- teachers
- topics
- invitations
- userProfiles
- userProfiles.guardianInvitations
- userProfiles.guardians
- Google Drive files/export + comments/replies para archivos entregados

## Scope nuevo

Para revisar de forma general archivos entregados y crear/responder comentarios en esos archivos, el refresh token debe incluir:

`https://www.googleapis.com/auth/drive`

Este scope es más amplio que los scopes de Classroom. El conector lo usa únicamente para archivos que el profesor ya puede acceder mediante su cuenta Google.

## Límites no solucionables solo con API oficial

- Leer/escribir comentarios privados nativos de una entrega de Classroom.
- Leer/escribir comentarios nativos del tablón/anuncios de Classroom.
- Escribir puntajes por criterio de rúbrica.
- Editar la nota global calculada del curso como un campo general.
- Saltar la restricción `associatedWithDeveloper` de Google para determinadas escrituras.

## Sobre “responder cuando un estudiante comente”

- Si el comentario está en el **archivo de Drive entregado**, el conector puede listar comentarios y responderlos.
- Si el comentario es un **comentario nativo de Classroom**, la API oficial no entrega el contenido ni permite responderlo. La API de informes de administrador puede registrar que ocurrió un evento de comentario, pero no sustituye un endpoint de lectura/respuesta del comentario.
