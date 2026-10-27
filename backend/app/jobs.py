"""Very small job tracker: each job is a folder with a status.json file."""
import json
import os
import re
import uuid
from pathlib import Path

from app.config import WORK_DIR

JOB_ID = re.compile(r"[0-9a-f]{10}")
RUNNING = {"uploaded", "queued", "downloading", "transcribing", "choosing", "exporting"}


class UnknownJob(LookupError):
    """The job id is malformed or has no folder."""


def create_job() -> tuple[str, Path]:
    job_id = uuid.uuid4().hex[:10]
    folder = WORK_DIR / job_id
    folder.mkdir(parents=True)
    set_status(job_id, "uploaded")
    return job_id, folder


def job_dir(job_id: str) -> Path:
    # Only ids we made ourselves are accepted, so a request can never reach other folders.
    if not JOB_ID.fullmatch(job_id):
        raise UnknownJob(job_id)
    return WORK_DIR / job_id


def write_atomic(path: Path, text: str) -> None:
    """Write a file so a reader never sees it half-written (write aside, then swap in)."""
    tmp = path.with_name(path.name + ".tmp")
    tmp.write_text(text)
    os.replace(tmp, path)


def set_status(job_id: str, status: str, **extra) -> None:
    data = {"status": status, **extra}
    write_atomic(job_dir(job_id) / "status.json", json.dumps(data, ensure_ascii=False))


def get_status(job_id: str) -> dict | None:
    path = job_dir(job_id) / "status.json"
    if not path.exists():
        return None
    return json.loads(path.read_text())


def mark_interrupted() -> int:
    """At server start: jobs that were mid-way when the server stopped can never finish."""
    count = 0
    for folder in WORK_DIR.iterdir():
        status = get_status(folder.name) if JOB_ID.fullmatch(folder.name) else None
        if status and status["status"] in RUNNING:
            set_status(folder.name, "error",
                       error="This job was interrupted because the server was restarted. "
                             "Please upload the video again.")
            count += 1
    return count
