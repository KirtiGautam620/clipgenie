"""Saving storyboards on this computer: one folder per storyboard under data/storyboards/.

Each folder holds the cleaned photo (photo.jpg, no hidden camera or location data) and project.json.
Nothing leaves the computer.
"""
import json
import shutil
import uuid
from datetime import datetime, timezone
from pathlib import Path

from app import jobs
from app.config import DATA_DIR
from app.photostory import ingest
from app.storyboard import model, planner

ROOT = DATA_DIR / "storyboards"          # tests point this somewhere temporary
MAX_UPLOAD = 25 * 1024 * 1024            # bytes


class UnknownStoryboard(LookupError):
    """The id is malformed or has no folder."""


def _now() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%S")


def folder(sid: str) -> Path:
    # Only ids we made ourselves are accepted, so a request can never reach other folders.
    if not isinstance(sid, str) or not model.STORYBOARD_ID.fullmatch(sid):
        raise UnknownStoryboard(sid)
    return ROOT / sid


def photo_path(sid: str) -> Path:
    path = folder(sid) / "photo.jpg"
    if not path.exists():
        raise UnknownStoryboard(sid)
    return path


def save(sb: model.Storyboard) -> model.Storyboard:
    sb.updated = _now()
    sb.created = sb.created or sb.updated
    jobs.write_atomic(folder(sb.id) / "project.json", json.dumps(model.to_dict(sb), ensure_ascii=False))
    return sb


def load(sid: str) -> model.Storyboard:
    path = folder(sid) / "project.json"
    if not path.exists():
        raise UnknownStoryboard(sid)
    return model.parse(json.loads(path.read_text()))


def create(data: bytes, *, title: str = "", prompt: str = "", product: str = "", style: str | None = None,
           count: int | None = None, aspect: str = "9:16", rights: str = "unsure",
           people: str = "none") -> model.Storyboard:
    """Take in a photo, plan the scenes, and save. Raises ValueError (nothing is left behind)."""
    plan = planner.plan(prompt, product=product, style=style, count=count, aspect=aspect)   # checks the inputs first
    sid = uuid.uuid4().hex[:12]
    where = folder(sid)
    where.mkdir(parents=True)
    try:
        report = ingest.normalize_image(data, where / "photo.jpg")
        sb = model.parse({
            "id": sid, "title": (title.strip() or prompt.strip()[:60] or "Storyboard"), "aspect": aspect,
            "style": plan["style"], "product": product, "prompt": prompt, "rights": rights, "people": people,
            "scenes": plan["scenes"], "plan": {"understood": plan["understood"], "notes": plan["notes"]}},
            photo={"file": "photo.jpg", "width": report["width"], "height": report["height"]})
        return save(sb)
    except Exception:
        shutil.rmtree(where, ignore_errors=True)
        raise


def replan(sb: model.Storyboard, *, prompt: str, product: str, style: str | None, count: int | None,
           aspect: str) -> model.Storyboard:
    """New scenes from a new prompt. The photo, title and the rights answers are kept."""
    plan = planner.plan(prompt, product=product, style=style, count=count, aspect=aspect)
    raw = model.to_dict(sb)
    raw.update(prompt=prompt, product=product, aspect=aspect, style=plan["style"], scenes=plan["scenes"],
               plan={"understood": plan["understood"], "notes": plan["notes"]})
    return save(model.parse(raw, photo=sb.photo))


def list_all() -> list[dict]:
    out = []
    if ROOT.exists():
        for f in ROOT.iterdir():
            if f.is_dir() and model.STORYBOARD_ID.fullmatch(f.name) and (f / "project.json").exists():
                try:
                    sb = load(f.name)
                except (ValueError, OSError):        # a damaged project must not hide the others
                    continue
                out.append({"id": sb.id, "title": sb.title, "updated": sb.updated, "scenes": len(sb.scenes),
                            "aspect": sb.aspect})
    return sorted(out, key=lambda x: x["updated"], reverse=True)


def delete(sid: str) -> None:
    where = folder(sid)
    if not where.exists():
        raise UnknownStoryboard(sid)
    shutil.rmtree(where)
