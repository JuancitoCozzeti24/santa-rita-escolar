# Santa Rita Escolar v0.6.0

Servidor MCP remoto para **Google Classroom + SieWeb**. Esta versión extiende la v0.5.0 para revisar archivos entregados por estudiantes, dar retroalimentación sobre esos archivos, publicar anuncios y hacer más visible el envío de mensajes nuevos por SieWeb.

## Novedades v0.6.0

### Revisar archivos entregados por estudiantes

La herramienta `classroom_submission_files` permite:

- `list`: listar adjuntos de una entrega y metadatos de Drive;
- `inspect_text`: extraer texto de PDF, DOCX, XLSX, PPTX y archivos de texto;
- `comment`: crear un comentario en el archivo de Google Drive entregado;
- `list_comments`: listar comentarios del archivo;
- `reply_comment`: responder un comentario del archivo;
- `resolve_comment`: responder y resolver un comentario del archivo.

La herramienta `classroom_attachment_image` devuelve a ChatGPT una **imagen real** para revisión visual:

- fotos JPG/PNG/etc.;
- una página concreta de un PDF.

Esto permite flujos como:

1. listar entregas;
2. seleccionar la entrega de un alumno;
3. leer su DOCX/PDF o mirar su foto/PDF escaneado;
4. redactar retroalimentación;
5. colocar esa retroalimentación como comentario del archivo de Drive o enviarla por SieWeb;
6. opcionalmente poner/cambiar la nota y devolver la entrega.

### Anuncios en el tablón

Además de `classroom_announcements`, existe el alias explícito `classroom_create_announcement` para publicar/programar anuncios y adjuntar archivos de Drive o enlaces al crearlos.

### Mensajes NUEVOS en SieWeb

Además de `sieweb_send_message`, existe `sieweb_new_message`. Puede:

- recibir `recipient_codes` (USUCOD) directamente;
- o buscar un destinatario por `recipient_query`, tipo y salón;
- mostrar vista previa;
- enviar el mensaje nuevo tras confirmación.

No necesita que exista un mensaje previo ni un hilo de respuesta.

## Comentarios: diferencia importante

Google **no expone mediante la API oficial de Classroom**:

- comentarios privados nativos de una entrega (`StudentSubmission`);
- comentarios nativos en el tablón/anuncios.

Por eso v0.6.0 no simula esos comentarios con otro recurso. Para retroalimentación real ofrece:

- comentarios en el **archivo de Drive** entregado;
- mensajes privados por **SieWeb**;
- calificación/devolución mediante Classroom.

Si un estudiante comenta dentro del archivo de Drive entregado, el conector sí puede listar ese comentario y responderlo. Si comenta usando el cuadro de comentarios nativo de Classroom, Google no ofrece un endpoint oficial para leer su texto o responderlo.

## Scope Google adicional

La revisión general de archivos entregados y los comentarios en Drive requieren que el refresh token incluya:

`https://www.googleapis.com/auth/drive`

La herramienta `classroom_google_auth_status` indicará si falta. Si tu refresh token actual fue creado antes de v0.6.0, probablemente debas regenerarlo una vez con este scope incluido.

## Formatos de archivo revisables

- PDF: extracción de texto; si es escaneado, revisión visual página por página.
- Imágenes: revisión visual.
- DOCX: texto y tablas.
- XLSX: hojas y valores.
- PPTX: texto de las diapositivas.
- TXT/CSV/JSON/XML/HTML y otros textos UTF-8.

Para archivos binarios no soportados, se devuelve el enlace/metadatos sin inventar contenido.

## Classroom — otras capacidades conservadas

- cursos, alumnos, docentes e invitaciones;
- temas;
- tareas/preguntas/materiales/anuncios;
- adjuntos Drive/link al crear publicaciones;
- entregas;
- notas provisionales/finales;
- cambio o intento seguro de quitar notas;
- devolución individual/lote;
- rúbricas (con límites oficiales);
- grupos de estudiantes;
- tutores y capacidades elegibles;
- diagnóstico `associatedWithDeveloper`.

## Pruebas recomendadas después del deploy

1. `Ejecuta classroom_capabilities y dime la versión.` → debe ser `0.6.0`.
2. `Verifica mis scopes de Google. No modifiques nada.`
3. `Crea una vista previa de un anuncio para 2.º A; no publiques todavía.`
4. `Lista los archivos adjuntos de la entrega de [alumno] en [tarea].`
5. Para DOCX/PDF con texto: `Revisa el adjunto 0 y extrae su contenido.`
6. Para foto/PDF escaneado: `Abre visualmente el adjunto 0, página 1.`
7. Después de revisar: `Prepara un comentario para el archivo, pero no lo publiques todavía.`
8. `Busca al alumno en SieWeb y prepara un mensaje nuevo con la retroalimentación; no lo envíes todavía.`

## Referencias oficiales auditadas

- Classroom REST: https://developers.google.com/workspace/classroom/reference/rest
- Flujo de tareas y límite de comentarios: https://developers.google.com/workspace/classroom/tutorials/assignment-workflows
- StudentSubmission attachments: https://developers.google.com/workspace/classroom/reference/rest/v1/courses.courseWork.studentSubmissions
- Announcements: https://developers.google.com/workspace/classroom/reference/rest/v1/courses.announcements
- Drive downloads/exports: https://developers.google.com/workspace/drive/api/guides/manage-downloads
- Drive comments/replies: https://developers.google.com/workspace/drive/api/guides/manage-comments
