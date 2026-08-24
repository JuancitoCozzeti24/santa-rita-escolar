import json
import os
from copy import deepcopy

import pytest

os.environ.setdefault("AUTH0_ISSUER", "https://tests.example.auth0.com")
os.environ.setdefault("AUTH0_AUDIENCE", "https://tests.example/api")
os.environ.setdefault("CLASSROOM_BRIDGE_SECRET", "test-bridge-secret")

from bridge import ClassroomBridgeQueue
from sieweb import SieWebClient, SieWebError
import server


def scoped_read(url, numeric, qualitative):
    text = f"Nota cuantitativa: {numeric}/20. Calificación cualitativa: {qualitative}."
    return {
        "ok": True,
        "operation": "read_private_comments",
        "count": 1,
        "comments": [{
            "text": text,
            "markers": ["nota cuantitativa", "calificacion cualitativa"],
            "structuredFeedback": True,
            "timestamp": None,
            "domOrder": 0,
        }],
        "private_section_verified": True,
        "bounded_private_region_verified": True,
        "student_scope_verified": True,
        "teacher_account_verified": True,
        "scope_evidence": "private_label_and_composer",
        "comment_order": "document_order",
        "method": "dom-v0.8.6-read",
        "url": url,
    }


@pytest.mark.parametrize(
    ("text", "numeric", "qualitative"),
    [
        ("Nota cuantitativa: 20/20. Calificación cualitativa: A.", 20, "A"),
        ("B - 14 puntos", 14, "B"),
        ("Nota cuantitativa: 17/20.", 17, "A"),
    ],
)
def test_v084_extracts_agreed_abc_grade_formats(text, numeric, qualitative):
    out = server._extract_private_comment_grade(text)
    assert out["ok"] is True
    assert out["numeric"] == numeric
    assert out["qualitative"] == qualitative


def test_v084_blocks_numeric_qualitative_mismatch():
    out = server._extract_private_comment_grade(
        "Nota cuantitativa: 14/20. Calificación cualitativa: A."
    )
    assert out["ok"] is False
    assert out["reason"] == "numeric_qualitative_mismatch"


def test_v084_ignores_unlabelled_exercise_numbers_and_selects_latest_grade():
    comments = [
        {"text": "Página 408, ejercicios 1, 2 y 3.", "domOrder": 0},
        {"text": "Nota cuantitativa: 17/20. Calificación cualitativa: A.", "domOrder": 1,
         "timestamp": "2026-08-20T12:00:00Z"},
        {"text": "Nota cuantitativa: 14/20. Calificación cualitativa: B.", "domOrder": 2,
         "timestamp": "2026-08-21T12:00:00Z"},
    ]
    out = server._select_latest_private_comment_grade(comments)
    assert out["ok"] is True
    assert len(out["events"]) == 2
    assert out["selected"]["numeric"] == 14
    assert out["selected"]["qualitative"] == "B"
    assert out["selection_basis"] == "latest_verified_timestamp"


def test_v084_multiple_grade_comments_without_timestamps_are_ambiguous():
    out = server._select_latest_private_comment_grade([
        {"text": "Nota cuantitativa: 17/20. Calificación cualitativa: A."},
        {"text": "Nota cuantitativa: 14/20. Calificación cualitativa: B."},
    ])
    assert out["ok"] is False
    assert out["reason"] == "multiple_grade_comments_without_verified_chronology"


def multi_summary():
    headers = [701, 702]
    students = []
    for index, code in enumerate(("A001", "A002"), start=1):
        students.append({
            "idPersona": 100 + index,
            "alucod": code,
            "nemo": "2A",
            "notas": {
                str(header): {
                    "idNota": header * 10 + index,
                    "nivelEva": 3,
                    "notaReg": "",
                    "tokenCelda": f"{header}-{code}",
                }
                for header in headers
            },
        })
    return {
        "class": {"ano": "2026", "cursocod": "05", "arrNGS": []},
        "criteria": [{"id": header, "nivelEva": 3} for header in headers],
        "students": students,
    }


class MultiSaveFake(SieWebClient):
    def __init__(self):
        super().__init__()
        self.summary = multi_summary()
        self.update_calls = []

    def get_gradebook_summary(self, **kwargs):
        return deepcopy(self.summary)

    def update_grades(self, **kwargs):
        records = deepcopy(kwargs["records"])
        self.update_calls.append(records)
        by_note = {}
        for student in self.summary["students"]:
            for note in student["notas"].values():
                by_note[note["idNota"]] = note
        for record in records:
            by_note[record["idNota"]]["notaReg"] = record["notaNue"]
        return {"update": {"json": {"estado": 1}}, "notification": None}


def test_v084_multi_performance_save_uses_one_put_and_verifies_every_cell():
    client = MultiSaveFake()
    out = client.save_grades_multi_verified(
        year="2026",
        course_code="05",
        class_period_id=10,
        root_content_id=20,
        period=2,
        section_ng=[],
        header_ids=[701, 702],
        grades_by_student_code={"A001": "A", "A002": "B"},
        notify=False,
    )
    assert out["saved"] is True
    assert out["single_update_request"] is True
    assert len(client.update_calls) == 1
    assert len(client.update_calls[0]) == 4
    assert out["verification"]["verified_cells"] == 4


def test_v084_multi_performance_save_blocks_level_of_achievement_before_put():
    client = MultiSaveFake()
    client.summary["criteria"][1]["nivelEva"] = 2
    with pytest.raises(SieWebError, match="PROTECCIÓN NIVEL DE LOGRO"):
        client.save_grades_multi_verified(
            year="2026", course_code="05", class_period_id=10,
            root_content_id=20, period=2, section_ng=[],
            header_ids=[701, 702],
            grades_by_student_code={"A001": "A"}, notify=False,
        )
    assert client.update_calls == []


def test_v084_multi_performance_save_rejects_non_abc_values():
    client = MultiSaveFake()
    with pytest.raises(SieWebError, match="solo admite A, B o C"):
        client.save_grades_multi_verified(
            year="2026", course_code="05", class_period_id=10,
            root_content_id=20, period=2, section_ng=[], header_ids=[701],
            grades_by_student_code={"A001": "AD"}, notify=False,
        )
    assert client.update_calls == []


def test_v084_gradebook_extra_params_cannot_redirect_the_destination(monkeypatch):
    client = SieWebClient()
    calls = []
    monkeypatch.setattr(client, "_request", lambda *args, **kwargs: calls.append((args, kwargs)))
    with pytest.raises(SieWebError, match="PROTECCIÓN DE CONTEXTO SIEWEB"):
        client.get_gradebook(
            class_period_id=6305,
            root_content_id=119598,
            extra_params={"idClasePeriodo": 9999},
        )
    assert calls == []


def test_v084_criteria_extra_params_cannot_redirect_the_destination(monkeypatch):
    client = SieWebClient()
    calls = []
    monkeypatch.setattr(client, "_request", lambda *args, **kwargs: calls.append((args, kwargs)))
    with pytest.raises(SieWebError, match="PROTECCIÓN DE CONTEXTO SIEWEB"):
        client.get_criteria(
            class_id=2030,
            class_period_id=6305,
            root_content_id=119598,
            id_ambito=518,
            extra_params={"CURSOCOD": "05", "idClase": 9999},
        )
    assert calls == []


def test_v084_grouped_low_level_grade_write_is_disabled():
    out = json.loads(server.sieweb_academics(
        "update_grades",
        json.dumps({
            "year": "2026", "course_code": "05", "class_period_id": 30,
            "period": 2, "section_ng": [], "records": [{"notaNue": "A"}],
        }),
        confirmed=True,
    ))
    assert out["blocked"] is True
    assert out["nivel_de_logro_protected"] is True


class WorkflowClassroomFake:
    def list_students(self, course_id):
        return [
            {"userId": "u1", "email": "A001@school.edu", "name": "Uno"},
            {"userId": "u2", "email": "A002@school.edu", "name": "Dos"},
        ]

    def list_submissions(self, course_id, work_id):
        return [
            {"id": "s1", "userId": "u1", "assignedGrade": 14,
             "alternateLink": "https://classroom.google.com/c/c1/a/w1/student/s1"},
            {"id": "s2", "userId": "u2", "assignedGrade": 17,
             "alternateLink": "https://classroom.google.com/c/c1/a/w1/student/s2"},
        ]


class WorkflowSieWebFake:
    def __init__(self):
        self.saved = []

    def resolve_class_context(self, **kwargs):
        return {
            "idClase": 20, "idClasePeriodo": 30, "idContenido": 40,
            "idAmbito": 50, "idPeriodoAnt": 29, "nomSalon": "2A",
        }

    def get_gradebook_summary(self, **kwargs):
        return {
            "class": {"ano": "2026", "cursocod": "05", "arrNGS": []},
            "criteria": [
                {"id": 701, "nivelEva": 3, "descripcion": "Desempeño uno"},
                {"id": 702, "nivelEva": 3, "descripcion": "Desempeño dos"},
            ],
        }

    def assert_performance_target(self, summary, *, header_id, performance_level):
        matches = [row for row in summary["criteria"] if row["id"] == header_id]
        if len(matches) != 1 or matches[0]["nivelEva"] != performance_level:
            raise SieWebError("target inválido")
        return matches[0]

    def save_grades_multi_verified(self, **kwargs):
        self.saved.append(deepcopy(kwargs))
        return {"saved": True, "single_update_request": True}


def queue_two_scoped_reads():
    queue = ClassroomBridgeQueue()
    for submission_id, numeric, qualitative in (("s1", 14, "B"), ("s2", 17, "A")):
        url = f"https://classroom.google.com/c/c1/a/w1/student/{submission_id}"
        job = queue.enqueue(
            course_id="c1", course_work_id="w1", submission_id=submission_id,
            submission_url=url, operation="read_private_comments",
        )
        queue.mark_completed(job.id, bridge_result=scoped_read(url, numeric, qualitative))
    return queue


def workflow_payload(**overrides):
    payload = {
        "course_id": "c1", "course_work_id": "w1", "section": "2A",
        "period": 2, "course_code": "05", "header_ids": [701],
    }
    payload.update(overrides)
    return payload


def test_v084_private_comment_workflow_previews_abc_without_writing(monkeypatch):
    fake_sieweb = WorkflowSieWebFake()
    monkeypatch.setattr(server, "classroom", WorkflowClassroomFake())
    monkeypatch.setattr(server, "sieweb", fake_sieweb)
    monkeypatch.setattr(server, "bridge_queue", queue_two_scoped_reads())
    out = json.loads(server.workflow_private_comment_grades_to_sieweb(workflow_payload()))
    assert out["requires_confirmation"] is True
    assert out["preview"]["grades"] == {"A001": "B", "A002": "A"}
    assert out["preview"]["blocked"] is False
    assert out["preview"]["write_shape"]["cell_count"] == 2
    assert fake_sieweb.saved == []


def test_v084_private_comment_workflow_never_copies_one_grade_to_many_columns_implicitly(monkeypatch):
    monkeypatch.setattr(server, "classroom", WorkflowClassroomFake())
    monkeypatch.setattr(server, "sieweb", WorkflowSieWebFake())
    monkeypatch.setattr(server, "bridge_queue", queue_two_scoped_reads())
    out = json.loads(server.workflow_private_comment_grades_to_sieweb(
        workflow_payload(header_ids=[701, 702])
    ))
    reasons = {item["reason"] for item in out["preview"]["blockers"]}
    assert "one_grade_source_cannot_be_copied_to_multiple_performances_implicitly" in reasons
    assert out["preview"]["blocked"] is True


def test_v084_private_comment_workflow_confirmed_uses_safe_multi_save(monkeypatch):
    fake_sieweb = WorkflowSieWebFake()
    monkeypatch.setattr(server, "classroom", WorkflowClassroomFake())
    monkeypatch.setattr(server, "sieweb", fake_sieweb)
    monkeypatch.setattr(server, "bridge_queue", queue_two_scoped_reads())
    out = json.loads(server.workflow_private_comment_grades_to_sieweb(
        workflow_payload(header_ids=[701, 702], replicate_single_grade_to_all=True, confirmed=True)
    ))
    assert out["result"]["saved"] is True
    assert len(fake_sieweb.saved) == 1
    sent = fake_sieweb.saved[0]
    assert sent["header_ids"] == [701, 702]
    assert sent["grades_by_student_code"] == {"A001": "B", "A002": "A"}
    assert sent["notify"] is False
    assert sent["performance_level"] == 3


def test_v084_private_comment_workflow_blocks_duplicate_institutional_code(monkeypatch):
    classroom_fake = WorkflowClassroomFake()
    classroom_fake.list_students = lambda course_id: [
        {"userId": "u1", "email": "A001@school.edu", "name": "Uno"},
        {"userId": "u2", "email": "A001@school.edu", "name": "Dos"},
    ]
    monkeypatch.setattr(server, "classroom", classroom_fake)
    monkeypatch.setattr(server, "sieweb", WorkflowSieWebFake())
    monkeypatch.setattr(server, "bridge_queue", queue_two_scoped_reads())
    out = json.loads(server.workflow_private_comment_grades_to_sieweb(workflow_payload()))
    reasons = {item["reason"] for item in out["preview"]["blockers"]}
    assert "duplicate_institutional_code_across_classroom_users" in reasons
    assert out["preview"]["blocked"] is True


def test_v084_private_comment_workflow_blocks_assigned_grade_without_comment_grade(monkeypatch):
    queue = queue_two_scoped_reads()
    s1_job = queue.matching(
        course_id="c1", course_work_id="w1", submission_id="s1",
        operation="read_private_comments", statuses={"completed"},
    )[0]
    s1_job.bridge_result = scoped_read(s1_job.submission_url, 14, "B")
    s1_job.bridge_result["comments"] = []
    s1_job.bridge_result["count"] = 0
    monkeypatch.setattr(server, "classroom", WorkflowClassroomFake())
    monkeypatch.setattr(server, "sieweb", WorkflowSieWebFake())
    monkeypatch.setattr(server, "bridge_queue", queue)
    out = json.loads(server.workflow_private_comment_grades_to_sieweb(workflow_payload()))
    reasons = {item["reason"] for item in out["preview"]["blockers"]}
    assert "assigned_grade_without_private_comment_grade" in reasons
    assert out["preview"]["blocked"] is True
