"""The list of projects (one per uploaded or imported video), newest first.

Listing only reads what each project folder already holds. `branch()` is the one writer: it starts a
NEW project from an existing one and never changes the original. Shared by the home page and the
assistant (which uses it to understand "my last video").
"""
import json
import os
import shutil
from datetime import datetime, timezone
from pathlib import Path

from app import jobs, textmode

MAX_PROJECTS = 50


def _read(path: Path) -> dict | None:
    try:
        return json.loads(path.read_text())
    except (OSError, ValueError):
        return None


def _created_at(folder: Path, meta: dict | None, provenance: dict | None) -> str:
    if meta and meta.get("created_at"):
        return meta["created_at"]
    if provenance and provenance.get("declared_at"):
        return provenance["declared_at"]
    return datetime.fromtimestamp(folder.stat().st_mtime, timezone.utc).isoformat(timespec="seconds")


def describe(job_id: str) -> dict | None:
    """One project as the page and the assistant see it, or None if the folder is not a project."""
    folder = jobs.job_dir(job_id)
    status = _read(folder / "status.json")
    if status is None:
        return None
    provenance = _read(folder / "provenance.json") or {}
    meta = _read(folder / "meta.json")
    clips = (_read(folder / "clips.json") or {}).get("clips", [])
    first = textmode.public(clips[0]) if clips else None
    return {
        "job_id": job_id,
        "status": status.get("status"),
        "title": provenance.get("title") or (first or {}).get("title") or "Untitled video",
        "source": "YouTube import" if provenance.get("url") else "Uploaded video",
        "created_at": _created_at(folder, meta, provenance),
        "has_transcript": (folder / "transcript.json").exists(),
        "clips": len(clips),
        "first_clip": {"id": first["id"], "version": first.get("version", 0)} if first else None,
    }


def list_projects(limit: int = MAX_PROJECTS) -> list[dict]:
    """Every project, newest first."""
    out = []
    root = Path(jobs.WORK_DIR)
    if not root.exists():
        return out
    for folder in root.iterdir():
        if folder.is_dir() and jobs.JOB_ID.fullmatch(folder.name):
            project = describe(folder.name)
            if project:
                out.append(project)
    out.sort(key=lambda p: p["created_at"], reverse=True)
    return out[:limit]


def latest_with_clips() -> dict | None:
    """The newest project that has finished clips (for "a thumbnail for my last video")."""
    return next((p for p in list_projects() if p["clips"] and p["status"] == "done"), None)


LINKED = ("source.mp4", "audio.wav")              # big files: shared, never written again
COPIED = ("transcript.json", "provenance.json")     # small files: copied


def branch(job_id: str) -> str:
    """A NEW project made from an existing one, for making fresh clips without touching the videos
    the original already has. The video and its audio are hard-linked (no extra disk space; neither
    file is ever written again), the transcript and the rights declaration are copied.
    Returns the new project's id."""
    src = jobs.job_dir(job_id)
    if not (src / "source.mp4").exists() or not (src / "transcript.json").exists():
        raise ValueError("That project's video or transcript is no longer on this computer.")
    new_id, folder = jobs.create_job()
    for name in LINKED:
        if (src / name).exists():
            try:
                os.link(src / name, folder / name)
            except OSError:                          # another disk, or links not allowed: copy instead
                shutil.copy2(src / name, folder / name)
    for name in COPIED:
        if (src / name).exists():
            shutil.copy2(src / name, folder / name)
    meta = json.loads((folder / "meta.json").read_text())
    jobs.write_atomic(folder / "meta.json", json.dumps({**meta, "derived_from": job_id}))
    return new_id


def latest_with_transcript() -> dict | None:
    """The newest project whose speech has been transcribed (what "my last video" means)."""
    return next((p for p in list_projects() if p["has_transcript"]), None)
