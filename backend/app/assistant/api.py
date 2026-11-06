"""HTTP endpoints for the assistant (all under /api/assistant)."""
import re
import shutil
from datetime import datetime, timezone

from fastapi import APIRouter, File, HTTPException, UploadFile
from pydantic import BaseModel

from app import jobs, projects, rights, ytdl
from app.assistant import router as intents
from app.assistant import store, tools, workflows

api = APIRouter(prefix="/api/assistant")
CONVERSATIONS = "conversations"

HELP = ("I can make clips from a video, suggest ideas for your next video, write titles and hashtags for "
        "your clips, or make a thumbnail. Attach a video or paste a YouTube link, or pick one of the shortcuts.")


def _now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def _conversation(conv_id: str | None) -> dict:
    if conv_id:
        try:
            return store.load(CONVERSATIONS, conv_id)
        except store.NotFound:
            raise HTTPException(404, "Unknown conversation")
    return {"id": store.new_id(), "created_at": _now(), "messages": []}


def _say(conv: dict, role: str, text: str, workflow_id: str | None = None) -> None:
    conv["messages"].append({"role": role, "text": text, "workflow_id": workflow_id, "at": _now()})


def _attachment(job_id: str | None) -> dict | None:
    """An uploaded video waiting in the chat (uploaded, not processed yet)."""
    if not job_id:
        return None
    project = projects.describe(job_id) if jobs.JOB_ID.fullmatch(job_id) else None
    if project is None:
        raise HTTPException(404, "That video upload was not found. Attach it again.")
    return project


def decide(conv: dict, text: str, attachment: dict | None) -> tuple[str, dict | None]:
    """What to answer and which workflow (if any) this message starts."""
    choice = intents.route(text, has_attachment=attachment is not None)
    name, args = choice["tool"], choice["args"]
    if name is None:
        return HELP, None
    tool = tools.get(name)
    if not tool["available"]:
        return f"{tool['title']} isn't available yet. {tool['reason']}", None

    if name == "make_clips":
        if attachment:
            source = {"kind": "upload", "job_id": attachment["job_id"], "filename": attachment["title"]}
            where = f"your upload “{attachment['title']}”"
        elif "url" in args:
            try:
                source = {"kind": "url", "url": ytdl.check_url(args["url"])}
            except ytdl.ImportError_ as e:
                return str(e), None
            where = "that YouTube video"
        elif args.get("project") == "latest" and (latest := projects.latest_with_transcript()):
            source = {"kind": "project", "job_id": latest["job_id"], "title": latest["title"]}
            where = f"your last video “{latest['title']}”, as a new project (your current videos stay)"
        else:
            return ("Which video? Attach one, paste a YouTube link, or say “from my last video”.", None)
        wf = workflows.plan_make_clips(conv["id"], args, source)
        n = wf["args"]["count"]
        return (f"Here's the plan: up to {n} clip{'s' if n != 1 else ''} from {where}, edited automatically. "
                "Check the details below and press Start.", wf)

    if name == "video_ideas":
        if attachment and not attachment["has_transcript"]:
            return ("I haven't listened to that upload yet. Make clips from it first, then ask me for ideas.", None)
        project = attachment if attachment else projects.latest_with_transcript()
        if project is None:
            return ("I need one of your videos to listen to first. Make clips from a video, then ask me again.", None)
        wf = workflows.start_ideas(conv["id"], project)
        return (f"Reading what you said in “{project['title']}” and thinking of ideas for your next video…", wf)

    if name in ("create_thumbnail", "write_copy"):
        project = attachment if attachment and attachment["clips"] else projects.latest_with_clips()
        if project is None:
            return ("You don't have any finished clips yet. Make clips from a video first, then ask me again.", None)
        if name == "create_thumbnail":
            wf = workflows.start_thumbnail(conv["id"], project)
            return (f"Pick a clip from “{project['title']}”. I'll find its sharpest, best-lit frames "
                    "and you choose one and the text.", wf)
        wf = workflows.start_copy(conv["id"], project)
        return (f"Writing a title, description and hashtags for the clips in “{project['title']}”, "
                "from what is said in each one…", wf)
    return HELP, None


# ---------------------------------------------------------------- endpoints

@api.get("/tools")
def list_tools():
    """Every shortcut, with whether it works yet (and why not)."""
    return {"tools": tools.listing()}


class MessageIn(BaseModel):
    text: str
    conversation_id: str | None = None
    attachment_job_id: str | None = None


@api.post("/messages")
def send_message(body: MessageIn):
    text = " ".join(body.text.split())[:2000]
    if not text:
        raise HTTPException(400, "Please type what you'd like to do.")
    conv = _conversation(body.conversation_id)
    attachment = _attachment(body.attachment_job_id)
    _say(conv, "user", text)
    reply, wf = decide(conv, text, attachment)
    _say(conv, "assistant", reply, wf["id"] if wf else None)
    store.save(CONVERSATIONS, conv)
    return {"conversation": conv, "reply": reply, "workflow": wf}


@api.get("/conversations/{conv_id}")
def get_conversation(conv_id: str):
    return _conversation(conv_id)


@api.get("/workflows/{wf_id}")
def get_workflow(wf_id: str):
    try:
        return workflows.get(wf_id)
    except store.NotFound:
        raise HTTPException(404, "Unknown workflow")


class ConfirmIn(BaseModel):
    rights: str | None = None
    count: int | None = None
    edit_mode: str | None = None
    style_id: str | None = None


@api.post("/workflows/{wf_id}/confirm")
def confirm_workflow(wf_id: str, body: ConfirmIn):
    try:
        return workflows.confirm(wf_id, {k: v for k, v in body.model_dump().items() if v is not None})
    except store.NotFound:
        raise HTTPException(404, "Unknown workflow")
    except (ValueError, ytdl.ImportError_) as e:
        raise HTTPException(400, str(e))


class ScriptIn(BaseModel):
    index: int


@api.post("/workflows/{wf_id}/script")
def draft_script(wf_id: str, body: ScriptIn):
    """"Draft a script" on an idea: a new message and outline run in the same conversation."""
    try:
        ideas_wf = workflows.get(wf_id)
        conv = _conversation(ideas_wf["conversation_id"])
        wf = workflows.start_script(conv["id"], wf_id, body.index)
    except store.NotFound:
        raise HTTPException(404, "Unknown workflow")
    except ValueError as e:
        raise HTTPException(400, str(e))
    _say(conv, "user", f"Draft a script for “{wf['idea']['title']}”")
    _say(conv, "assistant", "Writing an outline: a hook, the main points and a closing line…", wf["id"])
    store.save(CONVERSATIONS, conv)
    return {"conversation": conv, "workflow": wf}


@api.post("/workflows/{wf_id}/cancel")
def cancel_workflow(wf_id: str):
    try:
        return workflows.cancel(wf_id)
    except store.NotFound:
        raise HTTPException(404, "Unknown workflow")
    except ValueError as e:
        raise HTTPException(400, str(e))


@api.post("/upload")
async def upload_for_chat(file: UploadFile = File(...)):
    """Keep a video for the chat WITHOUT starting anything: the user says what to do with it first."""
    suffix = re.sub(r"[^a-z0-9]", "", (file.filename or "").rsplit(".", 1)[-1].lower())
    if suffix != "mp4":
        raise HTTPException(400, "Please upload an MP4 file")
    job_id, folder = jobs.create_job()
    with open(folder / "source.mp4", "wb") as out:
        shutil.copyfileobj(file.file, out)         # streamed to disk, safe for big files
    # nothing is declared yet: the user says who owns the video when they confirm the plan
    rights.save_source(job_id, "unsure", title=file.filename or "")
    jobs.set_status(job_id, "waiting")      # not "running": a restart must not mark it as failed
    return {"job_id": job_id, "filename": file.filename}
