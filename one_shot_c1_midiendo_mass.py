from __future__ import annotations

import unicodedata
from typing import Any

TARGET_ASSIGNMENT = "C1: FICHA DE MIDIENDO NUESTRO AVANCE"


def _norm(value: Any) -> str:
    text = unicodedata.normalize("NFD", str(value or ""))
    text = "".join(ch for ch in text if unicodedata.category(ch) != "Mn")
    return " ".join(text.upper().split())


def _level(grade: int) -> str:
    return "A" if grade >= 15 else ("B" if grade >= 11 else "C")


def _perfect(name: str) -> str:
    return f"""{name},
He revisado tu trabajo de manera detallada, considerando las evidencias que presentaste en la ficha MATRICES: MIDIENDO NUESTRO AVANCE.

LO QUE HICISTE BIEN:
Desarrollaste correctamente los diez ejercicios de la ficha. En la pregunta 1 identificaste bien el orden de A = 2x2, B = 3x4 y C = 1x4. En la pregunta 2 representaste los datos en una matriz 3x3. En las preguntas 3 y 4 reconociste filas, columnas y elementos usando correctamente la notación aij. En la pregunta 5 determinaste la diagonal principal 5, 4, 3; la diagonal secundaria 7, 4, 9; y q21 = 1. En la pregunta 6 clasificaste correctamente las matrices identidad, escalar, triangular superior y triangular inferior. En la pregunta 7 reconociste la diagonal principal 6, 5, 8, 9, elementos situados por encima de ella y la matriz triangular superior. En la pregunta 8 calculaste correctamente las trazas 12, 17 y 25. En la pregunta 9 analizaste adecuadamente las proposiciones de verdadero y falso, y en la pregunta 10 construiste correctamente la matriz triangular inferior solicitada.

LO QUE DEBES MEJORAR:
No se identificaron errores matemáticos que requieran corrección en la evidencia revisada. El siguiente paso es mantener este mismo nivel de precisión, especialmente al leer subíndices, identificar diagonales y justificar las clasificaciones de matrices.

SUGERENCIAS:
Conserva el hábito de verificar cada respuesta antes de entregar. En matrices conviene revisar siempre tres aspectos: filas x columnas, posición fila-columna de cada elemento y ubicación de los ceros respecto de la diagonal principal.

Tu calificación es 20 - (A)""".strip()


def _feedback(name: str, grade: int, bien: str, errors: str, suggestions: str) -> str:
    return f"""{name},
He revisado tu trabajo de manera detallada, considerando las evidencias que presentaste en la ficha MATRICES: MIDIENDO NUESTRO AVANCE.

LO QUE HICISTE BIEN:
{bien}

LO QUE DEBES MEJORAR:
{errors}

SUGERENCIAS:
{suggestions}

Tu calificación es {grade} - ({_level(grade)})""".strip()


def _missing(name: str) -> str:
    return f"""{name},
He revisado tu estado de entrega en la actividad C1: FICHA DE MIDIENDO NUESTRO AVANCE.

LO QUE HICISTE BIEN:
En esta oportunidad no se cuenta con una evidencia presentada que permita reconocer logros específicos de aprendizaje en esta actividad.

LO QUE DEBES MEJORAR:
No se presentó evidencia de la ficha MIDIENDO NUESTRO AVANCE, por lo que no es posible valorar tu proceso ni verificar el desarrollo de los aprendizajes propuestos. Estás cursando quinto año de secundaria, una etapa en la que asumir con mayor autonomía tus responsabilidades académicas es especialmente importante. Cumplir con los compromisos, organizar tus tiempos y atender los plazos establecidos son hábitos que trascienden el colegio y serán valiosos en tus estudios posteriores, en el trabajo y en distintos aspectos de tu vida adulta.

SUGERENCIAS:
Toma esta situación como una oportunidad para fortalecer tu organización, constancia y responsabilidad personal. En adelante procura revisar oportunamente las indicaciones y presentar las evidencias dentro de los plazos establecidos.

Tu calificación es 0 - (C). Debido a que el sistema de registro ya se encuentra cerrado, esta calificación queda como definitiva para esta actividad.""".strip()


def _wrong(name: str, evidence: str) -> str:
    return f"""{name},
He revisado de manera detallada el archivo que adjuntaste en C1: FICHA DE MIDIENDO NUESTRO AVANCE.

LO QUE HICISTE BIEN:
Se verificó que existe un archivo/evidencia adjunta y que contiene trabajo matemático realizado por ti. Sin embargo, la evidencia corresponde a otra actividad y no a la ficha que debía evaluarse en este ítem.

LO QUE DEBES MEJORAR:
Evidencia presentada: {evidence}.
Error detectado: el archivo no corresponde a MATRICES: MIDIENDO NUESTRO AVANCE, que es la actividad específica de este ítem. Por esa razón no es válido trasladar respuestas ni asignar puntaje a partir de una ficha diferente, aunque trate también sobre matrices.
Procedimiento correcto: antes de enviar una evidencia, verifica el título de la actividad en Classroom y compáralo con el encabezado de la ficha que estás adjuntando. En este caso debía presentarse la ficha MIDIENDO NUESTRO AVANCE, con sus diez preguntas.
Resultado de la revisión: no existe evidencia válida de esta actividad que pueda ser calificada.

SUGERENCIAS:
Fortalece el hábito de revisar el nombre del archivo y de la actividad antes de pulsar Entregar. En quinto de secundaria, esta verificación forma parte de la responsabilidad y autonomía que necesitarás también en estudios superiores y en el ámbito laboral.

Tu calificación es 0 - (C). Debido a que el sistema de registro ya se encuentra cerrado, esta calificación queda como definitiva para esta actividad.""".strip()


TARGETS = {
    "ALESSIA FERREIRA TEJADA": (20, _perfect("Alessia"), "valid"),
    "ALEXANDRO ARTURO MARTINEZ ARMAS": (20, _perfect("Alexandro"), "valid"),
    "ANDRE ROBERTO YAFAC MEDINA": (20, _perfect("André"), "valid"),
    "ARIANA SOFIA FIGUEROA VARGAS": (20, _perfect("Ariana"), "valid"),
    "DIEGO ALEJANDRO LINARES ARTETA": (0, _missing("Diego"), "created_zero"),
    "DORIAN NICOLAS FERNANDEZ MORIS RODRIGUEZ": (19, _feedback("Dorian", 19,
        "Resolviste correctamente las preguntas 1 a 5; también identificaste bien la diagonal y el tipo de matriz de la pregunta 7, calculaste las trazas 12, 17 y 25 de la pregunta 8, analizaste correctamente las proposiciones de la pregunta 9 y construiste correctamente la matriz de la pregunta 10.",
        """Pregunta 6 - clasificación de las matrices E y T:
Tu respuesta/procedimiento: clasificaste E como triangular superior y T como escalar.
Error detectado: ambas clasificaciones quedaron intercambiadas.
Procedimiento correcto: E tiene todos los elementos fuera de la diagonal principal iguales a cero y los tres elementos diagonales iguales a 4, por lo que es escalar. En T, todos los elementos debajo de la diagonal principal son cero, por lo que es triangular superior.
Resultado correcto: E = matriz escalar; T = matriz triangular superior.""",
        "Antes de clasificar una matriz, observa primero la diagonal principal y después dónde se encuentran los ceros. Si todos los elementos diagonales son iguales y el resto son cero, reconoce una matriz escalar."), "valid"),
    "FATIMA GABRIELA MUJICA KCOMT": (20, _perfect("Fátima"), "valid"),
    "FATIMA MIA VARGAS ASENCIO": (18, _feedback("Fátima", 18,
        "Desarrollaste correctamente las preguntas 1 a 5, calculaste correctamente las trazas de la pregunta 8 y construiste correctamente la matriz triangular inferior de la pregunta 10. También identificaste adecuadamente la matriz identidad y la matriz escalar.",
        """Pregunta 6 - matrices T y R:
Tu respuesta/procedimiento: dejaste como clasificación final T = triangular inferior y R = triangular superior.
Error detectado: las dos clasificaciones están invertidas.
Procedimiento correcto: en T los ceros están debajo de la diagonal principal, por ello es triangular superior; en R los ceros están encima de la diagonal principal, por ello es triangular inferior.
Resultado correcto: T = triangular superior; R = triangular inferior.

Pregunta 7 - tipo de matriz A:
Tu respuesta/procedimiento: clasificaste A como triangular inferior.
Error detectado: los ceros de A se encuentran debajo de la diagonal principal.
Procedimiento correcto: cuando los elementos debajo de la diagonal principal son cero, la matriz es triangular superior.
Resultado correcto: A = triangular superior.

Pregunta 9, inciso b:
Tu respuesta/procedimiento: marcaste como falsa la afirmación sobre los ceros debajo de la diagonal principal.
Error detectado: esa afirmación corresponde precisamente a la definición de una matriz triangular superior.
Procedimiento correcto: compara la ubicación de los ceros con la diagonal principal.
Resultado correcto: b) Verdadero.""",
        "Usa la diagonal principal como línea de referencia: ceros debajo = triangular superior; ceros encima = triangular inferior. Antes de marcar V/F, contrasta cada frase con esa definición."), "valid"),
    "FERNANDA LUCIA GONZALES TAPIA": (18, _feedback("Fernanda", 18,
        "Resolviste correctamente los órdenes y la representación matricial de las preguntas 1 a 3, las diagonales de la pregunta 5, las clasificaciones principales de la pregunta 6, las trazas de la pregunta 8 y la construcción de la pregunta 10.",
        """Pregunta 4 - ubicación de elementos de P:
Tu respuesta/procedimiento: registraste solo tres valores, 1, 5 y 7.
Error detectado: la consigna pedía cuatro posiciones y faltó ubicar correctamente p34.
Procedimiento correcto: en pij, el primer subíndice indica la fila y el segundo la columna. Para p34 se busca fila 3, columna 4.
Resultado correcto: p12 = 1, p23 = 5, p34 = 3 y p31 = 7.

Pregunta 7, incisos b y c:
Tu respuesta/procedimiento: identificaste la diagonal principal, pero dejaste sin completar los dos elementos por encima de la diagonal y el tipo de matriz.
Error detectado: la pregunta quedó incompleta.
Procedimiento correcto: selecciona dos entradas situadas encima de la diagonal principal y observa que todos los elementos debajo de ella son cero.
Resultado correcto: son válidos, por ejemplo, 2 y -1; la matriz es triangular superior.

Pregunta 9, inciso a:
Tu respuesta/procedimiento: marcaste como falsa la afirmación “Toda matriz identidad es una matriz escalar”.
Error detectado: una identidad es un caso particular de matriz escalar, con todos los valores de la diagonal iguales a 1.
Procedimiento correcto: compara las definiciones de identidad y escalar.
Resultado correcto: a) Verdadero.""",
        "Revisa que cada pregunta tenga todos sus incisos contestados. Para la notación aij recuerda siempre fila primero y columna después; y para clasificaciones busca la definición más específica."), "valid"),
    "GRECIA LUCIA BAZAN ROMERO": (20, _perfect("Grecia"), "valid"),
    "HANNA ELENA VALENZUELA CABALLERO": (0, _missing("Hanna"), "created_zero"),
    "JORGE LUIS SAAVEDRA BENITES": (19, _feedback("Jorge Luis", 19,
        "Resolviste correctamente los órdenes, la representación de datos, la ubicación de elementos, las clasificaciones de la pregunta 6, la matriz triangular de la pregunta 7, las trazas de la pregunta 8 y la construcción de la pregunta 10.",
        """Pregunta 5 - diagonal secundaria de Q:
Tu respuesta/procedimiento: escribiste 9, 4, 7.
Error detectado: identificaste los tres elementos correctos, pero los registraste en sentido inverso al recorrido solicitado de la diagonal secundaria.
Procedimiento correcto: se lee desde la esquina superior derecha hacia la esquina inferior izquierda.
Resultado correcto: diagonal secundaria = 7, 4, 9.

Pregunta 9, inciso a:
Tu respuesta/procedimiento: marcaste como falsa la afirmación “Toda matriz identidad es una matriz escalar”.
Error detectado: una identidad sí cumple la definición de escalar porque todos sus elementos fuera de la diagonal son cero y todos los elementos diagonales son iguales.
Procedimiento correcto: reconoce a la identidad como el caso escalar con valor diagonal 1.
Resultado correcto: a) Verdadero.""",
        "En diagonales, mantén siempre el mismo sentido de lectura. En verdadero/falso, compara la afirmación con la definición completa antes de marcarla."), "valid"),
    "JORGE RODRIGO CALLE QUEVEDO": (18, _feedback("Jorge", 18,
        "Representaste correctamente los datos de la pregunta 2, resolviste la identificación de filas y columnas de la pregunta 3, clasificaste correctamente las matrices de la pregunta 6, resolviste la pregunta 7 y construiste correctamente la matriz de la pregunta 10.",
        """Pregunta 4 - elemento p31:
Tu respuesta/procedimiento: registraste p31 = 0.
Error detectado: p31 corresponde a la fila 3, columna 1 de P.
Procedimiento correcto: primero ubica la fila indicada por el primer subíndice y luego la columna indicada por el segundo.
Resultado correcto: p31 = 7.

Pregunta 5 - diagonal secundaria:
Tu respuesta/procedimiento: escribiste 9, 4, 7.
Error detectado: los valores están escritos en sentido inverso.
Procedimiento correcto: recorre la diagonal secundaria desde arriba a la derecha hacia abajo a la izquierda.
Resultado correcto: 7, 4, 9.

Pregunta 8 - traza de C:
Tu respuesta/procedimiento: escribiste 15.
Error detectado: la traza se obtiene sumando únicamente los elementos de la diagonal principal.
Procedimiento correcto: 2 + 7 + 8.
Resultado correcto: Traza(C) = 17.""",
        "Refuerza la lectura fila-columna de los subíndices y revisa las operaciones de suma de la diagonal principal antes de entregar."), "valid"),
    "LEONARDO RODRIGO CHOQUE GALINDO": (20, _perfect("Leonardo"), "valid"),
    "MARCO POLO TIMOTEO ESPINOZA": (18, _feedback("Marco Polo", 18,
        "Resolviste correctamente las preguntas 1 a 5, identificaste correctamente la diagonal y los elementos superiores de la pregunta 7, obtuviste las trazas de C y D y construiste adecuadamente la matriz de la pregunta 10.",
        """Pregunta 6 - clasificación de E, T y R:
Tu respuesta/procedimiento: clasificaste E como triangular superior, T como escalar y R como cuadrada.
Error detectado: esas respuestas no corresponden al tipo más específico mostrado por cada matriz.
Procedimiento correcto: E tiene diagonal 4,4,4 y ceros fuera de ella; T tiene ceros debajo de la diagonal; R tiene ceros encima de la diagonal.
Resultado correcto: E = escalar; T = triangular superior; R = triangular inferior.

Pregunta 8 - traza de B:
Tu respuesta/procedimiento: escribiste 11.
Error detectado: la traza suma únicamente 3 y 9, que son los elementos de la diagonal principal.
Procedimiento correcto: 3 + 9.
Resultado correcto: Traza(B) = 12.""",
        "Busca siempre el tipo más específico de matriz y, para la traza, marca primero la diagonal principal antes de sumar sus elementos."), "valid"),
    "MATIAS ANTONIO ALIAGA MONTOYA": (0, _wrong("Matías", "un video donde se desarrolla la ficha Introducción a las matrices, de ocho preguntas, en lugar de la ficha MIDIENDO NUESTRO AVANCE de diez preguntas"), "wrong"),
    "MAURICIO JESUS PACO FERNANDEZ": (20, _perfect("Mauricio"), "valid"),
    "MAYA CUEVA VALERA": (18, _feedback("Maya", 18,
        "Resolviste correctamente las preguntas 1 a 6, calculaste correctamente las tres trazas de la pregunta 8, desarrollaste correctamente los incisos b, c y d de la pregunta 9 y construiste correctamente la matriz triangular inferior de la pregunta 10.",
        """Pregunta 7, inciso a - diagonal principal:
Tu respuesta/procedimiento: escribiste 6, 5, 8, 1.
Error detectado: el último elemento diagonal está en la fila 4, columna 4 y es 9.
Procedimiento correcto: recorre las posiciones a11, a22, a33 y a44.
Resultado correcto: 6, 5, 8, 9.

Pregunta 7, inciso b - elementos por encima de la diagonal:
Tu respuesta/procedimiento: escribiste 2 y 0.
Error detectado: el 0 seleccionado no corresponde a un elemento situado por encima de la diagonal principal.
Procedimiento correcto: elige dos entradas con columna mayor que fila, por ejemplo a12 y a13.
Resultado correcto: son válidos, por ejemplo, 2 y -1.

Pregunta 9, inciso a:
Tu respuesta/procedimiento: marcaste como falsa la afirmación de que toda matriz identidad es escalar.
Error detectado: una identidad es un caso particular de matriz escalar.
Procedimiento correcto: observa que la identidad tiene ceros fuera de la diagonal y todos sus elementos diagonales son iguales a 1.
Resultado correcto: a) Verdadero.""",
        "En matrices grandes, recorre la diagonal usando posiciones a11, a22, a33... y verifica que los elementos elegidos como 'superiores' estén realmente por encima de ella."), "valid"),
    "NAARA MILAGROS QUISPE FLORES": (0, _wrong("Naara", "un PDF titulado PRÁCTICA DE AULA – OPERACIONES CON MATRICES, que corresponde a otra actividad"), "wrong"),
    "NICOLAS ANTONIO VARGAS SOLIS": (0, _wrong("Nicolás", "fotografías de una tarea/ficha de Introducción a las matrices, con una estructura distinta a MIDIENDO NUESTRO AVANCE"), "created_zero"),
    "RENZO RYUJI VEGA OYANAGI": (0, _missing("Renzo"), "created_zero"),
    "RODRIGO ALBERTO CADILLO WONG": (18, _feedback("Rodrigo", 18,
        "Representaste correctamente la matriz de datos de la pregunta 2, identificaste filas, columnas y elementos en las preguntas 3 y 4, resolviste la pregunta 7, calculaste correctamente las trazas y desarrollaste adecuadamente los incisos principales de verdadero/falso.",
        """Pregunta 1 - orden de C:
Tu respuesta/procedimiento: escribiste C = 1x1.
Error detectado: C tiene una sola fila, pero contiene cuatro elementos, por lo que tiene cuatro columnas.
Procedimiento correcto: cuenta primero filas y luego columnas.
Resultado correcto: C = 1x4.

Pregunta 5 - diagonal secundaria:
Tu respuesta/procedimiento: escribiste 9, 4, 7.
Error detectado: los elementos están registrados en orden inverso.
Procedimiento correcto: recorre la diagonal secundaria desde la esquina superior derecha hacia la inferior izquierda.
Resultado correcto: 7, 4, 9.

Pregunta 6 - matrices T y R:
Tu respuesta/procedimiento: las clasificaciones de triangular superior e inferior quedaron intercambiadas.
Error detectado: T tiene ceros debajo de la diagonal y R tiene ceros encima.
Procedimiento correcto: usa la diagonal principal como referencia.
Resultado correcto: T = triangular superior; R = triangular inferior.

Pregunta 10 - elemento k31:
Tu respuesta/procedimiento: escribiste 3 en la posición fila 3, columna 1.
Error detectado: la condición dada indica k31 = -3.
Procedimiento correcto: copia cada condición respetando también su signo.
Resultado correcto: k31 = -3; la tercera fila debe comenzar con -3.""",
        "Antes de entregar, haz una revisión final de dimensiones, sentido de las diagonales y signos. En matrices triangulares, recuerda: ceros debajo = superior; ceros encima = inferior."), "valid"),
    "RODRIGO ALONSO RODRIGUEZ GAMONAL": (0, _wrong("Rodrigo", "un documento titulado Introducción a las MATRICES, con ocho ejercicios, que no corresponde a la ficha MIDIENDO NUESTRO AVANCE"), "wrong"),
    "SEBASTIAN CORADO RIOFRIO": (0, _wrong("Sebastián", "una fotografía de la FICHA: INTRODUCCIÓN A LAS MATRICES, que corresponde a otra actividad"), "created_zero"),
    "VALERIA ANDREA IZAGUIRRE SOLIS": (20, _perfect("Valeria"), "valid"),
    "XIMENA ALEXANDRA SUAREZ ARGOTE": (0, _wrong("Ximena", "fotografías de PRÁCTICA DE AULA – OPERACIONES CON MATRICES, que corresponden a otra actividad"), "wrong"),
}


def enqueue_mass(classroom: Any, bridge_queue: Any) -> dict[str, Any]:
    target_norm = _norm(TARGET_ASSIGNMENT)
    course = work = None
    for c in classroom.list_courses(active_only=True):
        hay = _norm(f"{c.get('name') or ''} {c.get('section') or ''}")
        if "MATE 5TO" in hay and ("5TO - B" in hay or "5TO B" in hay):
            works = classroom.list_coursework(str(c.get("id") or ""), include_drafts=True)
            matches = [w for w in works if _norm(w.get("title")) == target_norm]
            if len(matches) == 1:
                course, work = c, matches[0]
                break
    if not course or not work:
        raise RuntimeError("C1_MIDIENDO_MASS: no se encontró de forma única curso/tarea objetivo.")

    course_id = str(course.get("id") or "")
    work_id = str(work.get("id") or "")
    students = classroom.list_students(course_id)
    submissions = classroom.list_submissions(course_id, work_id)
    by_user = {str(s.get("userId") or ""): s for s in students}
    found = set()
    jobs = []

    for sub in submissions:
        st = by_user.get(str(sub.get("userId") or "")) or {}
        key = _norm(st.get("name"))
        if key not in TARGETS:
            continue
        found.add(key)
        grade, comment, mode = TARGETS[key]
        submission_id = str(sub.get("id") or "")
        submission_url = str(sub.get("alternateLink") or "")
        if not submission_id or not submission_url:
            raise RuntimeError(f"C1_MIDIENDO_MASS: entrega sin id/url para {st.get('name')}")

        # CREATED + 0 ya registrado: no existe una entrega que devolver. R6.9.8
        # publica la retroalimentación y conserva el cero existente sin buscar Enviar/Devolver.
        if mode == "created_zero":
            existing_zero = any(
                value is not None and float(value) == 0.0
                for value in (sub.get("draftGrade"), sub.get("assignedGrade"))
            )
            if not existing_zero:
                raise RuntimeError(f"C1_MIDIENDO_MASS: {st.get('name')} CREATED no tiene 0 previo; se detiene por seguridad.")
            grade_arg = None
            return_after = False
        else:
            grade_arg = float(grade)
            return_after = True

        prior = [j for j in bridge_queue.matching(
            course_id=course_id,
            course_work_id=work_id,
            submission_id=submission_id,
            operation="post_private_comment",
        ) if str(getattr(j, "comment", "") or "").strip() == comment
            and getattr(j, "status", "") not in {"failed", "cancelled"}]
        if prior:
            print(f"C1_MIDIENDO_ALREADY_QUEUED: {st.get('name')} job={prior[0].id} status={prior[0].status}", flush=True)
            continue

        job = bridge_queue.enqueue(
            course_id=course_id,
            course_work_id=work_id,
            submission_id=submission_id,
            submission_url=submission_url,
            comment=comment,
            grade=grade_arg,
            return_after_comment=return_after,
            operation="post_private_comment",
        )
        jobs.append({"student": st.get("name"), "grade": grade, "mode": mode, "job_id": job.id, "guard_job_id": job.guard_job_id})
        print(f"C1_MIDIENDO_ENQUEUED: {st.get('name')} grade={grade} mode={mode} job={job.id} guard={job.guard_job_id}", flush=True)

    missing = sorted(set(TARGETS) - found)
    if missing:
        raise RuntimeError("C1_MIDIENDO_MASS: faltan estudiantes en Classroom: " + ", ".join(missing))
    print(f"C1_MIDIENDO_MASS_READY: {len(jobs)} trabajo(s) encolado(s) para 26 estudiantes revisados.", flush=True)
    return {"queued": bool(jobs), "count": len(jobs), "jobs": jobs, "course_name": course.get("name"), "work": work.get("title")}
