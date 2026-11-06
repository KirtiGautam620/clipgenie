"""Very small job tracker: each job is a folder with a status.json file."""
import json
import os
import re
import time
import uuid
from datetime import datetime, timezone
from pathlib import Path

from app.config import WORK_DIR

JOB_ID = re.compile(r"[0-9a-f]{10}")
RUNNING = {"uploaded", "queued", "downloading", "transcribing", "choosing", "exporting"}
# "waiting" (a video attached in the chat, not started yet) is deliberately NOT running: it survives a restart


LOCAL_OWNER = "local"      # until there are accounts, every project belongs to the one local user


class UnknownJob(LookupError):
    """The job id is malformed or has no folder."""


def create_job() -> tuple[str, Path]:
    job_id = uuid.uuid4().hex[:10]
    folder = WORK_DIR / job_id
    folder.mkdir(parents=True)
    set_status(job_id, "uploaded")
    write_atomic(folder / "meta.json", json.dumps({
        "owner_id": LOCAL_OWNER, "created_at": datetime.now(timezone.utc).isoformat(timespec="seconds")}))
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


def owner_of(job_id: str) -> str:
    """Who owns this project. Projects made before owners existed belong to the local user."""
    path = job_dir(job_id) / "meta.json"
    try:
        return json.loads(path.read_text()).get("owner_id", LOCAL_OWNER)
    except (OSError, ValueError):
        return LOCAL_OWNER


def record_usage(job_id: str, kind: str, seconds: float, **detail) -> None:
    """Append one line to the project's usage log (what ran, for how long). The groundwork for
    plans and limits later; it never stops real work, so any failure is ignored."""
    try:
        line = json.dumps({"at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
                           "owner_id": owner_of(job_id), "kind": kind,
                           "seconds": round(seconds, 2), **detail}, ensure_ascii=False)
        with open(job_dir(job_id) / "usage.jsonl", "a") as f:
            f.write(line + "\n")
    except Exception:
        pass


class timed:
    """`with jobs.timed(job_id, "render", clip=3):` records how long the block took."""
    def __init__(self, job_id: str, kind: str, **detail):
        self.job_id, self.kind, self.detail = job_id, kind, detail

    def __enter__(self):
        self.t0 = time.monotonic()
        return self

    def __exit__(self, *exc):
        record_usage(self.job_id, self.kind, time.monotonic() - self.t0, ok=exc[0] is None, **self.detail)
        return False
