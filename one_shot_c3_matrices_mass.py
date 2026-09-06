from __future__ import annotations

import unicodedata
from typing import Any

TARGET_TOKENS = ("C3", "EVALUACION", "SEMANAL", "MATRICES")


def _norm(value: Any) -> str:
    text = unicodedata.normalize("NFD", str(value or ""))
    text = "".join(ch for ch in text if unicodedata.category(ch) != "Mn")
    return " ".join(text.upper().split())


def _missing(name: str) -> str:
    return f"""{name},
He revisado tu estado de entrega en C3: EVALUACIÓN SEMANAL DE MATRICES.

LO QUE HICISTE BIEN:
En esta oportunidad no se cuenta con una evidencia presentada que permita reconocer logros específicos de aprendizaje en esta evaluación.

LO QUE DEBES MEJORAR:
No se presentó evidencia de la evaluación semanal de matrices. Al no existir un desarrollo que pueda ser revisado, no es posible verificar procedimientos, resultados ni los aprendizajes alcanzados, por lo que la calificación se mantiene en 0/20 (C).

SUGERENCIAS:
Fortalece tu organización y responsabilidad frente a las actividades académicas. En quinto año de secundaria es especialmente importante revisar oportunamente las indicaciones, administrar los plazos y asegurarte de que la evidencia quede correctamente entregada. Estos hábitos serán valiosos también en tus estudios posteriores y en el ámbito laboral.

Tu calificación es 0 - (C)""".strip()


RODRIGO = """Rodrigo,
He revisado de manera detallada las cuatro páginas de tu C3: EVALUACIÓN SEMANAL DE MATRICES.

LO QUE HICISTE BIEN:
Resolviste correctamente prácticamente toda la evaluación. Hallaste correctamente la traspuesta en la pregunta 2; identificaste la matriz antisimétrica en la 3; trabajaste adecuadamente matriz opuesta, suma y resta en las preguntas 4 a 7; calculaste correctamente los productos matriciales y determinantes de las preguntas 8 a 15; resolviste correctamente la ecuación con traspuesta de la pregunta 16; encontraste x = ±3 en la pregunta 17; interpretaste adecuadamente el valor 17 de la pregunta 18; obtuviste QP = (58, 58) en la pregunta 19 y calculaste det(2A - B) = -12 en la pregunta 20. Tus procedimientos muestran dominio consistente de operaciones con matrices y determinantes.

LO QUE DEBES MEJORAR:
Pregunta 1 - orden de la matriz A:
Tu respuesta/procedimiento: escribiste correctamente a23 = 0, pero no anotaste el orden de la matriz A.
Error detectado: la consigna solicitaba dos respuestas: indicar el orden y escribir el elemento a23. Solo quedó registrada la segunda.
Procedimiento correcto: primero se cuentan las filas y luego las columnas. La matriz A tiene 2 filas y 3 columnas.
Resultado correcto: orden(A) = 2 x 3 y a23 = 0.

SUGERENCIAS:
Cuando una pregunta tenga más de una indicación, subraya mentalmente cada parte antes de responder. Tu desarrollo matemático fue muy sólido; una revisión final de las consignas te permitirá evitar perder puntos por respuestas incompletas aunque el procedimiento esté dominado.

Tu calificación es 19 - (A)""".strip()


MATIAS = """Matías,
He revisado de manera detallada las cuatro páginas de tu C3: EVALUACIÓN SEMANAL DE MATRICES.

LO QUE HICISTE BIEN:
Mostraste buen dominio general de las operaciones con matrices. Resolviste correctamente el orden y el elemento solicitado en la pregunta 1, la traspuesta de la pregunta 2, la identificación de antisimetría en la pregunta 3, la suma de la pregunta 5, las operaciones de las preguntas 6 a 12, el producto AB de la pregunta 13, el valor x = 4 de la pregunta 14, la ecuación con traspuesta de la pregunta 16, x = ±3 en la pregunta 17, el producto QP = (58, 58) de la pregunta 19 y el determinante final -12 de la pregunta 20.

LO QUE DEBES MEJORAR:
Pregunta 4 - matriz opuesta y comprobación:
Tu respuesta/procedimiento: la pregunta quedó sin desarrollar.
Error detectado: faltó escribir la matriz opuesta de B y verificar la suma con la matriz original.
Procedimiento correcto: se cambia el signo de cada elemento de B. Luego se suma elemento a elemento B + (-B).
Resultado correcto: -B = [[2, -5], [-3, 7]] y B + (-B) = [[0, 0], [0, 0]].

Pregunta 13 - orden del producto AB:
Tu respuesta/procedimiento: obtuviste correctamente AB = [[-3, -1], [9, 8]], pero no escribiste previamente el orden del resultado como pedía la consigna.
Error detectado: faltó anticipar la dimensión del producto.
Procedimiento correcto: A es 2 x 3 y B es 3 x 2; las dimensiones internas coinciden y quedan las externas.
Resultado correcto: AB es de orden 2 x 2.

Pregunta 14 - verificación del valor de x:
Tu respuesta/procedimiento: hallaste correctamente x = 4, pero no realizaste la verificación solicitada.
Error detectado: faltó sustituir el valor obtenido en el determinante.
Procedimiento correcto: det([[4,2],[3,4]]) = 4·4 - 2·3 = 16 - 6.
Resultado correcto: 10, por lo tanto x = 4 queda verificado.

Pregunta 15 - productos AB y BA:
Tu respuesta/procedimiento: escribiste solamente “NO”.
Error detectado: la consigna pedía calcular primero ambos productos y después comparar sus órdenes.
Procedimiento correcto: calcula fila por columna. AB resulta 2 x 2 y BA resulta 3 x 3.
Resultado correcto: AB = [[4,5],[-1,-2]]; BA = [[1,3,5],[1,-3,-1],[-1,6,4]]. No tienen el mismo orden y, por ello, no pueden ser iguales.

Pregunta 18 - interpretación del elemento (2,1):
Tu respuesta/procedimiento: calculaste correctamente M + T = [[24,18],[17,13]], pero la interpretación escrita no corresponde al elemento solicitado.
Error detectado: el elemento de fila 2, columna 1 es 17, no 10.
Procedimiento correcto: se suman los valores que ocupan la misma posición: 10 + 7 = 17.
Resultado correcto: (M + T)21 = 17; representa el total combinado de mañana y tarde en esa posición de la tabla.

SUGERENCIAS:
No te quedes solo con el resultado numérico cuando la consigna pida justificar, verificar o interpretar. Antes de entregar, revisa cada verbo de la pregunta: “calcula”, “verifica”, “escribe el orden”, “interpreta” o “responde”. Esa revisión te ayudará a convertir procedimientos correctos en respuestas completas.

Tu calificación es 17 - (A)""".strip()


FATIMA = """Fátima,
He revisado de manera detallada las cuatro páginas incluidas dentro del archivo ZIP de tu C3: EVALUACIÓN SEMANAL DE MATRICES.

LO QUE HICISTE BIEN:
Resolviste correctamente el orden y el elemento de la pregunta 1, la traspuesta de la pregunta 2, la matriz opuesta de la pregunta 4, la suma y resta de las preguntas 5 y 6, el producto por escalar de la pregunta 7, los determinantes de las preguntas 9 y 10, las ecuaciones matriciales de las preguntas 11 y 12, el producto AB de la pregunta 13, el valor x = 4 de la pregunta 14, los productos AB y BA de la pregunta 15 y la ecuación con traspuesta de la pregunta 16. También obtuviste correctamente las matrices y resultados principales de las preguntas 18, 19 y 20.

LO QUE DEBES MEJORAR:
Pregunta 3 - matriz antisimétrica:
Tu respuesta/procedimiento: calculaste correctamente S^T = [[0,-4],[4,0]], pero escribiste solamente “No es simétrica”.
Error detectado: faltó responder que S es antisimétrica y justificarlo con la igualdad solicitada.
Procedimiento correcto: compara S^T con -S.
Resultado correcto: S^T = -S, por lo tanto S es antisimétrica.

Pregunta 4 - comprobación de la matriz opuesta:
Tu respuesta/procedimiento: obtuviste correctamente -B = [[2,-5],[-3,7]], pero no realizaste la comprobación pedida.
Error detectado: faltó sumar B + (-B).
Procedimiento correcto: suma elemento a elemento la matriz original con su opuesta.
Resultado correcto: B + (-B) = [[0,0],[0,0]].

Pregunta 8 - producto AB:
Tu respuesta/procedimiento: escribiste AB = [[2,2],[15,12]].
Error detectado: el producto de matrices no se obtiene multiplicando elementos que ocupan posiciones semejantes; se multiplica cada fila de A por cada columna de B.
Procedimiento correcto: a11 = 2·1 + (-1)·(-2) = 4; a12 = 2·5 + (-1)·3 = 7; a21 = 3·1 + 4·(-2) = -5; a22 = 3·5 + 4·3 = 27.
Resultado correcto: AB = [[4,7],[-5,27]].

Pregunta 13 - orden del producto:
Tu respuesta/procedimiento: calculaste correctamente AB = [[-3,-1],[9,8]], pero omitiste escribir antes su orden.
Error detectado: faltó una parte explícita de la consigna.
Procedimiento correcto: A es 2 x 3 y B es 3 x 2; por tanto el producto es 2 x 2.
Resultado correcto: orden(AB) = 2 x 2.

Pregunta 14 - verificación:
Tu respuesta/procedimiento: hallaste correctamente x = 4, pero no sustituiste el valor para comprobarlo.
Error detectado: faltó la verificación solicitada.
Procedimiento correcto: 4·4 - 2·3 = 16 - 6.
Resultado correcto: det(D) = 10, verificando x = 4.

Pregunta 15 - comparación de AB y BA:
Tu respuesta/procedimiento: calculaste correctamente ambos productos, pero no respondiste las dos preguntas finales.
Error detectado: faltó indicar si tienen el mismo orden y si pueden ser iguales.
Procedimiento correcto: compara sus dimensiones después de calcularlos.
Resultado correcto: AB es 2 x 2 y BA es 3 x 3; no tienen el mismo orden y no pueden ser iguales.

Pregunta 17 - soluciones del determinante:
Tu respuesta/procedimiento: llegaste correctamente a x² = 9, pero escribiste únicamente x = 3.
Error detectado: una ecuación cuadrática x² = 9 tiene dos soluciones reales.
Procedimiento correcto: x = ±√9.
Resultado correcto: x = 3 y x = -3.

Pregunta 18 - interpretación:
Tu respuesta/procedimiento: obtuviste M + T = [[24,18],[17,13]] y (M+T)21 = 17, pero faltó interpretar el significado del 17.
Error detectado: la consigna pedía explicar el resultado, no solo calcularlo.
Procedimiento correcto: relaciona 10 de la mañana con 7 de la tarde en la misma posición.
Resultado correcto: 17 es el total combinado correspondiente a la fila 2, columna 1.

Pregunta 19 - interpretación de QP:
Tu respuesta/procedimiento: obtuviste correctamente QP = [[58],[58]], pero no explicaste los resultados.
Error detectado: faltó interpretar cada componente del vector.
Procedimiento correcto: cada fila de Q representa una tienda y se multiplica por el vector de precios.
Resultado correcto: cada tienda obtiene un total de S/58 para las cantidades registradas.

Pregunta 20 - determinante final:
Tu respuesta/procedimiento: calculaste correctamente 2A - B = [[3,3],[6,2]], pero dejaste sin hallar su determinante.
Error detectado: faltó la segunda parte de la pregunta.
Procedimiento correcto: det(2A-B) = 3·2 - 3·6 = 6 - 18.
Resultado correcto: det(2A-B) = -12.

SUGERENCIAS:
Tus resultados muestran que reconoces gran parte de los procedimientos, pero debes completar todas las partes de cada consigna. En especial, diferencia producto matricial de operaciones elemento a elemento y revisa siempre si la pregunta pide justificar, verificar, interpretar o hallar más de una solución.

Tu calificación es 16 - (A)""".strip()


TARGETS = {
    ("RENZO", "VEGA"): {"grade": 0, "comment": _missing("Renzo"), "mode": "created_zero"},
    ("DIEGO", "LINARES"): {"grade": 0, "comment": _missing("Diego"), "mode": "created_zero"},
    ("RODRIGO", "RODRIGUEZ"): {"grade": 19, "comment": RODRIGO, "mode": "graded"},
    ("MATIAS", "ALIAGA"): {"grade": 17, "comment": MATIAS, "mode": "graded"},
    ("FATIMA", "MUJICA"): {"grade": 16, "comment": FATIMA, "mode": "graded"},
}


def enqueue_mass(classroom: Any, bridge_queue: Any) -> dict[str, Any]:
    course = work = None
    for c in classroom.list_courses(active_only=True):
        hay = _norm(f"{c.get('name') or ''} {c.get('section') or ''}")
        if "MATE 5TO" not in hay or not ("5TO - B" in hay or "5TO B" in hay):
            continue
        works = classroom.list_coursework(str(c.get("id") or ""), include_drafts=True)
        matches = [w for w in works if all(tok in _norm(w.get("title")) for tok in TARGET_TOKENS)]
        if len(matches) == 1:
            course, work = c, matches[0]
            break
        if len(matches) > 1:
            raise RuntimeError("C3_MASS: múltiples actividades coinciden con C3 Evaluación semanal de matrices.")
    if not course or not work:
        raise RuntimeError("C3_MASS: no se encontró la actividad exacta en 5.º B.")

    course_id = str(course.get("id") or "")
    work_id = str(work.get("id") or "")
    students = classroom.list_students(course_id)
    submissions = classroom.list_submissions(course_id, work_id)
    by_user = {str(s.get("userId") or ""): s for s in students}
    jobs = []

    for tokens, cfg in TARGETS.items():
        matches = []
        for sub in submissions:
            st = by_user.get(str(sub.get("userId") or "")) or {}
            hay = _norm(f"{st.get('name') or ''} {st.get('email') or ''}")
            if all(tok in hay for tok in tokens):
                matches.append((st, sub))
        if len(matches) != 1:
            raise RuntimeError(f"C3_MASS: {' '.join(tokens)} coincide con {len(matches)} estudiantes.")
        st, sub = matches[0]
        submission_id = str(sub.get("id") or "")
        submission_url = str(sub.get("alternateLink") or "")
        if not submission_id or not submission_url:
            raise RuntimeError(f"C3_MASS: entrega sin id/url para {st.get('name')}")

        if cfg["mode"] == "created_zero":
            attachments = ((sub.get("assignmentSubmission") or {}).get("attachments") or [])
            existing_zero = any(v is not None and float(v) == 0.0 for v in (sub.get("draftGrade"), sub.get("assignedGrade")))
            if attachments:
                raise RuntimeError(f"C3_MASS: seguridad: {st.get('name')} ahora tiene evidencia; no se aplicará cero automático.")
            if _norm(sub.get("state")) != "CREATED" or not existing_zero:
                raise RuntimeError(f"C3_MASS: seguridad: {st.get('name')} ya no está CREATED con cero previo.")
            grade_arg = None
            return_after = False
        else:
            attachments = ((sub.get("assignmentSubmission") or {}).get("attachments") or [])
            if not attachments:
                raise RuntimeError(f"C3_MASS: seguridad: falta la evidencia revisada de {st.get('name')}.")
            grade_arg = float(cfg["grade"])
            return_after = True

        job = bridge_queue.enqueue(
            course_id=course_id,
            course_work_id=work_id,
            submission_id=submission_id,
            submission_url=submission_url,
            comment=str(cfg["comment"]),
            grade=grade_arg,
            return_after_comment=return_after,
            operation="post_private_comment",
        )
        jobs.append({"student": st.get("name"), "grade": cfg["grade"], "mode": cfg["mode"], "job_id": job.id, "guard_job_id": job.guard_job_id})
        print(f"C3_MASS_ENQUEUED: {st.get('name')} grade={cfg['grade']} mode={cfg['mode']} job={job.id} guard={job.guard_job_id}", flush=True)

    if len(jobs) != 5:
        raise RuntimeError(f"C3_MASS: se esperaban exactamente 5 estudiantes y se encolaron {len(jobs)}.")
    print("C3_MASS_READY: exactamente 5 estudiantes encolados; ningún otro estudiante fue incluido.", flush=True)
    return {"queued": True, "count": 5, "jobs": jobs, "course_name": course.get("name"), "work": work.get("title")}
