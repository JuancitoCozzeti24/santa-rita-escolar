from __future__ import annotations

from typing import Any


def enqueue_once(classroom: Any, bridge_queue: Any) -> dict[str, Any]:
    """Abre SOLO la entrega de Sebastián Corado en modo lectura.

    No escribe comentario, no cambia nota y no devuelve la entrega. El objetivo
    es comprobar desde la interfaz real de Classroom si existe evidencia visible
    que la API no está reportando en attachments[].
    """
    course_id = "794101896009"
    course_work_id = "874691341801"
    submission_id = "Cg4I0tmfxJoTEOnbqr26GQ"
    submission_url = (
        "https://classroom.google.com/c/Nzk0MTAxODk2MDA5/a/ODc0NjkxMzQxODAx/"
        "submissions/by-status/and-sort-last-name/student/NjU5OTU3NDc2NTYy"
    )

    existing = bridge_queue.matching(
        course_id=course_id,
        course_work_id=course_work_id,
        submission_id=submission_id,
        operation="read_private_comments",
        statuses={"queued", "claimed"},
    )
    if existing:
        job = existing[0]
        print(f"SEBASTIAN_PROBE_EXISTS: job={job.id} status={job.status}", flush=True)
        return {
            "queued": False,
            "job_id": job.id,
            "course_name": "MATE 5TO - B",
            "student_name": "Sebastian CORADO RIOFRIO",
        }

    job = bridge_queue.enqueue(
        course_id=course_id,
        course_work_id=course_work_id,
        submission_id=submission_id,
        submission_url=submission_url,
        operation="read_private_comments",
    )
    print(f"SEBASTIAN_PROBE_ENQUEUED: job={job.id}", flush=True)
    return {
        "queued": True,
        "job_id": job.id,
        "course_name": "MATE 5TO - B",
        "student_name": "Sebastian CORADO RIOFRIO",
    }
