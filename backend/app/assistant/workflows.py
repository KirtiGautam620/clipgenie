"""A workflow: one run of a tool, planned, (confirmed,) executed step by step, saved with its progress.

    {"id", "conversation_id", "tool", "status": "awaiting_confirmation" | "running" | "done" | "error" | "cancelled",
     "args": {...}, "source": {...}, "steps": [{"key", "title", "status", "detail"}], "result": {...}, "error"}

Make clips runs the existing pipeline (run_pipeline / run_clips_only): the workflow only starts it
and follows its job status, so it is exactly the same work as the Create screen. Everything heavy
still waits for the one-job-at-a-time lock, so the assistant can never run two heavy jobs at once.
"""
import json
import threading
from datetime import datetime, timezone

from app import jobs, pipeline, projects, rights, styles, textmode, ytdl
from app.assistant import ideas, store
from app.content import copy as clip_copy
from app.content import script as outline
from app.llm import LLMError

KIND = "workflows"
MAKE_STEPS = [("source", "Get the video"), ("transcribe", "Listen and transcribe"),
              ("choose", "Find the best moments"), ("edit", "Edit the clips"), ("check", "Check the results")]
COPY_STEPS = [("read", "Read what is said in each clip"), ("write", "Write titles, descriptions and hashtags"),
              ("check", "Check each hashtag against what was said")]
SCRIPT_STEPS = [("read", "Read the idea and your video"), ("write", "Write the outline")]
COPY_MAX_CLIPS = 5
IDEA_STEPS = [("read", "Read your video"), ("think", "Think of ideas"), ("check", "Check each idea against what you said")]
# which step a job status means is running now
ACTIVE = {"uploaded": "source", "waiting": "source", "queued": "source", "downloading": "source", "transcribing": "transcribe",
          "choosing": "choose", "exporting": "edit"}
POLL_SECONDS = 1.0


def _now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def _steps(spec, skipped=()) -> list[dict]:
    return [{"key": k, "title": t, "status": "skipped" if k in skipped else "pending", "detail": ""} for k, t in spec]


def get(wf_id: str) -> dict:
    return store.load(KIND, wf_id)


def _save(wf: dict) -> dict:
    wf["updated_at"] = _now()
    store.save(KIND, wf)
    return wf


# ---------------------------------------------------------------- Make clips

def plan_make_clips(conversation_id: str, args: dict, source: dict) -> dict:
    """A plan the user checks before anything heavy starts. source: {"kind": "upload" | "url" | "project", ...}"""
    edit_mode = args.get("edit_mode", "auto")
    style_id = args.get("style_id", styles.DEFAULT_STYLE) if edit_mode == "custom" else styles.DEFAULT_STYLE
    wf = {"id": store.new_id(), "conversation_id": conversation_id, "tool": "make_clips",
          "status": "awaiting_confirmation", "created_at": _now(), "source": source,
          "args": {"count": int(args.get("count") or pipeline.DEFAULTS["count"]), "edit_mode": edit_mode,
                   "style_id": style_id},
          "needs_rights": source["kind"] in ("upload", "url"),
          "warning": "",
          "note": ("CocoGenie makes a new project from it, so the videos you already have stay as they are."
                   if source["kind"] == "project" else ""),
          "steps": _steps(MAKE_STEPS, skipped=("transcribe",) if source["kind"] == "project" else ()),
          "result": None, "error": None, "job_id": source.get("job_id")}
    return _save(wf)


def _check_choices(wf: dict, choices: dict) -> dict:
    """The final settings, from the plan plus what the user changed on it. ValueError if not usable."""
    count = int(choices.get("count", wf["args"]["count"]))
    if not 1 <= count <= 10:
        raise ValueError("Choose between 1 and 10 clips.")
    edit_mode = choices.get("edit_mode", wf["args"]["edit_mode"])
    if edit_mode not in ("auto", "assist", "custom"):
        raise ValueError("Unknown editing mode.")
    style_id = choices.get("style_id", wf["args"]["style_id"]) if edit_mode == "custom" else styles.DEFAULT_STYLE
    if styles.get(style_id) is None:
        raise ValueError("Please choose one of your editing styles.")
    settings = {"count": count, "edit_mode": edit_mode, "style_id": style_id}
    if wf["needs_rights"]:
        declared = choices.get("rights")
        if declared not in rights.SOURCE_RIGHTS:
            raise ValueError("Please say whether you own this video or have permission to use it.")
        if wf["source"]["kind"] == "url" and declared not in rights.DOWNLOAD_OK:
            raise ValueError("A video can only be imported from a link if you own it, have permission, "
                             "or it is public domain or licensed for reuse.")
        settings["rights"] = declared
    return settings


def confirm(wf_id: str, choices: dict) -> dict:
    """The user pressed Start: check their choices, then start the real job in the background."""
    wf = get(wf_id)
    if wf["tool"] != "make_clips":
        raise ValueError("Only a Make clips plan can be started.")
    if wf["status"] != "awaiting_confirmation":
        raise ValueError("This plan has already been started or cancelled.")
    chosen = _check_choices(wf, choices)
    settings = {**pipeline.DEFAULTS, **{k: chosen[k] for k in ("count", "edit_mode", "style_id")}}
    source = wf["source"]
    if source["kind"] == "upload":
        job_id = source["job_id"]
        if not (jobs.job_dir(job_id) / "source.mp4").exists():
            raise ValueError("That upload is no longer on this computer. Attach the video again.")
        rights.save_source(job_id, chosen["rights"], title=source.get("filename", ""))
        target, run_args = pipeline.run_pipeline, (job_id, None, settings)
    elif source["kind"] == "url":
        clean = ytdl.check_url(source["url"])
        job_id, _ = jobs.create_job()
        rights.save_source(job_id, chosen["rights"], clean)
        settings["rights"] = chosen["rights"]
        target, run_args = pipeline.run_pipeline, (job_id, None, settings, clean)
    else:                                   # an existing project: a NEW project from it, the original untouched
        job_id = projects.branch(source["job_id"])
        target, run_args = pipeline.run_clips_only, (job_id, settings)
    jobs.set_status(job_id, "queued")       # so following it never sees a stale status
    wf.update(status="running", job_id=job_id, args={**wf["args"], **{k: chosen[k] for k in ("count", "edit_mode", "style_id")}},
              started_at=_now())
    _save(wf)
    threading.Thread(target=target, args=run_args, daemon=True).start()
    threading.Thread(target=_follow, args=(wf_id,), daemon=True).start()
    return wf


def cancel(wf_id: str) -> dict:
    wf = get(wf_id)
    if wf["status"] != "awaiting_confirmation":
        raise ValueError("Only a plan that hasn't started can be cancelled.")
    wf["status"] = "cancelled"
    return _save(wf)


def _apply_status(wf: dict, status: dict) -> None:
    """Show a job status as workflow steps."""
    active = ACTIVE.get(status.get("status"))
    keys = [s["key"] for s in wf["steps"]]
    for step in wf["steps"]:
        if step["status"] == "skipped":
            continue
        if active is None:
            step["status"] = "done"
        else:
            here, now = keys.index(step["key"]), keys.index(active)
            step["status"] = "done" if here < now else "running" if here == now else "pending"
        step["detail"] = status.get("progress", "") if step["key"] == active else step["detail"]


def _clip_summaries(job_id: str) -> list[dict]:
    try:
        data = json.loads((jobs.job_dir(job_id) / "clips.json").read_text())
    except (OSError, ValueError):
        return []
    out = []
    for c in data.get("clips", []):
        c = textmode.public(c)
        out.append({"id": c["id"], "title": c.get("title") or f"Clip {c['id']}", "duration": c.get("duration"),
                    "version": c.get("version", 0), "checks": (c.get("checks") or {}).get("status", "unchecked"),
                    "needs_decision": c["text"].get("needs_decision", False)})
    return out


def _follow(wf_id: str) -> None:
    """Follow the job until it ends, keeping the workflow's steps up to date."""
    import time
    seen = None
    while True:
        wf = get(wf_id)
        status = jobs.get_status(wf["job_id"]) or {}
        key = (status.get("status"), status.get("progress"))
        if key != seen:
            seen = key
            if status.get("status") == "error":
                for step in wf["steps"]:
                    if step["status"] == "running":
                        step["status"] = "error"
                wf.update(status="error", error=status.get("error") or "Something went wrong.")
                _save(wf)
                return
            _apply_status(wf, status)
            if status.get("status") == "done":
                clips = _clip_summaries(wf["job_id"])
                checked = [c for c in clips if c["checks"] != "unchecked"]
                wf["steps"][-1]["detail"] = (f"{sum(c['checks'] == 'ok' for c in checked)} of {len(clips)} passed every check"
                                             if checked else "")
                wf.update(status="done", result={"project": projects.describe(wf["job_id"]), "clips": clips,
                                                 "note": status.get("note", "ok")}, finished_at=_now())
                _save(wf)
                return
            _save(wf)
        time.sleep(POLL_SECONDS)


# ---------------------------------------------------------------- Video ideas

def start_ideas(conversation_id: str, project: dict) -> dict:
    """Ideas need no confirmation (nothing is changed); they start straight away, after any heavy job."""
    wf = {"id": store.new_id(), "conversation_id": conversation_id, "tool": "video_ideas", "status": "running",
          "created_at": _now(), "source": {"kind": "project", "job_id": project["job_id"], "title": project["title"]},
          "args": {}, "needs_rights": False, "warning": "", "steps": _steps(IDEA_STEPS), "result": None,
          "error": None, "job_id": project["job_id"]}
    _save(wf)
    threading.Thread(target=_run_ideas, args=(wf["id"],), daemon=True).start()
    return wf


def _set_step(wf: dict, key: str, status: str, detail: str = "") -> None:
    for step in wf["steps"]:
        if step["key"] == key:
            step["status"], step["detail"] = status, detail


def _run_ideas(wf_id: str) -> None:
    wf = get(wf_id)
    try:
        _set_step(wf, "read", "running")
        _save(wf)
        segments = json.loads((jobs.job_dir(wf["job_id"]) / "transcript.json").read_text())["segments"]
        _set_step(wf, "read", "done")
        _set_step(wf, "think", "running", "waiting for any video being made to finish" if pipeline.heavy_job_lock.locked() else "")
        _save(wf)
        with pipeline.heavy_job_lock:              # the model needs memory: never beside a heavy job
            _set_step(wf, "think", "running")
            _save(wf)
            found = ideas.suggest(segments)
        _set_step(wf, "think", "done")
        _set_step(wf, "check", "done", f"{len(found)} idea{'s' if len(found) != 1 else ''} matched what you said")
        if not found:
            raise ValueError("I couldn't come up with ideas I could tie to what you said in this video.")
        wf.update(status="done", finished_at=_now(), result={
            "ideas": found, "project": wf["source"],
            "note": "Based only on what you said in this video. CocoGenie doesn't use YouTube search or trend data yet."})
    except LLMError:
        wf.update(status="error", error="The local AI model isn't running, so I can't think of ideas right now. "
                                        "Start it (see Settings) and ask again.")
    except Exception as e:
        for step in wf["steps"]:
            if step["status"] == "running":
                step["status"] = "error"
        wf.update(status="error", error=str(e) if isinstance(e, ValueError) else "Something went wrong while thinking of ideas.")
    _save(wf)


# ---------------------------------------------------------------- Create thumbnail

def start_thumbnail(conversation_id: str, project: dict) -> dict:
    """Nothing runs yet: the card lists the clips; the user picks one and its frames, and makes it."""
    wf = {"id": store.new_id(), "conversation_id": conversation_id, "tool": "create_thumbnail", "status": "done",
          "created_at": _now(), "source": {"kind": "project", "job_id": project["job_id"], "title": project["title"]},
          "args": {}, "needs_rights": False, "warning": "", "steps": [], "error": None, "job_id": project["job_id"],
          "result": {"project": project, "clips": _clip_summaries(project["job_id"])}, "finished_at": _now()}
    return _save(wf)


# ---------------------------------------------------------------- Write titles (title, description, hashtags)

def start_copy(conversation_id: str, project: dict) -> dict:
    """Drafts only: saved on each clip as a suggestion, used only after the user saves it."""
    wf = {"id": store.new_id(), "conversation_id": conversation_id, "tool": "write_copy", "status": "running",
          "created_at": _now(), "source": {"kind": "project", "job_id": project["job_id"], "title": project["title"]},
          "args": {}, "needs_rights": False, "warning": "", "steps": _steps(COPY_STEPS), "result": None,
          "error": None, "job_id": project["job_id"]}
    _save(wf)
    threading.Thread(target=_run_copy, args=(wf["id"],), daemon=True).start()
    return wf


def _run_copy(wf_id: str) -> None:
    wf = get(wf_id)
    job_id = wf["job_id"]
    try:
        _set_step(wf, "read", "running")
        _save(wf)
        clips = json.loads((jobs.job_dir(job_id) / "clips.json").read_text()).get("clips", [])
        trusted = [c for c in clips if clip_copy.can_draft(c)]
        skipped = len(clips) - len(trusted)
        chosen = trusted[:COPY_MAX_CLIPS]
        if not chosen:
            raise ValueError("None of these clips has speech CocoGenie could trust, so it won't write about them. "
                             "You can write your own titles in each clip's Export window.")
        _set_step(wf, "read", "done", f"{len(chosen)} clip{'s' if len(chosen) != 1 else ''}"
                  + (f", {skipped} skipped (speech not trusted)" if skipped else ""))
        drafts, failed = [], 0
        for n, c in enumerate(chosen, 1):
            _set_step(wf, "write", "running", f"clip {n} of {len(chosen)}"
                      + (" (waiting for the video being made)" if pipeline.heavy_job_lock.locked() else ""))
            _save(wf)
            try:
                entry = clip_copy.draft(job_id, c["id"], wait=True)
                drafts.append({"id": c["id"], "version": c.get("version", 0), **entry["copy"]})
            except LLMError:
                raise
            except ValueError:
                failed += 1
        _set_step(wf, "write", "done")
        _set_step(wf, "check", "done", f"{len(drafts)} draft{'s' if len(drafts) != 1 else ''} ready"
                  + (f", {failed} couldn't be written" if failed else ""))
        if not drafts:
            raise ValueError("The AI couldn't write usable text for these clips. Try again, or write your own.")
        wf.update(status="done", finished_at=_now(), result={
            "project": projects.describe(job_id), "drafts": drafts,
            "note": "Drafts written only from what is said in each clip. Edit them and press Save before you copy them."})
    except LLMError:
        _fail_running(wf)
        wf.update(status="error", error="The local AI model isn't running, so I can't write titles right now. "
                                        "Start it (see Settings) and ask again.")
    except Exception as e:
        _fail_running(wf)
        wf.update(status="error", error=str(e) if isinstance(e, ValueError) else "Something went wrong while writing titles.")
    _save(wf)


def _fail_running(wf: dict) -> None:
    for step in wf["steps"]:
        if step["status"] == "running":
            step["status"] = "error"


# ---------------------------------------------------------------- Script outline (from a video idea)

def start_script(conversation_id: str, ideas_wf_id: str, index: int) -> dict:
    """An outline for one idea from a finished Video ideas card. ValueError if there is no such idea."""
    source = get(ideas_wf_id)
    if source["tool"] != "video_ideas" or source["status"] != "done":
        raise ValueError("Pick an idea from a finished Video ideas card.")
    found = source["result"]["ideas"]
    if not 0 <= index < len(found):
        raise ValueError("That idea isn't on the card.")
    idea = found[index]
    wf = {"id": store.new_id(), "conversation_id": conversation_id, "tool": "script_outline", "status": "running",
          "created_at": _now(), "source": {"kind": "idea", "workflow_id": ideas_wf_id, "index": index,
                                           "job_id": source["job_id"], "title": idea["title"]},
          "args": {}, "needs_rights": False, "warning": "", "steps": _steps(SCRIPT_STEPS), "result": None,
          "error": None, "job_id": source["job_id"], "idea": idea}
    _save(wf)
    threading.Thread(target=_run_script, args=(wf["id"],), daemon=True).start()
    return wf


def _run_script(wf_id: str) -> None:
    wf = get(wf_id)
    try:
        _set_step(wf, "read", "running")
        _save(wf)
        segments = json.loads((jobs.job_dir(wf["job_id"]) / "transcript.json").read_text())["segments"]
        _set_step(wf, "read", "done")
        _set_step(wf, "write", "running", "waiting for any video being made to finish" if pipeline.heavy_job_lock.locked() else "")
        _save(wf)
        with pipeline.heavy_job_lock:
            result = outline.draft(wf["idea"], ideas.excerpt(segments))
        _set_step(wf, "write", "done")
        wf.update(status="done", finished_at=_now(), result={
            **result, "idea": wf["idea"],
            "note": "A draft outline from this idea and what you said before. Rewrite it in your own words."})
    except LLMError:
        _fail_running(wf)
        wf.update(status="error", error="The local AI model isn't running, so I can't write an outline right now. "
                                        "Start it (see Settings) and ask again.")
    except Exception as e:
        _fail_running(wf)
        wf.update(status="error", error=str(e) if isinstance(e, ValueError) else "Something went wrong while writing the outline.")
    _save(wf)


# ---------------------------------------------------------------- after a restart

def mark_interrupted() -> int:
    """A Video ideas, Write titles or Script run that was going when the server stopped can never finish. (Make clips runs are
    followed from their job, which the job tracker marks interrupted itself.)"""
    count = 0
    for wf in store.all_of(KIND):
        if wf.get("status") == "running":
            if wf["tool"] == "make_clips" and wf.get("job_id"):
                threading.Thread(target=_follow, args=(wf["id"],), daemon=True).start()   # report how it ended
                continue
            wf.update(status="error", error="This was interrupted because CocoGenie restarted. Please ask again.")
            _save(wf)
            count += 1
    return count
