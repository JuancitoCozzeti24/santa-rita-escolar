import copy

from sieweb import SieWebClient


def _sample_gradebook_nested():
    return {
        "outer": {
            "json": {
                "payload": {
                    "cabeceraNotas": [
                        {
                            "id": 9001,
                            "idpadre": 8001,
                            "idClaseContenido": 9101,
                            "desc": "AREA-PERIM 408",
                            "abreviatura": "AREA-PERIM 408",
                            "nivelEva": 3,
                            "info": {"programa": "Desempeño", "descComp": "Áreas y perímetros", "peso": 1},
                        }
                    ],
                    "dataAlumno": [
                        {
                            "datos": {
                                "idPersona": 321,
                                "alucod": "20180042",
                                "nomcomp": "ESTUDIANTE DE PRUEBA",
                                "ngs": "S2A",
                                "nemo": "2026019",
                                "numord": 1,
                                "estadoAnual": "V",
                            },
                            "notas": {
                                "9001": {
                                    "idCabecera": 9001,
                                    "idNota": 9101,
                                    "notaIni": "",
                                    "notaReg": "B",
                                    "notaPeAnt": "",
                                    "nivelEva": 3,
                                    "llave": 1,
                                }
                            },
                        }
                    ],
                    "infoClasePeriodo": {
                        "idClasePeriodo": 6305,
                        "idAmbito": 518,
                        "idClase": 2030,
                        "idCurso": 24,
                        "idContenidoPrin": 119598,
                        "ano": "2026",
                        "cursocod": "05",
                        "cursonom": "Matemática",
                        "periodo": 2,
                        "nomSalon": 'Secundaria Segundo Grado "A"',
                        "arrNGS": ["S2A"],
                        "arrNemo": ["2026019"],
                    },
                    "dataPermisoRegistro": {"editarNotas": True},
                }
            }
        }
    }


def test_v0712_get_criteria_auto_resolves_and_sends_cursocod(monkeypatch):
    c = SieWebClient()
    monkeypatch.setattr(
        c,
        "list_classes",
        lambda **kwargs: {"json": [{"ID_CLASE": 2030, "CURSOCOD": "05"}]},
    )
    seen = {}

    def fake_request(method, path, **kwargs):
        seen.update(copy.deepcopy(kwargs.get("params") or {}))
        return {"json": {"resCriterios": []}}

    monkeypatch.setattr(c, "_request", fake_request)
    c.get_criteria(
        class_id=2030,
        class_period_id=6305,
        root_content_id=119598,
        id_ambito=518,
        extra_params={"idPeriodoAnt": 6304},
    )
    assert seen["CURSOCOD"] == "05"
    assert seen["idClase"] == 2030
    assert seen["idClasePeriodo"] == 6305
    assert seen["idContenido"] == 119598
    assert seen["idAmbito"] == 518
    assert seen["idPeriodoAnt"] == 6304


def test_v0712_get_criteria_caches_course_context(monkeypatch):
    c = SieWebClient()
    calls = {"classes": 0}

    def fake_classes(**kwargs):
        calls["classes"] += 1
        return {"json": [{"ID_CLASE": 2030, "CURSOCOD": "05"}]}

    monkeypatch.setattr(c, "list_classes", fake_classes)
    monkeypatch.setattr(c, "_request", lambda *args, **kwargs: {"json": {"resCriterios": []}})
    for _ in range(3):
        c.get_criteria(
            class_id=2030,
            class_period_id=6305,
            root_content_id=119598,
            id_ambito=518,
        )
    assert calls["classes"] == 1


def test_v0712_gradebook_reader_finds_students_through_nested_wrappers():
    c = SieWebClient()
    summary = c.summarize_gradebook(_sample_gradebook_nested())
    assert summary["class"]["cursocod"] == "05"
    assert len(summary["criteria"]) == 1
    assert len(summary["students"]) == 1
    assert summary["students"][0]["alucod"] == "20180042"
    assert summary["students"][0]["notas"]["9001"]["nivelEva"] == 3
    assert summary["reader_diagnostics"]["student_count"] == 1


def test_v0712_grade_build_accepts_classroom_a_prefix_but_sends_real_alucod():
    c = SieWebClient()
    summary = c.summarize_gradebook(_sample_gradebook_nested())
    records = c.build_grade_records(
        summary,
        header_id=9001,
        grades_by_student_code={"A20180042": "A"},
    )
    assert len(records) == 1
    assert records[0]["alucod"] == "20180042"
    assert records[0]["idPersona"] == 321
    assert records[0]["notaNue"] == "A"
    assert records[0]["nivelEva"] == 3


def test_v0712_grade_verification_accepts_classroom_a_prefix_after_save():
    c = SieWebClient()
    raw = _sample_gradebook_nested()
    raw["outer"]["json"]["payload"]["dataAlumno"][0]["notas"]["9001"]["notaReg"] = "A"
    summary = c.summarize_gradebook(raw)
    check = c.verify_grade_changes(
        summary,
        header_id=9001,
        grades_by_student_code={"A20180042": "A"},
    )
    assert check["ok"] is True
    assert check["verified_count"] == 1
    assert check["failed_count"] == 0


def test_v0712_student_code_alias_is_not_fuzzy_for_names():
    c = SieWebClient()
    assert c._student_code_aliases("A20180042@colegio.edu") == {"A20180042", "20180042"}
    assert c._student_code_aliases("20180042") == {"20180042", "A20180042"}
    assert c._student_code_aliases("juan.perez") == {"JUAN.PEREZ"}
