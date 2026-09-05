from __future__ import annotations

import unicodedata
from typing import Any

TARGET_ASSIGNMENT = "SUBIR AQUÍ FICHA INTRO MATRICES"

TARGETS = [
    {
        "tokens": ("LEONARDO", "CHOQUE", "GALINDO"),
        "grade": 16,
        "feedback": """Leonardo,
He revisado tu trabajo de manera detallada. La ficha evidencia que comprendes la mayor parte de los contenidos trabajados sobre matrices.

LO QUE HICISTE BIEN:
Resolviste correctamente el ejercicio 2 al identificar las 3 filas, 3 columnas y los elementos 0, 5 y 7 de la fila 2. En el ejercicio 3 ubicaste correctamente p12 = 1, p23 = 5, p34 = 3 y p14 = 2. En el ejercicio 5 clasificaste correctamente la matriz identidad I, la matriz escalar E y la matriz triangular superior T. En el ejercicio 6 identificaste correctamente la diagonal principal 6, 5, 8, 9 y señalaste elementos ubicados por encima de ella. También calculaste correctamente las trazas del ejercicio 7: 12, 17 y 25. En el ejercicio 8 identificaste adecuadamente los valores de verdad y realizaste correcciones en las proposiciones falsas.

LO QUE DEBES MEJORAR:
Ejercicio 1 - orden de las matrices B y C:
Tu respuesta/procedimiento: escribiste B = 2x3 y C = 3x4.
Error detectado: intercambiaste el número de filas y columnas de ambas matrices.
Procedimiento correcto: el orden siempre se expresa como filas x columnas. Primero se cuentan las filas y luego las columnas.
Resultado correcto: B = 3x4 y C = 2x3.

Ejercicio 4 - diagonales y elemento q21:
Tu respuesta/procedimiento: marcaste gráficamente las diagonales sobre la matriz, pero dejaste sin escribir las respuestas solicitadas en los incisos a), b) y c).
Error detectado: identificar visualmente las diagonales es un buen inicio, pero la actividad pedía escribir sus elementos y determinar q21.
Procedimiento correcto: diagonal principal: 5, 4, 3; diagonal secundaria: 7, 4, 9; para q21 se busca fila 2, columna 1.
Resultado correcto: diagonal principal = 5, 4, 3; diagonal secundaria = 7, 4, 9; q21 = 1.

Ejercicio 5 - clasificación de R:
Tu respuesta/procedimiento: clasificaste R como triangular superior.
Error detectado: en R los ceros se encuentran por encima de la diagonal principal.
Procedimiento correcto: cuando los elementos por encima de la diagonal principal son cero, la matriz es triangular inferior.
Resultado correcto: R es triangular inferior.

Ejercicio 6 - tipo de matriz:
Tu respuesta/procedimiento: escribiste solamente que era una matriz cuadrada.
Error detectado: aunque es cuadrada, el ejercicio busca la clasificación más específica.
Procedimiento correcto: observa que todos los elementos por debajo de la diagonal principal son cero.
Resultado correcto: es una matriz triangular superior.

SUGERENCIAS:
Antes de responder el orden de una matriz, repite siempre “filas x columnas”. Cuando una consigna pide escribir una diagonal, no basta con marcarla en el dibujo: anota sus elementos. Finalmente, en la clasificación de matrices utiliza siempre el tipo más específico que puedas reconocer.

Tu calificación es 16 - (A)""".strip(),
    },
    {
        "tokens": ("MATIAS", "ALIAGA", "MONTOYA"),
        "grade": 15,
        "feedback": """Matías,
He revisado cuidadosamente la evidencia que presentaste en video. Se observa que desarrollaste una parte importante de la ficha y que dominas varios procedimientos básicos de matrices.

LO QUE HICISTE BIEN:
En el ejercicio 2 identificaste correctamente las 3 filas, 3 columnas y los elementos 0, 5 y 7 de la fila 2. En el ejercicio 3 ubicaste correctamente los elementos pedidos de la matriz P. En el ejercicio 4 reconociste correctamente las diagonales y el elemento solicitado. En el ejercicio 5 clasificaste adecuadamente las matrices identidad, escalar, triangular superior y triangular inferior. En el ejercicio 6 identificaste correctamente los elementos de la diagonal principal y elementos situados por encima de ella. Asimismo, en el ejercicio 7 calculaste correctamente las trazas 12, 17 y 25.

LO QUE DEBES MEJORAR:
Ejercicio 1 - orden de las matrices B y C:
Tu respuesta/procedimiento: escribiste B = 2x3 y C = 3x4.
Error detectado: se invirtieron las dimensiones de ambas matrices.
Procedimiento correcto: el orden se expresa siempre como filas x columnas.
Resultado correcto: B = 3x4 y C = 2x3.

Ejercicio 6 - clasificación de la matriz A:
Tu respuesta/procedimiento: escribiste que la matriz era cuadrada.
Error detectado: la respuesta es cierta, pero no corresponde al tipo más específico solicitado.
Procedimiento correcto: observa los elementos que están debajo de la diagonal principal; todos son cero.
Resultado correcto: A es una matriz triangular superior.

Ejercicio 8 - verdadero o falso:
Tu respuesta/procedimiento: en la evidencia revisada este ejercicio quedó sin desarrollar.
Error detectado: faltó resolver las cuatro proposiciones y corregir las falsas.
Procedimiento correcto: analiza cada definición y luego marca V o F. Cuando sea falsa, escribe la afirmación correcta.
Resultado correcto: a) V; b) V; c) F, porque la traza se define para matrices cuadradas; d) F, porque una matriz 3x4 tiene 3 filas y 4 columnas.

SUGERENCIAS:
Procura revisar la ficha completa antes de subir la evidencia para evitar dejar un ejercicio sin responder. En el orden de matrices recuerda “filas x columnas”, y cuando se solicite clasificar una matriz busca siempre el tipo más específico.

Tu calificación es 15 - (A)""".strip(),
    },
    {
        "tokens": ("RODRIGO", "RODRIGUEZ", "GAMONAL"),
        "grade": 16,
        "feedback": """Rodrigo,
He revisado de manera detallada la evidencia que incluiste en tu documento. El trabajo muestra buen dominio general de los conceptos de orden, diagonales, elementos y traza de matrices.

LO QUE HICISTE BIEN:
Determinaste correctamente los órdenes A = 2x2, B = 3x4 y C = 2x3. En el ejercicio 2 identificaste correctamente filas, columnas y la fila 2 de M. En el ejercicio 4 escribiste correctamente la diagonal principal 5, 4, 3; la diagonal secundaria 7, 4, 9; y q21 = 1. Clasificaste correctamente I como identidad y E como escalar. Identificaste correctamente la diagonal principal y elementos superiores de la matriz A del ejercicio 6. En el ejercicio 7 obtuviste correctamente las trazas 12, 17 y 25. En el ejercicio 8 resolviste correctamente los incisos a), c) y d), incluyendo correcciones pertinentes en las proposiciones falsas.

LO QUE DEBES MEJORAR:
Ejercicio 3 - elemento p34:
Tu respuesta/procedimiento: anotaste un elemento igual a 7 para la tercera posición solicitada.
Error detectado: la posición requerida era p34, es decir, fila 3 y columna 4.
Procedimiento correcto: en pij, el primer subíndice indica la fila y el segundo la columna.
Resultado correcto: p34 = 3.

Ejercicio 5 - matrices T y R:
Tu respuesta/procedimiento: clasificaste T como triangular inferior y R como triangular superior.
Error detectado: ambas clasificaciones quedaron intercambiadas.
Procedimiento correcto: si los ceros están debajo de la diagonal principal, la matriz es triangular superior; si están encima, es triangular inferior.
Resultado correcto: T es triangular superior y R es triangular inferior.

Ejercicio 6 - tipo de matriz A:
Tu respuesta/procedimiento: escribiste triangular inferior.
Error detectado: en A los ceros se encuentran debajo de la diagonal principal.
Procedimiento correcto: identifica dónde están los ceros respecto de la diagonal principal.
Resultado correcto: A es triangular superior.

Ejercicio 8 - inciso b:
Tu respuesta/procedimiento: marcaste como falsa la afirmación sobre la matriz triangular superior.
Error detectado: una matriz triangular superior sí tiene ceros debajo de la diagonal principal.
Procedimiento correcto: compara la posición de los ceros con la diagonal principal antes de decidir V o F.
Resultado correcto: b) V.

SUGERENCIAS:
Refuerza la lectura de subíndices: primero fila y luego columna. Para matrices triangulares, usa como referencia visual la diagonal principal y observa en qué lado aparecen los ceros. Antes de entregar, contrasta cada clasificación con su definición.

Tu calificación es 16 - (A)""".strip(),
    },
]


def _norm(value: Any) -> str:
    text = unicodedata.normalize("NFD", str(value or ""))
    text = "".join(ch for ch in text if unicodedata.category(ch) != "Mn")
    return " ".join(text.upper().split())


def enqueue_mass(classroom: Any, bridge_queue: Any) -> dict[str, Any]:
    target_assignment_norm = _norm(TARGET_ASSIGNMENT)
    course = None
    work = None
    for c in classroom.list_courses(active_only=True):
        hay = _norm(f"{c.get('name') or ''} {c.get('section') or ''}")
        if "MATE 5TO" in hay and ("5TO - B" in hay or "5TO B" in hay):
            works = classroom.list_coursework(str(c.get("id") or ""), include_drafts=True)
            matches = [w for w in works if _norm(w.get("title")) == target_assignment_norm]
            if len(matches) == 1:
                course, work = c, matches[0]
                break
    if not course or not work:
        raise RuntimeError("ZERO_MASS: no se encontró de forma única el curso/tarea objetivo.")

    course_id = str(course.get("id") or "")
    work_id = str(work.get("id") or "")
    students = classroom.list_students(course_id)
    submissions = classroom.list_submissions(course_id, work_id)
    by_user = {str(s.get("userId") or ""): s for s in students}
    jobs = []

    for target in TARGETS:
        matches = []
        for sub in submissions:
            student = by_user.get(str(sub.get("userId") or "")) or {}
            hay = _norm(f"{student.get('name') or ''} {student.get('email') or ''}")
            if not all(tok in hay for tok in target["tokens"]):
                continue
            draft = sub.get("draftGrade")
            assigned = sub.get("assignedGrade")
            is_zero = (draft is not None and float(draft) == 0.0) or (assigned is not None and float(assigned) == 0.0)
            attachments = ((sub.get("assignmentSubmission") or {}).get("attachments") or [])
            if is_zero and attachments:
                matches.append((student, sub))
        if len(matches) != 1:
            print(f"ZERO_MASS_SKIP: {' '.join(target['tokens'])} matches={len(matches)} (requiere nota 0 + adjunto).", flush=True)
            continue
        student, sub = matches[0]
        job = bridge_queue.enqueue(
            course_id=course_id,
            course_work_id=work_id,
            submission_id=str(sub.get("id") or ""),
            submission_url=str(sub.get("alternateLink") or ""),
            comment=str(target["feedback"]),
            grade=float(target["grade"]),
            return_after_comment=True,
            operation="post_private_comment",
        )
        jobs.append({"student": student.get("name"), "grade": target["grade"], "job_id": job.id, "guard_job_id": job.guard_job_id})
        print(f"ZERO_MASS_ENQUEUED: {student.get('name')} grade={target['grade']} job={job.id} guard={job.guard_job_id}", flush=True)

    print(f"ZERO_MASS_READY: {len(jobs)} trabajo(s) encolado(s).", flush=True)
    return {"queued": bool(jobs), "count": len(jobs), "jobs": jobs}
