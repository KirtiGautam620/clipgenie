import json
import re
import shutil
import urllib.request
from contextlib import asynccontextmanager

from fastapi import BackgroundTasks, FastAPI, File, Form, HTTPException, Request, UploadFile
from fastapi.responses import FileResponse, JSONResponse
from pydantic import BaseModel, Field

from app import jobs, music, rights, ytdl
from app.llm import OLLAMA_MODEL
from app.pipeline import DEFAULTS, run_clips_only, run_pipeline, set_clip_music


@asynccontextmanager
async def lifespan(app: FastAPI):
    jobs.mark_interrupted()
    yield


app = FastAPI(title="ClipGenie", lifespan=lifespan)

LANGUAGES = {"auto": None, "en": "en", "hi": "hi"}
FRAMINGS = ("crop", "blur")


@app.exception_handler(jobs.UnknownJob)
async def unknown_job(request: Request, exc: jobs.UnknownJob):
    return JSONResponse({"detail": "Unknown job"}, status_code=404)


# ------------------------------------------------------------------ health

def _ollama_state() -> dict:
    """Is Ollama running, and is our model installed? (1 second timeout)"""
    try:
        with urllib.request.urlopen("http://127.0.0.1:11434/api/tags", timeout=1) as r:
            names = [m["name"] for m in json.load(r).get("models", [])]
        return {"running": True, "model_installed": OLLAMA_MODEL in names, "model": OLLAMA_MODEL}
    except Exception:
        return {"running": False, "model_installed": False, "model": OLLAMA_MODEL}


@app.get("/api/health")
def health():
    """Tells the page what is available, so it can warn about anything missing."""
    return {"status": "ok", "ffmpeg": shutil.which("ffmpeg") is not None,
            "ollama": _ollama_state(), "music_tracks": len(music.list_tracks())}


# ------------------------------------------------------------------ starting a job

def _check_settings(min_len: float, max_len: float, count: int, framing: str) -> None:
    if not (0 < min_len <= max_len <= 180) or not (1 <= count <= 10):
        raise HTTPException(400, "Invalid min_len / max_len / count")
    if framing not in FRAMINGS:
        raise HTTPException(400, "framing must be crop or blur")


def _check_rights(value: str) -> None:
    if value not in rights.SOURCE_RIGHTS:
        raise HTTPException(400, "Please say whether you own this video or have permission to use it")


@app.post("/api/upload")
async def upload(
    background: BackgroundTasks,
    file: UploadFile = File(...),
    rights_declared: str = Form(..., alias="rights"),
    language: str = Form("auto"),
    min_len: float = Form(DEFAULTS["min_len"]),
    max_len: float = Form(DEFAULTS["max_len"]),
    count: int = Form(DEFAULTS["count"]),
    use_ai: bool = Form(DEFAULTS["use_ai"]),
    framing: str = Form(DEFAULTS["framing"]),
    music_on: bool = Form(DEFAULTS["music"]),
    music_volume: float = Form(DEFAULTS["music_volume"]),
):
    """One call does everything: transcribe, choose the best moments, edit the clips."""
    if language not in LANGUAGES:
        raise HTTPException(400, "language must be auto, en or hi")
    _check_rights(rights_declared)
    _check_settings(min_len, max_len, count, framing)
    suffix = re.sub(r"[^a-z0-9]", "", (file.filename or "").rsplit(".", 1)[-1].lower())
    if suffix != "mp4":
        raise HTTPException(400, "Please upload an MP4 file")

    job_id, folder = jobs.create_job()
    with open(folder / "source.mp4", "wb") as out:
        shutil.copyfileobj(file.file, out)  # streams to disk, safe for big files
    rights.save_source(job_id, rights_declared, title=file.filename or "")

    settings = dict(min_len=min_len, max_len=max_len, count=count, use_ai=use_ai, framing=framing,
                    music=music_on, music_volume=max(0.0, min(1.0, music_volume)))
    background.add_task(run_pipeline, job_id, LANGUAGES[language], settings)
    return {"job_id": job_id}


@app.post("/api/import-url")
def import_url(
    background: BackgroundTasks,
    url: str = Form(...),
    rights_declared: str = Form(..., alias="rights"),
    language: str = Form("auto"),
    min_len: float = Form(DEFAULTS["min_len"]),
    max_len: float = Form(DEFAULTS["max_len"]),
    count: int = Form(DEFAULTS["count"]),
    use_ai: bool = Form(DEFAULTS["use_ai"]),
    framing: str = Form(DEFAULTS["framing"]),
    music_on: bool = Form(DEFAULTS["music"]),
    music_volume: float = Form(DEFAULTS["music_volume"]),
):
    """Import a YouTube video you own or have permission to use, then run the same job."""
    if language not in LANGUAGES:
        raise HTTPException(400, "language must be auto, en or hi")
    _check_rights(rights_declared)
    if rights_declared not in rights.DOWNLOAD_OK:
        raise HTTPException(400, "A video can only be imported from a link if you own it, have "
                                 "permission, or it is public domain / licensed for reuse.")
    _check_settings(min_len, max_len, count, framing)
    try:
        clean = ytdl.check_url(url)
    except ytdl.ImportError_ as e:
        raise HTTPException(400, str(e))

    job_id, _ = jobs.create_job()
    rights.save_source(job_id, rights_declared, clean)
    settings = dict(min_len=min_len, max_len=max_len, count=count, use_ai=use_ai, framing=framing,
                    music=music_on, music_volume=max(0.0, min(1.0, music_volume)),
                    rights=rights_declared)
    background.add_task(run_pipeline, job_id, LANGUAGES[language], settings, clean)
    return {"job_id": job_id}


@app.get("/api/jobs/{job_id}")
def job_status(job_id: str):
    status = jobs.get_status(job_id)
    if status is None:
        raise HTTPException(404, "Unknown job")
    return status


@app.post("/api/jobs/{job_id}/clips")
def remake_clips(job_id: str, background: BackgroundTasks,
                 min_len: float = DEFAULTS["min_len"], max_len: float = DEFAULTS["max_len"],
                 count: int = DEFAULTS["count"], use_ai: bool = DEFAULTS["use_ai"],
                 framing: str = DEFAULTS["framing"]):
    """Make a fresh set of clips from an already-transcribed video."""
    status = jobs.get_status(job_id)
    if status is None or not (jobs.job_dir(job_id) / "transcript.json").exists():
        raise HTTPException(409, "This video has not been analysed yet")
    _check_settings(min_len, max_len, count, framing)
    settings = dict(min_len=min_len, max_len=max_len, count=count, use_ai=use_ai, framing=framing)
    background.add_task(run_clips_only, job_id, settings)
    return {"started": True}


# ------------------------------------------------------------------ clips

def _clips(job_id: str) -> dict:
    path = jobs.job_dir(job_id) / "clips.json"
    if not path.exists():
        raise HTTPException(404, "No clips yet")
    return json.loads(path.read_text())


def _clip(job_id: str, clip_id: int) -> dict:
    clip = next((c for c in _clips(job_id)["clips"] if c["id"] == clip_id), None)
    if clip is None:
        raise HTTPException(404, "Clip not found")
    return clip


@app.get("/api/jobs/{job_id}/clips")
def list_clips(job_id: str):
    data = _clips(job_id)
    source = rights.load_source(job_id)
    return {**data, "disclaimer": rights.DISCLAIMER,
            "source": {"rights": source["rights"],
                       "rights_label": rights.SOURCE_RIGHTS.get(source["rights"]),
                       "url": source.get("url"), "title": source.get("title")},
            "clips": [rights.enrich(job_id, c) for c in data["clips"]]}


def _video_path(job_id: str, clip_id: int):
    folder = jobs.job_dir(job_id)
    with_music = folder / f"clip_{clip_id}_music.mp4"
    path = with_music if with_music.exists() else folder / f"clip_{clip_id}.mp4"
    if not path.exists():
        raise HTTPException(404, "Clip not found")
    return path


@app.get("/api/jobs/{job_id}/clips/{clip_id}.mp4")
def preview_clip(job_id: str, clip_id: int):
    """For watching in the page. Saving a copy goes through /download (the checklist)."""
    return FileResponse(_video_path(job_id, clip_id), media_type="video/mp4")


class Checklist(BaseModel):
    items: list[str]


@app.post("/api/jobs/{job_id}/clips/{clip_id}/checklist")
def confirm_checklist(job_id: str, clip_id: int, body: Checklist):
    clip = _clip(job_id, clip_id)
    missing = rights.confirm(job_id, clip, body.items)
    if missing:
        raise HTTPException(400, "Please tick every box in the checklist first.")
    return rights.enrich(job_id, clip)


@app.get("/api/jobs/{job_id}/clips/{clip_id}/download")
def download_clip(job_id: str, clip_id: int):
    """The only way to get a file out. Needs the copyright checklist for this exact clip."""
    clip = _clip(job_id, clip_id)
    if not rights.is_confirmed(job_id, clip):
        raise HTTPException(403, "Complete the copyright checklist for this clip first.")
    return FileResponse(_video_path(job_id, clip_id), media_type="video/mp4",
                        filename=f"clipgenie_{job_id}_{clip_id}.mp4")


@app.get("/api/jobs/{job_id}/clips/{clip_id}/report")
def clip_report(job_id: str, clip_id: int):
    """A record of the source, music licence and confirmations, to keep with your files."""
    report = rights.report(job_id, _clip(job_id, clip_id))
    return JSONResponse(report, headers={
        "Content-Disposition": f'attachment; filename="clipgenie_{job_id}_{clip_id}_rights.json"'})


class MusicChoice(BaseModel):
    track_id: str | None = None          # None = no music
    volume: float = Field(DEFAULTS["music_volume"], ge=0, le=1)


@app.post("/api/jobs/{job_id}/clips/{clip_id}/music")
def change_clip_music(job_id: str, clip_id: int, choice: MusicChoice):
    """Pick another track, change the volume, or remove the music. Only audio is re-mixed.
    A new mix is a new version of the clip, so its checklist must be confirmed again."""
    _clips(job_id)
    try:
        return rights.enrich(job_id, set_clip_music(job_id, clip_id, choice.track_id, choice.volume))
    except KeyError as e:
        raise HTTPException(404, str(e.args[0]))
    except RuntimeError as e:
        raise HTTPException(500, str(e))


# ------------------------------------------------------------------ music library

@app.get("/api/music")
def music_library():
    return {"tracks": music.list_tracks(), "licenses": music.LICENSES, "moods": music.MOODS}


@app.get("/api/music/{track_id}/preview")
def music_preview(track_id: str):
    track = music.get_track(track_id)
    if track is None:
        raise HTTPException(404, "Unknown track")
    return FileResponse(music.track_path(track))


@app.post("/api/music")
async def add_music(
    file: UploadFile = File(...),
    title: str = Form(""),
    moods: str = Form("other"),                 # comma-separated
    license: str = Form("unknown"),
    attribution: str = Form(""),
    source: str = Form(""),
):
    """Add a track you have the right to use. Its licence is saved with it."""
    try:
        return music.add_track(await file.read(), file.filename or "track.mp3", title,
                               [m.strip() for m in moods.split(",")], license, attribution, source)
    except ValueError as e:
        raise HTTPException(400, str(e))
