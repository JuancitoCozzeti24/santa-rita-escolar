# SieRoom SRC 0.7.6 — Classroom → SIEweb y réplica segura de desempeños

Esta versión parte de **0.7.5** y conserva correo, Classroom, Bridge y asesorías.

## Cambios
- `workflow_school action=classroom_grades_to_sieweb`: toma `assignedGrade` de Classroom, cruza al estudiante por correo institucional/alucod, convierte 0–20 a AD/A/B/C y guarda en un **desempeño nivel 3**.
- Protección obligatoria del Nivel de Logro: el flujo automático rechaza cualquier `header_id` cuyo `nivelEva` no sea 3.
- Relectura posterior: una nota solo se declara guardada si SIEweb la devuelve persistida.
- `workflow_school action=replicate_performances`: replica desempeños entre secciones resolviendo la capacidad padre y los IDs internos **independientemente en cada sección**.
- Prevención de duplicados por texto canónico + padre + nivel.
- Alta de desempeños verificada: después de `HyoClaseContenido/insertar`, relee el registro y exige exactamente una coincidencia.
- Si SIEweb responde `e0006` o cualquier estado distinto de éxito, no se declara guardado ni se continúa silenciosamente.
- Para secciones cuyo `idAmbito` todavía no esté mapeado (por ejemplo 2.º B), el flujo acepta `id_ambito_by_section`, evitando inventar IDs.

## Umbrales por defecto Classroom 0–20 → SIEweb
- AD: 18–20
- A: 15–17
- B: 11–14
- C: 0–10

Se pueden cambiar mediante `grade_thresholds`.

## Nota pedagógica
Una sola nota global de Classroom solo debe transferirse a un desempeño cuando representa ese desempeño. Si una evidencia produce notas distintas para Modela/Usa estrategias/Comunica, se debe ejecutar el guardado con el mapa específico de cada desempeño; la versión no copia mecánicamente la misma letra a todos.
