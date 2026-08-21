from copy import deepcopy

from sieweb import SieWebClient, SieWebError


HEADER_ID = 7001


def sample_summary():
    return {
        "criteria": [{"id": HEADER_ID, "nivelEva": 2}],
        "students": [
            {
                "idPersona": 101,
                "alucod": "A001",
                "nomcomp": "ALUMNO UNO",
                "nemo": "2A",
                "notas": {
                    str(HEADER_ID): {
                        "idNota": 9001,
                        "nivelEva": 2,
                        "notaIni": "11",
                        "notaReg": "11",
                        "campoInterno": "CONSERVAR",
                        "objInterno": {"x": 1},
                    }
                },
            },
            {
                "idPersona": 102,
                "alucod": "A002",
                "nomcomp": "ALUMNO DOS",
                "nemo": "2A",
                "notas": {
                    str(HEADER_ID): {
                        "idNota": 9002,
                        "nivelEva": 2,
                        "notaInicial": "13",
                        "notaRegistrada": "13",
                        "tokenCelda": "XYZ",
                    }
                },
            },
        ],
    }


def test_build_preserves_real_cell():
    client = SieWebClient()
    summary = sample_summary()
    records = client.build_grade_records(
        summary,
        header_id=HEADER_ID,
        grades_by_student_code={"A001": "17", "A002": "18"},
    )
    assert len(records) == 2
    first = records[0]
    assert first["campoInterno"] == "CONSERVAR"
    assert first["objInterno"] == {"x": 1}
    assert first["notaIni"] == "11"
    assert first["notaReg"] == "11"
    assert first["notaNue"] == "17"
    assert first["idPersona"] == 101
    assert first["alucod"] == "A001"
    assert first["nemo"] == "2A"


def test_build_is_all_or_nothing():
    client = SieWebClient()
    try:
        client.build_grade_records(
            sample_summary(),
            header_id=HEADER_ID,
            grades_by_student_code={"A001": "17", "NO_EXISTE": "15"},
        )
    except SieWebError as exc:
        assert "student_not_found" in str(exc)
        assert "No se envió nada" in str(exc)
    else:
        raise AssertionError("El preflight debió bloquear el lote parcial")


def test_verify_registered_note():
    client = SieWebClient()
    after = sample_summary()
    after["students"][0]["notas"][str(HEADER_ID)]["notaReg"] = "17"
    after["students"][1]["notas"][str(HEADER_ID)]["notaRegistrada"] = "18"
    result = client.verify_grade_changes(
        after,
        header_id=HEADER_ID,
        grades_by_student_code={"A001": "17", "A002": "18"},
    )
    assert result["ok"] is True
    assert result["verified_count"] == 2


class FakeSieWeb(SieWebClient):
    def __init__(self):
        super().__init__()
        self.summary = sample_summary()
        self.sent_records = None

    def get_gradebook_summary(self, *, class_period_id, root_content_id, extra_params=None):
        return deepcopy(self.summary)

    def update_grades(self, *, year, course_code, class_period_id, period, section_ng,
                      records, class_name=None, notify=True):
        self.sent_records = deepcopy(records)
        by_code = {s["alucod"]: s for s in self.summary["students"]}
        for record in records:
            target = by_code[record["alucod"]]["notas"][str(HEADER_ID)]
            if "notaReg" in target:
                target["notaReg"] = record["notaNue"]
            if "notaRegistrada" in target:
                target["notaRegistrada"] = record["notaNue"]
        return {"update": {"json": {"estado": 1}}, "notification": None}


def test_full_safe_save():
    client = FakeSieWeb()
    out = client.save_grades_verified(
        year="2026",
        course_code="05",
        class_period_id=123,
        root_content_id=456,
        period=2,
        section_ng=[{"ng": "2", "nemo": "A"}],
        header_id=HEADER_ID,
        grades_by_student_code={"A001": "17", "A002": "18"},
        notify=False,
    )
    assert out["saved"] is True
    assert out["verification"]["ok"] is True
    assert client.sent_records[0]["campoInterno"] == "CONSERVAR"
    assert client.sent_records[0]["notaIni"] == "11"
    assert client.sent_records[0]["notaNue"] == "17"


if __name__ == "__main__":
    test_build_preserves_real_cell()
    test_build_is_all_or_nothing()
    test_verify_registered_note()
    test_full_safe_save()
    print("OK: pruebas SIEweb grades v0.7.4")
