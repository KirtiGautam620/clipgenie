"""HTTP endpoints for publishing text and thumbnails of a clip (under /api/jobs/{job_id}/clips/{clip_id}).

Nothing here changes the video, so no new version is made and the checklist stays as it was.
Saving a thumbnail file still needs the checklist, the same as saving the video.
"""
import json
import time

from fastapi import APIRouter, HTTPException
from fastapi.responses import FileResponse
from pydantic import BaseModel

from app import captionstyles, jobs, manifest, pipeline, rights, textmode
from app.content import copy as clip_copy
from app.content import thumbnails
from app.llm import LLMError

api = APIRouter(prefix="/api/jobs/{job_id}/clips/{clip_id}")


def _clip(job_id: str, clip_id: int) -> dict:
    path = jobs.job_dir(job_id) / "clips.json"
    if not path.exists():
        raise HTTPException(404, "No clips yet")
    clip = next((c for c in json.loads(path.read_text())["clips"] if c["id"] == clip_id), None)
    if clip is None:
        raise HTTPException(404, "Clip not found")
    return clip


# ---------------------------------------------------------------- title, description, hashtags

def _copy_view(job_id: str, clip: dict) -> dict:
    return {"copy": clip.get("copy"), "can_draft": clip_copy.can_draft(clip),
            "credits": rights.credits_text(rights.load_source(job_id), clip),
            "limits": {"title": clip_copy.TITLE_MAX, "description": clip_copy.DESCRIPTION_MAX,
                       "hashtags": clip_copy.HASHTAGS_MAX}}


@api.get("/copy")
def get_copy(job_id: str, clip_id: int):
    return _copy_view(job_id, _clip(job_id, clip_id))


@api.post("/copy/draft")
def draft_copy(job_id: str, clip_id: int):
    """The local model suggests a title, description and hashtags from this clip's own words."""
    _clip(job_id, clip_id)
    try:
        clip = clip_copy.draft(job_id, clip_id)
    except clip_copy.Untrusted as e:
        raise HTTPException(409, str(e))
    except pipeline.Busy as e:
        raise HTTPException(409, str(e))
    except LLMError:
        raise HTTPException(503, "The local AI model isn't running, so it can't write a draft. "
                                 "Start it (see Settings), or write your own.")
    except ValueError as e:
        raise HTTPException(422, str(e))
    return _copy_view(job_id, clip)


class CopyIn(BaseModel):
    title: str
    description: str = ""
    hashtags: list[str] = []


@api.put("/copy")
def save_copy(job_id: str, clip_id: int, body: CopyIn):
    """The user's own (or edited) text. Only this approved text is copied for publishing."""
    _clip(job_id, clip_id)
    try:
        clip = clip_copy.save_user(job_id, clip_id, body.model_dump())
    except pipeline.Busy as e:
        raise HTTPException(409, str(e))
    except ValueError as e:
        raise HTTPException(400, str(e))
    return _copy_view(job_id, clip)


# ---------------------------------------------------------------- thumbnails

def _thumb_view(job_id: str, clip_id: int, clip: dict) -> dict:
    folder = thumbnails.folder_for(job_id, clip_id)
    made = {size: (folder / f"thumbnail_{size}.png").exists() for size in thumbnails.SIZES}
    info = clip.get("thumbnail") or {}
    return {"frames": thumbnails.saved_candidates(job_id, clip_id, clip.get("version", 0)), "made": made, "chosen": info,
            "suggested_text": clip_copy.headline_text(clip), "max_chars": captionstyles.HEADLINE_MAX_CHARS,
            "presets": [{"id": k, "label": v["label"]} for k, v in captionstyles.HEADLINE_PRESETS.items()],
            "stamp": info.get("made_at", 0),
            "outdated": bool(info) and info.get("version") != clip.get("version", 0), "confirmed": rights.is_confirmed(job_id, clip)}


@api.get("/thumbnails")
def get_thumbnails(job_id: str, clip_id: int):
    return _thumb_view(job_id, clip_id, _clip(job_id, clip_id))


@api.post("/thumbnails/frames")
def find_frames(job_id: str, clip_id: int):
    """Look through the clip for the best frames (sharp, well lit, a face). Takes a few seconds."""
    clip = _clip(job_id, clip_id)
    if not pipeline.heavy_job_lock.acquire(blocking=False):
        raise HTTPException(409, "ClipGenie is busy making a video. Try again in a minute.")
    try:
        thumbnails.candidates(job_id, clip_id, clip.get("version", 0))
    except ValueError as e:
        raise HTTPException(404, str(e))
    finally:
        pipeline.heavy_job_lock.release()
    return _thumb_view(job_id, clip_id, clip)


@api.get("/thumbnails/frames/{index}.jpg")
def frame_image(job_id: str, clip_id: int, index: int):
    _clip(job_id, clip_id)
    path = thumbnails.folder_for(job_id, clip_id) / f"frame_{index}.jpg"
    if not path.exists():
        raise HTTPException(404, "Frame not found")
    return FileResponse(path, media_type="image/jpeg")


class ThumbnailIn(BaseModel):
    frame: int
    text: str = ""
    preset: str = captionstyles.DEFAULT_HEADLINE_PRESET


@api.post("/thumbnails")
def make_thumbnails(job_id: str, clip_id: int, body: ThumbnailIn):
    """Both thumbnails (1080x1920 and 1280x720) from the chosen frame, with the user's text."""
    clip = _clip(job_id, clip_id)
    text = body.text.strip()
    if text and textmode.is_untrusted(clip) and text == (clip.get("withheld") or {}).get("title"):
        raise HTTPException(400, "That text came from speech that couldn't be trusted. Write your own.")
    if not pipeline.heavy_job_lock.acquire(blocking=False):
        raise HTTPException(409, "ClipGenie is busy making a video. Try again in a minute.")
    try:
        m = manifest.current(jobs.job_dir(job_id), clip)
        thumbnails.compose(job_id, clip_id, body.frame, text, body.preset, m, clip.get("version", 0))
        folder, clips_file, data, entry, _ = pipeline._load_clip(job_id, clip_id)
        entry["thumbnail"] = {"frame": body.frame, "text": text, "preset": body.preset, "made_at": int(time.time()),
                              "version": clip.get("version", 0)}
        jobs.write_atomic(clips_file, json.dumps(data, ensure_ascii=False))
    except ValueError as e:
        raise HTTPException(400, str(e))
    finally:
        pipeline.heavy_job_lock.release()
    return _thumb_view(job_id, clip_id, entry)


def _thumb_file(job_id: str, clip_id: int, size: str):
    if size not in thumbnails.SIZES:
        raise HTTPException(404, "Unknown size")
    path = thumbnails.folder_for(job_id, clip_id) / f"thumbnail_{size}.png"
    if not path.exists():
        raise HTTPException(404, "Make the thumbnail first")
    return path


@api.get("/thumbnails/{size}.png")
def thumbnail_preview(job_id: str, clip_id: int, size: str):
    _clip(job_id, clip_id)
    return FileResponse(_thumb_file(job_id, clip_id, size), media_type="image/png")


@api.get("/thumbnails/{size}/download")
def thumbnail_download(job_id: str, clip_id: int, size: str):
    """Saving a thumbnail needs the copyright checklist, the same as saving the video."""
    clip = _clip(job_id, clip_id)
    if not rights.is_confirmed(job_id, clip):
        raise HTTPException(403, "Complete the copyright checklist for this clip first.")
    return FileResponse(_thumb_file(job_id, clip_id, size), media_type="image/png",
                        filename=f"clipgenie_{job_id}_{clip_id}_thumbnail_{size}.png")
