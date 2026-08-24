import json
import os
import asyncio
from pathlib import Path

import pytest

from bridge import ClassroomBridgeQueue


os.environ.setdefault("AUTH0_ISSUER", "https://tests.example.auth0.com")
os.environ.setdefault("AUTH0_AUDIENCE", "https://tests.example/api")
os.environ.setdefault("CLASSROOM_BRIDGE_SECRET", "test-bridge-secret")

import server


ROOT = Path(__file__).parent


def test_v0717_read_job_accepts_empty_comment_and_exposes_operation():
    queue = ClassroomBridgeQueue()
    job = queue.enqueue(
        course_id="course",
        course_work_id="work",
        submission_id="submission",
        submission_url="https://classroom.google.com/example",
        operation="read_private_comments",
    )
    public = job.public()
    assert public["operation"] == "read_private_comments"
    assert public["comment"] == ""
    assert public["status"] == "queued"


def test_v081_post_job_rejects_when_every_action_is_empty():
    queue = ClassroomBridgeQueue()
    with pytest.raises(ValueError, match="necesita comentario, nota o devolución"):
        queue.enqueue(
            course_id="course",
            course_work_id="work",
            submission_id="submission",
            submission_url="https://classroom.google.com/example",
            operation="post_private_comment",
        )


def test_v0717_read_result_is_preserved_on_completion():
    queue = ClassroomBridgeQueue()
    job = queue.enqueue(
        course_id="course",
        course_work_id="work",
        submission_id="submission",
        submission_url="https://classroom.google.com/example",
        operation="read_private_comments",
    )
    result = {
        "ok": True,
        "count": 1,
        "comments": [{"text": "Nota cuantitativa: 14. Calificación cualitativa: B."}],
    }
    completed = queue.mark_completed(job.id, bridge_result=result)
    assert completed.status == "completed"
    assert completed.bridge_result == result
    assert completed.classroom_result == {}


def test_v0717_extension_mirrors_and_read_message_are_present():
    root_content = (ROOT / "content.js").read_text(encoding="utf-8")
    extension_content = (ROOT / "browser_extension" / "content.js").read_text(encoding="utf-8")
    root_bridge = (ROOT / "bridge.js").read_text(encoding="utf-8")
    extension_bridge = (ROOT / "browser_extension" / "bridge.js").read_text(encoding="utf-8")
    assert root_content == extension_content
    assert root_bridge == extension_bridge
    assert "SIEROOM_READ_PRIVATE_COMMENTS" in extension_content
    assert "dom-v0.8.4-read" in extension_content
    assert 'job.operation === "read_private_comments"' in extension_bridge
    assert "X-SieRoom-Bridge-Capabilities" in extension_bridge
    assert "post_private_comment,read_private_comments,verified_private_comment_read_v4,student_scoped_private_comment_read,browser_grade_return,teacher_account_guard,target_submission_guard" in extension_bridge
    assert "waitTabTargetComplete" in extension_bridge
    assert "classroomTargetMatches(result?.url, forcedUrl)" in extension_bridge
    assert 'pong?.version === expectedVersion' in extension_bridge


def test_v0717_manifests_advertise_matching_version():
    root_manifest = json.loads((ROOT / "manifest.json").read_text(encoding="utf-8"))
    extension_manifest = json.loads(
        (ROOT / "browser_extension" / "manifest.json").read_text(encoding="utf-8")
    )
    assert root_manifest == extension_manifest
    assert root_manifest["version"] == "0.8.4"
    assert "scripting" in root_manifest["permissions"]


def test_v0717_read_all_previews_every_submission(monkeypatch):
    monkeypatch.setattr(server, "bridge_queue", ClassroomBridgeQueue())
    monkeypatch.setattr(
        server.classroom,
        "list_submissions",
        lambda course_id, course_work_id: [
            {"id": "s1", "alternateLink": "https://classroom.google.com/s1"},
            {"id": "s2", "alternateLink": "https://classroom.google.com/s2"},
        ],
    )
    result = json.loads(server.classroom_private_feedback(
        "read_all", course_id="c1", course_work_id="w1", confirmed=False
    ))
    assert result["requires_confirmation"] is True
    assert result["preview"]["count"] == 2
    assert result["preview"]["no_classroom_write"] is True
    assert result["preview"]["submission_ids"] == ["s1", "s2"]


def test_v0717_read_all_queues_read_jobs_and_list_filters_them(monkeypatch):
    monkeypatch.setattr(server, "bridge_queue", ClassroomBridgeQueue())
    monkeypatch.setattr(
        server.classroom,
        "list_submissions",
        lambda course_id, course_work_id: [
            {"id": "s1", "alternateLink": "https://classroom.google.com/s1"},
            {"id": "s2", "alternateLink": "https://classroom.google.com/s2"},
        ],
    )
    queued = json.loads(server.classroom_private_feedback(
        "read_all", course_id="c1", course_work_id="w1", confirmed=True
    ))
    assert queued["queued"] is True
    assert queued["count"] == 2
    assert {job["operation"] for job in queued["jobs"]} == {"read_private_comments"}

    listed = json.loads(server.classroom_private_feedback(
        "list",
        course_id="c1",
        course_work_id="w1",
        payload_json=json.dumps({"operation": "read_private_comments"}),
    ))
    assert len(listed["jobs"]) == 2
    assert {job["submission_id"] for job in listed["jobs"]} == {"s1", "s2"}


def test_v0717_old_bridge_cannot_claim_read_jobs():
    queue = ClassroomBridgeQueue()
    read_job = queue.enqueue(
        course_id="course",
        course_work_id="work",
        submission_id="read",
        submission_url="https://classroom.google.com/read",
        operation="read_private_comments",
    )
    post_job = queue.enqueue(
        course_id="course",
        course_work_id="work",
        submission_id="post",
        submission_url="https://classroom.google.com/post",
        comment="Retroalimentación",
        operation="post_private_comment",
    )
    claimed = queue.next_job(allowed_operations={"post_private_comment"})
    assert claimed.id == post_job.id
    assert read_job.status == "queued"
    assert queue.has_queued_operation("read_private_comments") is True


class _FakeBridgeRequest:
    def __init__(self, *, job_id="", body=None, capabilities="", version="0.8.4"):
        self.path_params = {"job_id": job_id}
        self._body = body or {}
        self.headers = {
            "x-sieroom-bridge-secret": "test-bridge-secret",
            "x-sieroom-bridge-capabilities": capabilities,
            "X-SieRoom-Bridge-Capabilities": capabilities,
            "X-SieRoom-Bridge-Version": version,
        }

    async def json(self):
        return self._body


def _json_response(response):
    return json.loads(response.body.decode("utf-8"))


def _valid_read(url="https://classroom.google.com/read", text=None):
    comments = []
    if text is not None:
        comments.append({
            "text": text,
            "markers": ["nota cuantitativa", "calificacion cualitativa"],
            "structuredFeedback": True,
            "timestamp": None,
            "domOrder": 0,
        })
    return {
        "ok": True,
        "operation": "read_private_comments",
        "count": len(comments),
        "comments": comments,
        "private_section_verified": True,
        "bounded_private_region_verified": True,
        "student_scope_verified": True,
        "teacher_account_verified": True,
        "scope_evidence": "private_label_and_composer",
        "comment_order": "document_order",
        "method": "dom-v0.8.4-read",
        "url": url,
    }


def test_v0717_next_endpoint_requires_read_capability(monkeypatch):
    queue = ClassroomBridgeQueue()
    queue.enqueue(
        course_id="course",
        course_work_id="work",
        submission_id="submission",
        submission_url="https://classroom.google.com/read",
        operation="read_private_comments",
    )
    monkeypatch.setattr(server, "bridge_queue", queue)
    response = asyncio.run(server.classroom_bridge_http_next(_FakeBridgeRequest()))
    payload = _json_response(response)
    assert payload["job"] is None
    assert payload["read_waiting_for_compatible_bridge"] is True
    assert queue.stats()["queued"] == 1

    response = asyncio.run(server.classroom_bridge_http_next(_FakeBridgeRequest(
        capabilities="post_private_comment,read_private_comments"
    )))
    payload = _json_response(response)
    assert payload["job"] is None
    assert payload["required_capability"] == "verified_private_comment_read_v4"
    assert queue.stats()["queued"] == 1

    response = asyncio.run(server.classroom_bridge_http_next(_FakeBridgeRequest(
        capabilities="post_private_comment,read_private_comments,verified_private_comment_read_v4"
    )))
    payload = _json_response(response)
    assert payload["job"] is None

    response = asyncio.run(server.classroom_bridge_http_next(_FakeBridgeRequest(
        capabilities=(
            "post_private_comment,read_private_comments,verified_private_comment_read_v4,"
            "student_scoped_private_comment_read"
        ),
        version="0.8.3",
    )))
    payload = _json_response(response)
    assert payload["job"] is None
    assert payload["required_version"] == "0.8.4"

    response = asyncio.run(server.classroom_bridge_http_next(_FakeBridgeRequest(
        capabilities=(
            "post_private_comment,read_private_comments,verified_private_comment_read_v4,"
            "student_scoped_private_comment_read"
        ),
    )))
    payload = _json_response(response)
    assert payload["job"]["operation"] == "read_private_comments"


def test_v0717_rejects_false_post_result_for_read_job(monkeypatch):
    queue = ClassroomBridgeQueue()
    job = queue.enqueue(
        course_id="course",
        course_work_id="work",
        submission_id="submission",
        submission_url="https://classroom.google.com/read",
        operation="read_private_comments",
    )
    queue.next_job(allowed_operations={"read_private_comments"})
    monkeypatch.setattr(server, "bridge_queue", queue)
    false_post_result = {
        "ok": True,
        "method": "dom-v0.8.0",
        "comment": {"ok": True, "skipped": True},
    }
    response = asyncio.run(server.classroom_bridge_http_complete(_FakeBridgeRequest(
        job_id=job.id, body=false_post_result
    )))
    payload = _json_response(response)
    assert response.status_code == 409
    assert payload["job"]["status"] == "failed"
    assert "bridge_incompatible_read_result" in payload["job"]["error"]


def test_v084_old_bridge_cannot_claim_post_job(monkeypatch):
    queue = ClassroomBridgeQueue()
    queue.enqueue(
        course_id="course", course_work_id="work", submission_id="submission",
        submission_url="https://classroom.google.com/read", comment="Bien",
        operation="post_private_comment",
    )
    monkeypatch.setattr(server, "bridge_queue", queue)
    caps = "post_private_comment,teacher_account_guard,target_submission_guard"
    old_response = asyncio.run(server.classroom_bridge_http_next(_FakeBridgeRequest(
        capabilities=caps, version="0.8.3"
    )))
    old_payload = _json_response(old_response)
    assert old_payload["job"] is None
    assert old_payload["post_waiting_for_compatible_bridge"] is True
    assert queue.stats()["queued"] == 1

    current_response = asyncio.run(server.classroom_bridge_http_next(_FakeBridgeRequest(
        capabilities=caps, version="0.8.4"
    )))
    assert _json_response(current_response)["job"]["operation"] == "post_private_comment"


def test_v0717_accepts_structured_read_result(monkeypatch):
    queue = ClassroomBridgeQueue()
    job = queue.enqueue(
        course_id="course",
        course_work_id="work",
        submission_id="submission",
        submission_url="https://classroom.google.com/read",
        operation="read_private_comments",
    )
    queue.next_job(allowed_operations={"read_private_comments"})
    monkeypatch.setattr(server, "bridge_queue", queue)
    read_result = _valid_read(
        "https://classroom.google.com/read?authuser=teacher@example.com",
        "Nota cuantitativa: 14. Calificación cualitativa: B.",
    )
    response = asyncio.run(server.classroom_bridge_http_complete(_FakeBridgeRequest(
        job_id=job.id, body=read_result
    )))
    payload = _json_response(response)
    assert response.status_code == 200
    assert payload["job"]["status"] == "completed"
    assert payload["job"]["bridge_result"] == read_result


@pytest.mark.parametrize(
    ("field", "value"),
    [
        ("student_scope_verified", False),
        ("bounded_private_region_verified", False),
        ("teacher_account_verified", False),
        ("comment_order", "length_order"),
    ],
)
def test_v084_rejects_read_without_full_scope_evidence(monkeypatch, field, value):
    queue = ClassroomBridgeQueue()
    job = queue.enqueue(
        course_id="course",
        course_work_id="work",
        submission_id="submission",
        submission_url="https://classroom.google.com/read",
        operation="read_private_comments",
    )
    queue.next_job(allowed_operations={"read_private_comments"})
    monkeypatch.setattr(server, "bridge_queue", queue)
    result = _valid_read(text="Nota cuantitativa: 14. Calificación cualitativa: B.")
    result[field] = value
    response = asyncio.run(server.classroom_bridge_http_complete(_FakeBridgeRequest(
        job_id=job.id, body=result
    )))
    assert response.status_code == 409
    assert _json_response(response)["job"]["status"] == "failed"


def test_v084_rejects_non_sequential_comment_order(monkeypatch):
    queue = ClassroomBridgeQueue()
    job = queue.enqueue(
        course_id="course",
        course_work_id="work",
        submission_id="submission",
        submission_url="https://classroom.google.com/read",
        operation="read_private_comments",
    )
    queue.next_job(allowed_operations={"read_private_comments"})
    monkeypatch.setattr(server, "bridge_queue", queue)
    result = _valid_read(text="Nota cuantitativa: 14. Calificación cualitativa: B.")
    result["comments"][0]["domOrder"] = 7
    response = asyncio.run(server.classroom_bridge_http_complete(_FakeBridgeRequest(
        job_id=job.id, body=result
    )))
    assert response.status_code == 409


def test_v082_rejects_classroom_navigation_as_private_comments(monkeypatch):
    queue = ClassroomBridgeQueue()
    job = queue.enqueue(
        course_id="course",
        course_work_id="work",
        submission_id="submission",
        submission_url="https://classroom.google.com/read",
        operation="read_private_comments",
    )
    queue.next_job(allowed_operations={"read_private_comments"})
    monkeypatch.setattr(server, "bridge_queue", queue)
    false_read = _valid_read()
    false_read["comments"] = [
        {"text": "Instrucciones", "markers": [], "structuredFeedback": False, "timestamp": None, "domOrder": 0},
        {"text": "Trabajo de los alumnos", "markers": [], "structuredFeedback": False, "timestamp": None, "domOrder": 1},
        {"text": "more_vert\nMás opciones", "markers": [], "structuredFeedback": False, "timestamp": None, "domOrder": 2},
    ]
    false_read["count"] = 3
    response = asyncio.run(server.classroom_bridge_http_complete(_FakeBridgeRequest(
        job_id=job.id, body=false_read
    )))
    payload = _json_response(response)
    assert response.status_code == 409
    assert payload["job"]["status"] == "failed"
    assert "bridge_incompatible_read_result" in payload["job"]["error"]


def test_v083_target_normalization_accepts_account_prefix_and_authuser():
    expected = (
        "https://classroom.google.com/c/course/a/work/submissions/"
        "by-status/and-sort-last-name/student/student-id?authuser=teacher@example.com"
    )
    actual = (
        "https://classroom.google.com/u/1/c/course/a/work/submissions/"
        "by-status/and-sort-last-name/student/student-id"
    )
    assert server._classroom_target_matches(actual, expected) is True


def test_v083_rejects_read_from_another_classroom_submission(monkeypatch):
    queue = ClassroomBridgeQueue()
    job = queue.enqueue(
        course_id="course-b",
        course_work_id="work-b",
        submission_id="submission-b",
        submission_url="https://classroom.google.com/c/course-b/a/work-b/student/submission-b",
        operation="read_private_comments",
    )
    queue.next_job(allowed_operations={"read_private_comments"})
    monkeypatch.setattr(server, "bridge_queue", queue)
    wrong_target_result = _valid_read(
        "https://classroom.google.com/c/course-a/a/work-a/student/submission-a",
        "Calificación cuantitativa: 20/20. Calificación cualitativa: A.",
    )
    response = asyncio.run(server.classroom_bridge_http_complete(_FakeBridgeRequest(
        job_id=job.id, body=wrong_target_result
    )))
    payload = _json_response(response)
    assert response.status_code == 409
    assert payload["job"]["status"] == "failed"
    assert "bridge_target_mismatch" in payload["job"]["error"]


def test_v081_grade_only_browser_job_is_allowed():
    queue = ClassroomBridgeQueue()
    job = queue.enqueue(
        course_id="course",
        course_work_id="work",
        submission_id="submission",
        submission_url="https://classroom.google.com/example",
        operation="post_private_comment",
        grade=17,
    )
    assert job.comment == ""
    assert job.grade == 17


def test_v081_teacher_email_guard_is_present_in_all_extension_surfaces():
    popup_html = (ROOT / "browser_extension" / "popup.html").read_text(encoding="utf-8")
    popup_js = (ROOT / "browser_extension" / "popup.js").read_text(encoding="utf-8")
    bridge_js = (ROOT / "browser_extension" / "bridge.js").read_text(encoding="utf-8")
    content_js = (ROOT / "browser_extension" / "content.js").read_text(encoding="utf-8")
    assert 'id="teacherEmail"' in popup_html
    assert 'chrome.storage.local.get(["endpoint", "teacherEmail", "secret"])' in popup_js
    assert 'u.searchParams.set("authuser", email)' in bridge_js
    assert "SIEROOM_CHECK_ACCOUNT" in bridge_js
    assert "SIEROOM_CHECK_ACCOUNT" in content_js
    assert "extractActiveAccountEmails" in content_js
    assert "extractEmailsFromPage" not in content_js
    assert "revealGoogleAccountMenu" not in content_js


def test_v081_server_accepts_verified_browser_grade_and_return(monkeypatch):
    queue = ClassroomBridgeQueue()
    job = queue.enqueue(
        course_id="course",
        course_work_id="work",
        submission_id="submission",
        submission_url="https://classroom.google.com/example",
        comment="Muy bien",
        grade=16,
        return_after_comment=True,
    )
    queue.next_job()
    monkeypatch.setattr(server, "bridge_queue", queue)
    browser_result = {
        "ok": True,
        "method": "dom-v0.8.4",
        "url": "https://classroom.google.com/example",
        "teacher_account_verified": True,
        "comment": {"ok": True, "alreadyPresent": False},
        "browser_followup_done": True,
        "browser_grade_applied": True,
        "browser_grade": 16,
        "browser_returned": True,
    }
    response = asyncio.run(server.classroom_bridge_http_complete(_FakeBridgeRequest(
        job_id=job.id, body=browser_result
    )))
    payload = _json_response(response)
    assert response.status_code == 200
    assert payload["job"]["status"] == "completed"
    assert payload["job"]["classroom_result"]["mode"] == "local_browser"
    assert payload["job"]["classroom_result"]["teacher_account_guard"] is True


def test_v081_server_rejects_unconfirmed_browser_grade(monkeypatch):
    queue = ClassroomBridgeQueue()
    job = queue.enqueue(
        course_id="course",
        course_work_id="work",
        submission_id="submission",
        submission_url="https://classroom.google.com/example",
        grade=16,
    )
    queue.next_job()
    monkeypatch.setattr(server, "bridge_queue", queue)
    response = asyncio.run(server.classroom_bridge_http_complete(_FakeBridgeRequest(
        job_id=job.id,
        body={
            "ok": True,
            "url": "https://classroom.google.com/example",
            "browser_followup_done": True,
            "browser_grade_applied": True,
            "browser_grade": 14,
            "browser_returned": False,
        },
    )))
    payload = _json_response(response)
    assert response.status_code == 409
    assert payload["job"]["status"] == "failed"
    assert "nota_distinta" in payload["job"]["error"]


def test_v084_read_all_reuses_active_jobs_instead_of_duplicating(monkeypatch):
    queue = ClassroomBridgeQueue()
    monkeypatch.setattr(server, "bridge_queue", queue)
    monkeypatch.setattr(
        server.classroom,
        "list_submissions",
        lambda course_id, course_work_id: [
            {"id": "s1", "alternateLink": "https://classroom.google.com/s1"},
            {"id": "s2", "alternateLink": "https://classroom.google.com/s2"},
        ],
    )
    first = json.loads(server.classroom_private_feedback(
        "read_all", course_id="c1", course_work_id="w1", confirmed=True
    ))
    second = json.loads(server.classroom_private_feedback(
        "read_all", course_id="c1", course_work_id="w1", confirmed=True
    ))
    assert first["count"] == 2
    assert second["count"] == 0
    assert second["reused_active_count"] == 2
    assert queue.stats()["queued"] == 2


def test_v084_content_never_reads_or_confirms_comments_from_document_body():
    content = (ROOT / "content.js").read_text(encoding="utf-8")
    assert "commentReadCandidates(document.body" not in content
    assert "const nodes = [container, ...container.querySelectorAll" in content
    assert "commentVisibleOutsideComposer(text, composer, container)" in content
    assert "student_scope_verified: true" in content
    assert 'comment_order: "document_order"' in content


def test_v084_bridge_has_single_tab_leader_and_process_now_does_not_cancel_active_job():
    bridge_js = (ROOT / "bridge.js").read_text(encoding="utf-8")
    popup_js = (ROOT / "popup.js").read_text(encoding="utf-8")
    queue_py = (ROOT / "bridge.py").read_text(encoding="utf-8")
    assert "async function isLeaderBridgeTab()" in bridge_js
    assert "if (busy)" in bridge_js
    assert "if (busy && force) resetGeneration += 1" not in bridge_js
    assert "Versión incompatible" in bridge_js
    assert "Versiones distintas" in popup_js
    assert 'chrome.tabs.query({ url: bridgeUrl + "*" })' in popup_js
    assert "claim_seconds: int = 300" in queue_py
