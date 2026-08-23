# SieRoom SRC 0.7.12

## SIEweb — CURSOCOD obligatorio + lector de alumnos corregido

La v0.7.12 corrige los dos fallos concretos observados después de instalar v0.7.11:

- `dataInicialPesosCriterios` ya no se llama sin contexto de curso. Si el llamador no envía `CURSOCOD`, SieRoom lo resuelve automáticamente desde `HyoClase/obtListar` usando el `idAmbito` y `idClase` exactos; para Matemática queda `CURSOCOD=05`. El valor se cachea por clase/ámbito para no repetir lecturas innecesarias.
- el lector del Registro de Notas ya no asume una única capa `{json:{...}}`. Localiza recursivamente `infoClasePeriodo`, `cabeceraNotas` y `dataAlumno`, por lo que no debe devolver `students: []` cuando los alumnos sí están presentes en una respuesta envuelta.
- el cruce Classroom → SIEweb acepta de forma segura tanto `ALUCOD` como `A+ALUCOD` (solo cuando el resto es numérico), pero el payload de guardado siempre usa el `ALUCOD` real del Registro de Notas.
- la verificación posterior usa los mismos alias seguros, evitando `student_not_found_after_save` por el prefijo `A`.
- se mantienen el árbol UI-native, la detección de `e0006`, la verificación de persistencia y la protección de **Nivel de Logro**.

La suite v0.7.12 pasa **38/38 pruebas**. Además se contrastó el nuevo lector contra una captura real previa del Registro de Notas de SIEweb: detectó 49 criterios y 28 alumnos con sus celdas de nota.

Consulta `SIEWEB_SYNC_V0.7.12.md` y `TEST_REPORT_V0.7.12.txt`.

---

# Historial — SieRoom SRC 0.7.11

## SIEweb — corrección del `e0006` con fila UI-native

La v0.7.11 corrige un desajuste que todavía permanecía en v0.7.10: el desempeño nuevo se construía clonando una fila ya persistida. La respuesta real de `dataInicialPesosCriterios` muestra que una fila nueva (`flExiste=false`) tiene un esquema más pequeño y no debe llevar varios campos que el servidor agrega recién después de guardar.

Cambios principales:

- construye el desempeño nuevo con una **fila sparse/UI-native** desde cero;
- no serializa en una alta `ID_CLASE`, `ID_CURSO`, `GRUPOCOD`, `ID_CLASE_PERIODO`, `NIVEL`, `TIPO_EVA`, `FL_CONCLUSION` ni `ORDEN_PROG`;
- conserva `ID_CONTENIDO_REF` como padre real, `ID_PROGRAMA=5`, LLAVE/INDICE/ORDEN nuevos, `flExiste=false` y `EDITOREG=1`;
- si no hay réplica interna, **omite** `datosReplica` en vez de inventar `[]` o `{}`;
- ante `estado=0/e0006` explícito, relee SIEweb para confirmar que no se guardó nada y recién entonces prueba, de forma controlada, tres scopes de payload: árbol completo, raíz modificada y fila modificada;
- no reintenta ante errores ambiguos distintos de e0006;
- `estado=1` sigue requiriendo verificación doble en editor + Registro de Notas;
- la réplica 2.º A ↔ 2.º B continúa resolviendo cada sección por separado;
- **Nivel de Logro permanece protegido** y no se escriben notas hasta confirmar el desempeño.

La suite v0.7.11 pasa **32/32 pruebas**, incluida una prueba de fallback adaptativo e0006 y una validación adicional contra una captura real de `resCriterios`.

Consulta `SIEWEB_SYNC_V0.7.11.md` y `TEST_REPORT_V0.7.11.txt`.

---

# Historial — SieRoom SRC 0.7.8

## SIEweb — criterios/desempeños persistentes (v0.7.8)

- Corrige el flujo que podía devolver `estado: 1` sin guardar realmente el desempeño y el caso `e0006`.
- Antes de escribir, relee `dataInicialPesosCriterios` y detecta la colección completa que usa el editor de SIEweb.
- Las altas se insertan clonando un hermano real dentro de esa colección; las ediciones modifican la fila real existente.
- El POST a `HyoClaseContenido/insertar` envía el modelo completo del editor y los `datosReplica` reales cuando SIEweb los proporciona.
- Solo se declara éxito si el desempeño aparece exactamente una vez tanto en el editor como en el Registro de Notas.
- Un falso `estado: 1` detiene el flujo y bloquea la posterior carga de notas.
- Classroom → SIEweb continúa limitado a desempeños `nivelEva=3`; **Nivel de Logro no se modifica**.

Consulta `SIEWEB_SYNC_V0.7.8.md` para el detalle técnico.

## SIEweb — respuestas dentro del hilo (v0.7.5)

La v0.7.5 corrige el flujo de **Responder** en Mensajería SIEweb. La respuesta ahora relee el mensaje original, conserva el asunto real por defecto, puede resolver el USUCOD del remitente desde el detalle, mantiene `idEdition` como identificador numérico (en v0.7.4 se enviaba como texto) y solo informa `sent=true` cuando SIEweb devuelve `estado=1`.

Herramientas recomendadas:

- `sieweb_messaging action=prepare_reply`: prepara y muestra el contexto del hilo sin enviar.
- `sieweb_messaging action=reply`: responde el hilo existente después de confirmación.
- `sieweb_reply_message`: alias directo con la misma preparación segura.

No se crea un correo nuevo cuando se usa `reply`. Si SIEweb responde `estado=0` (por ejemplo `e0001`), SieRoom lo trata como fallo y no afirma que el mensaje fue enviado.


## SIEweb — guardado seguro de notas (v0.7.4)

- `sieweb_academics action=save_grades_verified` es la ruta recomendada para escribir calificaciones.
- El payload se construye copiando la celda real devuelta por `obtRegistroNotas`; no se reconstruye desde cero.
- El preflight exige que todas las notas solicitadas encuentren alumno y celda.
- Después del guardado se vuelve a leer el gradebook y solo se declara éxito si las notas quedaron persistidas.
- `update_grades` se conserva como operación de bajo nivel por compatibilidad.


## Comentarios privados nativos de Classroom mediante puente local

Esta versión añade `classroom_private_feedback`, una cola segura para retroalimentación privada. El servidor obtiene `StudentSubmission.alternateLink` por la API oficial, encola el comentario y el componente local `browser_extension/` abre esa entrega con la sesión ya iniciada en Classroom. La extensión escribe el comentario en el cuadro **Comentarios privados** y confirma el resultado a SieRoom. Solo después, si el trabajo fue configurado con nota/devolución, el servidor usa la API oficial para calificar y/o devolver la entrega.

### Seguridad

- No se copian cookies de Google a Render.
- No se guarda el refresh token de Google en la extensión.
- El canal Render ↔ extensión usa un secreto independiente `CLASSROOM_BRIDGE_SECRET`.
- Los endpoints `/bridge/v1/*` rechazan peticiones sin ese secreto.
- La cola es temporal/en memoria: está pensada para trabajos inmediatos, no como almacenamiento permanente.

### Instalación del puente

1. En Render agrega `CLASSROOM_BRIDGE_SECRET` con un valor aleatorio largo. Puedes generarlo con `python generar_bridge_secret.py`.
2. Despliega v0.7.8 y espera `LIVE`.
3. En Chrome/Brave abre `chrome://extensions`, activa **Modo de desarrollador** y pulsa **Cargar descomprimida**. Selecciona la carpeta `browser_extension`.
4. Abre la extensión, pega el mismo `CLASSROOM_BRIDGE_SECRET`, pulsa **Guardar y probar** y luego **Iniciar puente**.
5. Deja abierta la pestaña `SieRoom Classroom Bridge` mientras procesas entregas.
6. En ChatGPT actualiza las acciones de SieRoom y usa `classroom_private_feedback`.

### Flujo de uso

`revisar archivo -> redactar feedback -> classroom_private_feedback queue -> navegador publica comentario privado -> nota opcional -> devolución opcional`

Si el comentario se publica pero la API oficial rechaza posteriormente la nota/devolución, el trabajo queda como `comment_posted_followup_failed`; SieRoom informa el éxito parcial y no repite el comentario silenciosamente.

---


## v0.6.5 — destinatarios masivos por sección en SieWeb

- Corrige el caso **“padres de familia de 2A y 2B”**: ya no intenta buscar esa frase como si fuera un nombre.
- Extrae las secciones de lenguaje natural (`2A`, `2.º B`, `S2A`, etc.).
- Obtiene alumnos `TIPCOD=005` por `NGS` y resuelve sus familias `TIPCOD=004` usando únicamente registros reales del directorio.
- Admite coincidencia exacta, apellidos familiares abreviados y pequeñas erratas únicas, siempre con diagnóstico.
- Deduplica familias y bloquea el envío si queda algún alumno sin resolver o una coincidencia ambigua.
- `sieweb_create_email`, `sieweb_send_new_email` y `sieweb_messaging` heredan este comportamiento sin cambiar el endpoint real de envío.

# Santa Rita Escolar v0.6.3

Servidor MCP remoto para **Google Classroom + SieWeb**. Esta versión extiende la v0.6.0 para revisar archivos entregados por estudiantes, dar retroalimentación sobre esos archivos, publicar anuncios y hacer más visible el envío de mensajes nuevos por SieWeb.

## Correos NUEVOS en CIEWEB/SIEWEB — v0.6.3

Se reforzó la mensajería para que ChatGPT no confunda **crear un correo nuevo** con **responder un hilo existente**.

Herramientas explícitas:

- `sieweb_capabilities`: confirma que la versión puede crear/enviar correos nuevos.
- `sieweb_create_email`: compone un correo nuevo, resuelve destinatario por nombre/USUCOD y devuelve una vista previa sin enviarla.
- `sieweb_send_new_email`: envía un correo nuevo real después de confirmación. No necesita `reply_to_message_id`, `idEdition` ni un hilo previo.

El envío usa el endpoint observado en DevTools:

`POST /lms/api/HyoMensajeria/enviarMensaje`

con el payload de correo nuevo: `adjunto`, `asunto`, `fh_programado`, `mensaje`, `para`, `programado`.

El directorio de destinatarios usa:

`GET /lms/api/HyoUsuario/obtListaUsuariosIntranet?isMensajeria=true`

Tipos observados: `004` familia, `005` alumno, `006` docente.

Ejemplos:

1. `Crea un correo nuevo para la familia de Sergio Caballero de 2.º A, asunto Seguimiento, con este texto. No lo envíes.`
2. `Ahora envíalo.`
3. `Crea y envía un correo nuevo al señor Huarachi...` (mostrará vista previa/confirmación antes de escribir).

**Nota:** SieWeb no necesita una operación separada de "guardar borrador" para poder enviar un correo nuevo. El conector compone la vista previa localmente y SieWeb crea el registro definitivo al ejecutar `enviarMensaje`.

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


## v0.6.3 — esquema compacto de 17 herramientas

Esta versión reduce el catálogo MCP de 48 herramientas a 17 herramientas agrupadas para evitar que acciones importantes queden fuera de la selección/descubrimiento de ChatGPT. No elimina capacidades: los aliases se convierten en helpers internos.

Mensajería SieWeb queda concentrada en `sieweb_messaging` con acciones `capabilities`, `list`, `read`, `search_recipients`, `compose_new`, `send_new` y `reply`. `send_new` crea y envía un correo NUEVO mediante `/lms/api/HyoMensajeria/enviarMensaje` sin requerir hilo previo.

El registro académico queda en `sieweb_academics`; los flujos Classroom↔SieWeb quedan en `workflow_school`; la revisión de adjuntos se incorpora a `classroom_submissions`, manteniendo `classroom_attachment_image` para visión de fotos/PDF.


## v0.6.3 - Compatibilidad robusta de mensajería SieWeb

Esta versión restaura como herramientas MCP explícitas, además del router agrupado, los nombres `sieweb_list_messages`, `sieweb_read_message`, `sieweb_search_recipients`, `sieweb_create_email`, `sieweb_send_new_email`, `sieweb_reply_message` y `sieweb_capabilities`. Así un cliente que todavía invoque un nombre de una versión anterior no obtiene `Unknown tool`.

Las herramientas críticas de mensajería se registran antes de las de Classroom. `sieweb_send_new_email` crea y envía un mensaje nuevo mediante `HyoMensajeria/enviarMensaje` sin `idEdition` ni `response`; `sieweb_reply_message` se reserva para respuestas a un hilo.


## v0.6.5 — Correos masivos por sección (SieWeb)

Se corrigió la resolución de destinatarios colectivos. Para expresiones como **“padres de familia de 2.º A y 2.º B”**, el conector ya no debe intentar resolver `idClase`/`idAmbito` ni buscar la frase literalmente.

Nuevas acciones explícitas:

- `sieweb_resolve_family_group(sections=["2A","2B"])`: obtiene alumnos por `NGS` (TIPCOD 005), relaciona sus apellidos con usuarios familia reales (TIPCOD 004), deduplica `USUCOD` y devuelve diagnóstico. No envía nada.
- `sieweb_send_section_email(...)`: previsualiza o envía un único correo masivo a las familias resueltas. `confirmed=false` solo prepara; `confirmed=true` envía. No usa IDs académicos de clase.
- `sieweb_search_recipients` ahora detecta grupos por sección y usa el mismo resolutor en vez de una búsqueda literal.

Seguridad: nunca inventa `USUCOD`; si queda un alumno sin familia o una coincidencia ambigua, bloquea el envío y devuelve el diagnóstico.
