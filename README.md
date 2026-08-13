# Santa Rita Escolar v0.3.1 integral

Añade a v0.3.0 los endpoints confirmados el 13/08/2026:

- Descubrimiento de clases por `HyoClase/obtListar` y periodos por `HyoClase/obtClasePeriodo`.
- Resolución natural para Matemática 2026: 2.º A (`id_ambito=518`) y 5.º A (`id_ambito=524`).
- Directorio de mensajería por `HyoUsuario/obtListaUsuariosIntranet?isMensajeria=true`.
- Búsqueda de destinatarios por nombre, `USUCOD`, tipo y NGS.
- Mensaje NUEVO por `POST HyoMensajeria/enviarMensaje`, con confirmación previa en ChatGPT.
- Flujo Classroom -> SieWeb que agrega el `USUCOD` del alumno cuando existe.

## Tipos observados en el directorio
- `TIPCOD=004`: familia/apoderado.
- `TIPCOD=005`: alumno.
- `TIPCOD=006`: docente.

La selección siempre debe verificarse por nombre/tipo antes de enviar.

## Mapeo 2026
- S2A: `id_ambito=518`; Matemática `ID_CLASE=2030`; periodos 6304, 6305, 6306.
- S5A: `id_ambito=524`; Matemática `ID_CLASE=2112`; periodos 6550, 6551, 6552.

## Seguridad
Las herramientas de escritura exigen `confirmed=true`. No se incluyen secretos ni `.env` reales.
