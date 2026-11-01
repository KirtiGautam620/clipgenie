"""The Storyboard API. A separate router: it adds routes under /api/storyboards and touches none of
the Shorts routes."""
import functools
from types import SimpleNamespace

from fastapi import APIRouter, BackgroundTasks, Body, File, Form, HTTPException, Request, UploadFile
from fastapi.responses import JSONResponse, PlainTextResponse, Response
from fastapi.responses import FileResponse
from PIL import Image

from app import music
from app.photostory.manifest import PEOPLE, RIGHTS, _choice, _number
from app.storyboard import animatic, frames, model, package, planner, prompts, store
from app.storyboard.shots import ASPECTS, MOTIONS, SHOTS, STYLE_INFO, STYLES, TRANSITIONS

router = APIRouter()

RIGHTS_LABELS = {"own": "I took this photo or I own it", "permission": "I have the owner's permission",
                 "licensed": "It is licensed for this use", "public_domain": "It is in the public domain",
                 "unsure": "I am not sure yet"}
PEOPLE_LABELS = {"none": "No identifiable people", "consent": "People appear and have agreed",
                 "no_consent": "People appear and have not agreed"}


def _payload(sb: model.Storyboard) -> dict:
    """The storyboard plus what the page needs: preview geometry for each scene and any blockers."""
    data = model.to_dict(sb)
    data["geometry"] = {s.id: frames.geometry(sb.photo["width"], sb.photo["height"], sb.aspect, s)
                        for s in sb.scenes}
    data["blockers"] = model.export_blockers(sb)
    return data


def _load(sid: str) -> model.Storyboard:
    try:
        return store.load(sid)
    except store.UnknownStoryboard:
        raise HTTPException(404, "Unknown storyboard")


def _count(value: str) -> int | None:
    if value in ("", None):
        return None
    try:
        return int(value)
    except ValueError:
        raise HTTPException(400, "The number of scenes must be a whole number.")


@router.get("/api/storyboard-options")
def options():
    """What the page may offer: styles, shots, motions and the limits."""
    return {
        "styles": [{"id": s.id, "label": s.label, "phrase": s.phrase} for s in STYLE_INFO.values()],
        "shots": [{"id": s.id, "label": s.label, "camera": s.camera, "detail": s.detail, "zoom": s.zoom,
                   "focus": list(s.focus), "motion": s.motion, "intensity": s.intensity, "duration": s.duration}
                  for s in SHOTS.values()],
        "motions": list(MOTIONS), "transitions": list(TRANSITIONS), "aspects": list(ASPECTS),
        "rights": [{"id": r, "label": RIGHTS_LABELS[r]} for r in RIGHTS],
        "people": [{"id": p, "label": PEOPLE_LABELS[p]} for p in PEOPLE],
        "limits": {"scenes": [planner.MIN_SCENES, planner.MAX_SCENES], "saved_scenes": [1, model.MAX_SCENES_SAVED],
                   "duration": list(model.DURATION), "zoom": list(model.ZOOM), "prompt": model.PROMPT_MAX,
                   "scene_prompt": model.SCENE_PROMPT_MAX, "upload_mb": store.MAX_UPLOAD // (1024 * 1024)}}


@router.get("/api/storyboards")
def list_storyboards():
    return {"storyboards": store.list_all()}


@router.post("/api/storyboards")
async def create_storyboard(
    photo: UploadFile = File(...), prompt: str = Form(""), product: str = Form(""), title: str = Form(""),
    style: str = Form(""), count: str = Form(""), aspect: str = Form("9:16"),
    rights: str = Form("unsure"), people: str = Form("none"),
):
    """Upload one photo with a prompt: the photo is checked and cleaned, and a shot plan is made."""
    data = await photo.read(store.MAX_UPLOAD + 1)
    if len(data) > store.MAX_UPLOAD:
        raise HTTPException(413, f"This photo is larger than {store.MAX_UPLOAD // (1024 * 1024)} MB.")
    try:
        sb = store.create(data, title=title, prompt=prompt, product=product, style=style or None,
                          count=_count(count), aspect=aspect, rights=rights, people=people)
    except ValueError as e:
        raise HTTPException(400, str(e))
    return _payload(sb)


@router.get("/api/storyboards/{sid}")
def get_storyboard(sid: str):
    return _payload(_load(sid))


@router.put("/api/storyboards/{sid}")
def save_storyboard(sid: str, body: dict = Body(...)):
    """Save the page's edits. The photo facts and the planner's notes stay as the server has them."""
    current = _load(sid)
    body = {**body, "id": sid, "created": current.created, "plan": current.plan}
    try:
        sb = model.parse(body, photo=current.photo)
    except ValueError as e:
        raise HTTPException(400, str(e))
    if sb.music["track_id"] and music.get_track(sb.music["track_id"]) is None:
        raise HTTPException(400, "That music track is not in your library.")
    return _payload(store.save(sb))


@router.post("/api/storyboards/{sid}/plan")
def replan_storyboard(sid: str, body: dict = Body(...)):
    """Make a new shot plan from a new prompt. This replaces the scenes (the page asks first)."""
    current = _load(sid)
    try:
        sb = store.replan(current, prompt=str(body.get("prompt", "")), product=str(body.get("product", "")),
                          style=body.get("style") or None, count=_count(str(body.get("count") or "")),
                          aspect=body.get("aspect") or current.aspect)
    except ValueError as e:
        raise HTTPException(400, str(e))
    return _payload(sb)


@router.post("/api/storyboards/{sid}/compose-prompt")
def compose_prompt(sid: str, body: dict = Body(...)):
    """Rebuild one scene's prompt from its fields (what the page shows before saving)."""
    sb = _load(sid)
    try:
        text = prompts.compose_scene(
            camera=str(body.get("camera", "")), detail=str(body.get("detail", "")),
            duration=_number(body.get("duration"), "Duration", *model.DURATION),
            product=str(body.get("product", sb.product)), style=_choice(body.get("style", sb.style), "Style", STYLES),
            aspect=_choice(body.get("aspect", sb.aspect), "Aspect", ASPECTS))
    except ValueError as e:
        raise HTTPException(400, str(e))
    return {"prompt": text}


@functools.lru_cache(maxsize=2)
def _decoded(path: str, mtime_ns: int) -> Image.Image:
    img = Image.open(path)
    img.load()
    return img


def _scene_from_query(request: Request) -> SimpleNamespace:
    q = request.query_params
    try:
        return SimpleNamespace(
            zoom=_number(float(q.get("zoom", 1)), "zoom", *model.ZOOM),
            intensity=_number(float(q.get("intensity", 0.5)), "intensity", 0, 1),
            motion=_choice(q.get("motion", "hold"), "motion", MOTIONS),
            focus=(_number(float(q.get("fx", 0.5)), "focus", 0, 1), _number(float(q.get("fy", 0.5)), "focus", 0, 1)))
    except ValueError as e:
        raise HTTPException(400, str(e))


@router.get("/api/storyboards/{sid}/geometry")
def scene_geometry(sid: str, request: Request):
    """Where a scene's movement begins and ends on the photo, and how sharp it will be (for live editing)."""
    sb = _load(sid)
    return frames.geometry(sb.photo["width"], sb.photo["height"], sb.aspect, _scene_from_query(request))


@router.get("/api/storyboards/{sid}/frame.jpg")
def frame(sid: str, request: Request):
    """A preview frame of the user's own photo for the start or end of a scene."""
    sb = _load(sid)
    scene = _scene_from_query(request)
    which = request.query_params.get("which", "start")
    if which not in ("start", "end"):
        raise HTTPException(400, "which must be start or end.")
    try:
        long_side = int(request.query_params.get("w", 480))
    except ValueError:
        raise HTTPException(400, "w must be a whole number.")
    if not 64 <= long_side <= 1600:
        raise HTTPException(400, "w must be between 64 and 1600.")
    path = store.photo_path(sid)
    photo = _decoded(str(path), path.stat().st_mtime_ns)
    start, end = frames.boxes(sb.photo["width"], sb.photo["height"], sb.aspect, scene)
    return Response(frames.render(photo, start if which == "start" else end, sb.aspect, long_side),
                    media_type="image/jpeg", headers={"Cache-Control": "no-store"})


@router.get("/api/storyboards/{sid}/photo.jpg")
def photo(sid: str):
    _load(sid)
    return FileResponse(store.photo_path(sid), media_type="image/jpeg", headers={"Cache-Control": "no-store"})


def _check_export(sb: model.Storyboard) -> None:
    blockers = model.export_blockers(sb)
    if blockers:
        raise HTTPException(409, " ".join(blockers))


@router.get("/api/storyboards/{sid}/prompts.txt")
def prompts_txt(sid: str):
    sb = _load(sid)
    _check_export(sb)
    return PlainTextResponse(prompts.prompts_text(sb.title, sb.aspect, model.to_dict(sb)["scenes"]))


@router.get("/api/storyboards/{sid}/package.zip")
def package_zip(sid: str):
    sb = _load(sid)
    _check_export(sb)
    data = package.build(sb, store.photo_path(sid))
    return Response(data, media_type="application/zip",
                    headers={"Content-Disposition": f'attachment; filename="storyboard_{sid}.zip"'})


@router.get("/api/storyboards/{sid}/animatic")
def animatic_status(sid: str):
    """The latest animatic render: not started, rendering (with progress), done, cancelled or failed.
    A finished one says whether the storyboard has changed since."""
    return animatic.status(_load(sid))


@router.post("/api/storyboards/{sid}/animatic")
def animatic_start(sid: str, background: BackgroundTasks, body: dict = Body(default={})):
    """Start making the animatic (a video of the photo moving) from the SAVED storyboard."""
    sb = _load(sid)
    try:
        run = animatic.start(sid, body.get("quality", "preview"))
    except ValueError as e:
        raise HTTPException(400, str(e))
    except animatic.Busy as e:
        raise HTTPException(409, str(e))
    background.add_task(run)
    return animatic.status(sb)


@router.post("/api/storyboards/{sid}/animatic/cancel")
def animatic_cancel(sid: str):
    sb = _load(sid)
    animatic.cancel(sid)
    return animatic.status(sb)


@router.get("/api/storyboards/{sid}/animatic.mp4")
def animatic_video(sid: str, download: int = 0):
    """The finished animatic. Watching it in the page is always allowed; downloading follows the same
    rights and consent rule as the package."""
    sb = _load(sid)
    path = store.folder(sid) / animatic.OUTPUT
    if not path.exists():
        raise HTTPException(404, "There is no animatic yet.")
    headers = {"Cache-Control": "no-store"}
    if download:
        _check_export(sb)
        return FileResponse(path, media_type="video/mp4", headers=headers, filename=f"animatic_{sid}.mp4")
    return FileResponse(path, media_type="video/mp4", headers=headers)


@router.delete("/api/storyboards/{sid}")
def delete_storyboard(sid: str):
    animatic.cancel(sid, wait=10)                   # a render in progress is stopped before its folder goes
    try:
        store.delete(sid)
    except store.UnknownStoryboard:
        raise HTTPException(404, "Unknown storyboard")
    _decoded.cache_clear()
    return {"deleted": sid}
