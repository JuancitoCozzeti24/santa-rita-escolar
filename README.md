# Santa Rita Escolar v0.3.0 integral

Amplía el MCP remoto con:

- Classroom: cursos, docentes, alumnos, topics, anuncios, tareas, materiales, entregas completas, progreso por alumno, creación/edición/eliminación de tareas y calificación individual/lote.
- SieWeb: login autónomo, mensajería ya mapeada, registro de notas, criterios/desempeños, conclusiones descriptivas B/C, búsqueda por alumno/criterio y operaciones por lote.
- Cruce Classroom↔SieWeb: empareja el código del correo institucional de Classroom con `alucod` de SieWeb y puede identificar los pendientes de Classroom con sus IDs de SieWeb.

## Aún requiere mapeo adicional de SieWeb

Para llegar al uso 100% por nombres sin IDs y enviar mensajes NUEVOS a cualquier alumno/familia faltan capturar tres llamadas de la interfaz:
1. listado de salones/clases/periodos del profesor;
2. directorio de destinatarios de mensajería;
3. payload de mensaje nuevo (no respuesta).

## Render
Build: `pip install -r requirements.txt`
Start: `python server.py`
