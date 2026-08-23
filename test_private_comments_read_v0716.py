import json
import os
from pathlib import Path

import pytest

from bridge import ClassroomBridgeQueue


os.environ.setdefault("AUTH0_ISSUER", "https://tests.example.auth0.com")
os.environ.setdefault("AUTH0_AUDIENCE", "https://tests.example/api")
os.environ.setdefault("CLASSROOM_BRIDGE_SECRET", "test-bridge-secret")

import server


ROOT = Path(__file__).parent


def test_v0716_read_job_accepts_empty_comment_and_exposes_operation():
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


def test_v0716_post_job_still_rejects_empty_comment():
    queue = ClassroomBridgeQueue()
    with pytest.raises(ValueError, match="no puede estar vacío"):
        queue.enqueue(
            course_id="course",
            course_work_id="work",
            submission_id="submission",
            submission_url="https://classroom.google.com/example",
            operation="post_private_comment",
        )


def test_v0716_read_result_is_preserved_on_completion():
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


def test_v0716_extension_mirrors_and_read_message_are_present():
    root_content = (ROOT / "content.js").read_text(encoding="utf-8")
    extension_content = (ROOT / "browser_extension" / "content.js").read_text(encoding="utf-8")
    root_bridge = (ROOT / "bridge.js").read_text(encoding="utf-8")
    extension_bridge = (ROOT / "browser_extension" / "bridge.js").read_text(encoding="utf-8")
    assert root_content == extension_content
    assert root_bridge == extension_bridge
    assert "SIEROOM_READ_PRIVATE_COMMENTS" in extension_content
    assert "dom-v0.7.16-read" in extension_content
    assert 'job.operation === "read_private_comments"' in extension_bridge


def test_v0716_manifests_advertise_matching_version():
    root_manifest = json.loads((ROOT / "manifest.json").read_text(encoding="utf-8"))
    extension_manifest = json.loads(
        (ROOT / "browser_extension" / "manifest.json").read_text(encoding="utf-8")
    )
    assert root_manifest == extension_manifest
    assert root_manifest["version"] == "0.7.16"


def test_v0716_read_all_previews_every_submission(monkeypatch):
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


def test_v0716_read_all_queues_read_jobs_and_list_filters_them(monkeypatch):
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
