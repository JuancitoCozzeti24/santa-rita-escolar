import pytest

from sieweb import SieWebClient, SieWebError


def _summary():
    return {
        "class": {
            "arrNivelGrado": [{"n": "S", "g": "2"}],
            "arrNGS": ["S2A"],
        }
    }


def test_resolve_grade_write_scope_keeps_arr_ngs_separate():
    client = SieWebClient()

    assert client.resolve_grade_write_scope(_summary(), ["S2A"]) == [
        {"n": "S", "g": "2"}
    ]
    assert client.resolve_grade_write_scope(_summary(), '["S2A"]') == [
        {"n": "S", "g": "2"}
    ]
    assert client.resolve_grade_write_scope(
        _summary(), [{"n": "S", "g": "2"}]
    ) == [{"n": "S", "g": "2"}]

    with pytest.raises(SieWebError):
        client.resolve_grade_write_scope(_summary(), ["S2B"])

    with pytest.raises(SieWebError):
        client.resolve_grade_write_scope(_summary(), [{"n": "S", "g": "5"}])


class _CaptureClient(SieWebClient):
    def __init__(self):
        super().__init__()
        self.sent_payload = None

    def _request(self, method, path, *, params=None, json=None):
        self.sent_payload = json
        return {"json": {"estado": 1}}


def test_update_grades_sends_native_arr_nivel_grado_as_objng():
    client = _CaptureClient()
    client.update_grades(
        year="2026",
        course_code="05",
        class_period_id=6305,
        period=2,
        section_ng=[{"n": "S", "g": "2"}],
        records=[
            {
                "alucod": "20170081",
                "idPersona": 123,
                "notaNue": "A",
            }
        ],
        notify=False,
    )

    assert client.sent_payload["objNG"] == [{"n": "S", "g": "2"}]


def test_update_grades_blocks_arr_ngs_strings_before_put():
    client = _CaptureClient()

    with pytest.raises(SieWebError):
        client.update_grades(
            year="2026",
            course_code="05",
            class_period_id=6305,
            period=2,
            section_ng=["S2A"],
            records=[
                {
                    "alucod": "20170081",
                    "idPersona": 123,
                    "notaNue": "A",
                }
            ],
            notify=False,
        )

    assert client.sent_payload is None
