# SieRoom SRC 0.7.17 — lectura privada verificada

## Problema corregido

Una copia antigua de SieRoom Bridge podía reclamar un trabajo `read_private_comments`, tratarlo como una publicación vacía y devolver `{ok: true}`. El servidor v0.7.16 aceptaba ese objeto demasiado genérico y marcaba el trabajo como completado aunque no hubiera recibido comentarios.

## Contrato nuevo

- La extensión envía `X-SieRoom-Bridge-Version` y `X-SieRoom-Bridge-Capabilities`.
- El servidor solo entrega trabajos de lectura a un puente que anuncie `read_private_comments`.
- Una lectura válida debe devolver:
  - `ok: true`;
  - `operation: read_private_comments`;
  - `comments` como lista;
  - `count` entero e igual a la longitud de `comments`.
- Cualquier resultado del flujo de publicación se rechaza como `bridge_incompatible_read_result`.

## Seguridad

La lectura no publica comentarios, no cambia la nota de Classroom, no devuelve entregas y no modifica el Nivel de Logro en SIEWeb. Las cookies de Google permanecen dentro del navegador docente.

## Verificación

La suite completa pasa 55/55 pruebas, incluidas pruebas específicas que demuestran que una extensión antigua no puede reclamar lecturas ni completar una lectura con un resultado del flujo de publicación.
