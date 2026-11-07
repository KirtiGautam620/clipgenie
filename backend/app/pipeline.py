"""The whole job in one go: transcribe -> choose moments -> edit clips."""
import copy
import json
import threading

from app import (captionstyles, checks, cuts, effects, hinglish, jobs, manifest, music, plan, quality, render,
                 rights, styles, textmode, ytdl)
from app.captions import words_in_clip
from app.clips import pick_clips
from app.export import base_path
from app.highlights import pick_ai_clips
from app.mix import apply_music
from app.transcribe import extract_audio, transcribe

# Whisper can only handle one job at a time (it isn't thread-safe, and
# 8 GB of RAM is tight). Other jobs wait here for their turn.
heavy_job_lock = threading.Lock()

DEFAULTS = {"min_len": 30, "max_len": 60, "count": 5, "use_ai": True, "framing": "crop",
            "music": True, "music_volume": 0.6, "caption_preset": captionstyles.DEFAULT_PRESET,
            "caption_script": "hinglish", "remove_pauses": True, "suggest_hook": True,
            "edit_mode": "auto", "style_id": styles.DEFAULT_STYLE}


def _music_info(track: dict, volume: float) -> dict:
    return {"track_id": track["id"], "title": track["title"], "volume": volume,
            "license": track["license_label"], "attribution": track["attribution"],
            "warning": track["warning"]}


def _mix_clip(folder, clip_id: int, track: dict, volume: float) -> dict:
    """Mix `track` under clip_N.mp4 -> clip_N_music.mp4 and describe what was used."""
    apply_music(folder / f"clip_{clip_id}.mp4", music.track_path(track),
                folder / f"clip_{clip_id}_music.mp4", volume)
    return _music_info(track, volume)


class Busy(RuntimeError):
    """Another video is being processed right now."""


def _load_clip(job_id: str, clip_id: int):
    folder = jobs.job_dir(job_id)
    clips_file = folder / "clips.json"
    data = json.loads(clips_file.read_text())
    clip = next((c for c in data["clips"] if c["id"] == clip_id), None)
    if clip is None:
        raise KeyError("Unknown clip")
    return folder, clips_file, data, clip, folder / f"clip_{clip_id}.mp4"


def _sync_clip(clip: dict, old: dict, new: dict, result: dict) -> None:
    """After a successful render, bring the clip entry in line with the manifest it was made from
    (older parts of the app, and old projects, read these fields)."""
    clip["effects"] = copy.deepcopy(new["effects"])
    clip["framing_choice"] = new["framing"]["mode"]
    clip["segments"] = copy.deepcopy(new["segments"])
    clip["fades"] = copy.deepcopy(new["fades"])
    clip["fade_with_video"] = new["audio"]["fade_with_video"]
    clip["clean_voice"] = new["audio"]["clean_voice"]
    if new["clip"] != old["clip"] or new["segments"] != old["segments"] or manifest.is_cut(new):
        span = new["clip"]                     # trimmed or tightened: cut, length and speech range follow
        if clip.get("cut"):
            clip["cut"]["cut_start"], clip["cut"]["cut_end"] = span["start"], span["end"]
        clip["duration"] = round(manifest.output_length(new), 1)
        if "start" in clip and "end" in clip:
            clip["start"], clip["end"] = max(clip["start"], span["start"]), min(clip["end"], span["end"])
    info = result.get("framing")
    if info:                                   # the picture was made again
        info = dict(info)
        clip["audio"] = info.pop("audio", clip.get("audio"))
        clip["framing"] = info
    if new["text"]["captions"] is not None:
        clip["captions"] = copy.deepcopy(new["text"]["captions"])
    if render.MUSIC in result["stages"]:
        wanted = new["audio"]["music"]
        clip["music"] = _music_info(result["music"], wanted["volume"]) if wanted else None


def _apply(job_id: str, clip_id: int, change, force=frozenset()) -> dict:
    """THE way a finished clip is edited. Under the one-job-at-a-time lock it
      1. builds the clip's manifest,  2. lets `change(clip, manifest)` edit it (and refuse bad edits),
      3. renders only the stages that differ (render.py, written safely),  4. saves the result.
    A real change is a new version of the clip, so its copyright checklist must be confirmed again."""
    if not heavy_job_lock.acquire(blocking=False):
        raise Busy("CocoGenie is busy processing a video. Try again in a minute.")
    try:
        folder, clips_file, data, clip, out = _load_clip(job_id, clip_id)
        old = manifest.current(folder, clip)
        m = copy.deepcopy(old)
        change(clip, m)
        new = manifest.validate(m)
        with jobs.timed(job_id, "render", clip=clip_id, stages="edit"):
            result = render.render(folder, clip_id, old, new, force)
        if not result["stages"] and clip == _load_clip(job_id, clip_id)[3]:
            return clip                         # nothing to change
        _sync_clip(clip, old, new, result)
        clip["version"] = clip.get("version", 0) + 1   # lets the page reload the video
        manifest.save(folder, clip_id, new, reason="edit")
        clip["checks"] = checks.safe_check(folder, clip_id, new)
        jobs.write_atomic(clips_file, json.dumps(data, ensure_ascii=False))
        return clip
    finally:
        heavy_job_lock.release()


def set_clip_music(job_id: str, clip_id: int, track_id: str | None, volume: float) -> dict:
    """Change (or remove) the music of one finished clip. Only the audio is re-mixed."""
    def change(clip, m):
        if track_id is None:
            m["audio"]["music"] = None
        else:
            if music.get_track(track_id) is None:
                raise KeyError("Unknown music track")
            m["audio"]["music"] = {"track_id": track_id, "volume": volume}
    return _apply(job_id, clip_id, change, force={render.MUSIC})


def set_clip_captions(job_id: str, clip_id: int, preset: str | None, overrides: dict,
                      texts: list[str] | None) -> dict:
    """Change the caption look and/or fix caption words of one finished clip.

    Only the captions are drawn again (over the saved caption-free base clip), then the music is
    mixed back in. The change is a new version of the clip, so its checklist must be confirmed again.
    """
    def change(clip, m):
        _, _, _, _, out = _load_clip(job_id, clip_id)
        state = textmode.text_state(clip)
        if textmode.is_untrusted(clip):
            raise ValueError(textmode.CAPTIONS_UNAVAILABLE)
        if state["mode"] != "captions":
            raise ValueError("This clip is showing a headline or no text. Switch it back to captions first.")
        caps = clip.get("captions")
        if not caps or not base_path(out).exists():
            raise ValueError("This clip was made before captions could be changed. "
                             "Make new clips from this video to edit its captions.")

        stored = {k: v for k, v in caps["style"].items() if k != "preset"}
        style = (captionstyles.resolve(preset, overrides) if preset
                 else captionstyles.resolve(caps["style"]["preset"], {**stored, **overrides}))
        words = caps["words"]
        if texts is not None:
            if len(texts) != len(words):
                raise ValueError("The caption words do not match this clip. Reload and try again.")
            cleaned = [t.strip() for t in texts]
            if any(not t or len(t) > 40 for t in cleaned):
                raise ValueError("Each caption word must be 1 to 40 characters.")
            words = [{**w, "text": t} for w, t in zip(words, cleaned)]
        if style.script != caps["style"].get("script", "original"):   # Hindi letters <-> Hinglish
            words = hinglish.convert_words(words, style.script)
        m["text"]["captions"] = {"style": style.as_dict(), "words": words}
    return _apply(job_id, clip_id, change, force={render.TEXT})


def _plan_text(clip: dict, mode: str | None, headline: dict | None, approve: bool):
    """Check a text change. Returns (new text state, mode to show, draft_only)."""
    state = dict(textmode.text_state(clip))
    state["headline"] = dict(state["headline"]) if state.get("headline") else None

    if headline is not None:           # a new or edited draft
        text = captionstyles.clean_headline(headline.get("text"))
        old = state["headline"] or {}
        old_style = {k: v for k, v in (old.get("style") or {}).items() if k != "preset"}
        preset = headline.get("preset")
        style = (captionstyles.resolve_headline(preset, headline.get("style") or {}) if preset
                 else captionstyles.resolve_headline((old.get("style") or {}).get("preset", captionstyles.DEFAULT_HEADLINE_PRESET),
                                                     {**old_style, **(headline.get("style") or {})}))
        state["headline"] = {"text": text, "style": style.as_dict(), "approved": False, "source": "user"}
        if mode is None and not approve:      # just a draft: nothing is drawn, the clip is not changed
            return state, None, True
        mode = mode or "headline"

    if mode == "headline" or (approve and mode is None):
        if not state["headline"]:
            raise ValueError("Type a headline first.")
        if not approve:
            raise ValueError("Preview the headline and approve it before it is added to the video.")
        state.update(mode="headline")
        state["headline"]["approved"] = True
        return state, "headline", False
    if mode == "none":
        state.update(mode="none")
        return state, "none", False
    if mode == "captions":
        if textmode.is_untrusted(clip) or not clip.get("captions"):
            raise ValueError(textmode.CAPTIONS_UNAVAILABLE)
        state.update(mode="captions")
        return state, "captions", False
    raise ValueError("Nothing to change.")


def set_clip_text(job_id: str, clip_id: int, mode: str | None, headline: dict | None,
                  approve: bool) -> dict:
    """Choose what text a clip shows.

    headline = {"text", "preset"?, "style"?}: saved as a DRAFT (nothing is drawn) until approve=True,
               so the user always previews and approves a headline before it is burned in.
    mode "none": export without any text.   mode "captions": back to captions, only if trustworthy.
    """
    if mode not in (None, "captions", "none", "headline"):
        raise ValueError("mode must be captions, headline or none")
    folder, clips_file, data, clip, out = _load_clip(job_id, clip_id)
    if not base_path(out).exists():
        raise ValueError("This clip was made before its text could be changed. Make new clips from this video.")
    state, shown, draft = _plan_text(clip, mode, headline, approve)
    if draft:
        clip["text"] = state
        jobs.write_atomic(clips_file, json.dumps(data, ensure_ascii=False))
        return clip

    def change(clip, m):
        clip["text"] = state
        m["text"]["mode"] = shown
        m["text"]["captions"] = m["text"]["headline"] = None
        if shown not in ("captions", "none"):          # a headline stands alone: no hook card beside it
            m["text"]["hook"] = None
        if shown == "headline":
            m["text"]["headline"] = {"text": state["headline"]["text"], "style": state["headline"]["style"]}
            clip["title"] = state["headline"]["text"]      # the user's own words now name the clip
        elif shown == "captions":
            caps = clip["captions"]
            m["text"]["captions"] = {"style": copy.deepcopy(caps["style"]), "words": copy.deepcopy(caps["words"])}
    return _apply(job_id, clip_id, change, force={render.TEXT})


def set_clip_hook(job_id: str, clip_id: int, text: str | None, preset: str | None, style: dict,
                  approve: bool, remove: bool) -> dict:
    """The hook: a title card over the first seconds, shown together with the captions.

    text given, approve False: saved as a DRAFT (nothing is drawn).  approve True: the user has seen
    it and wants it on the video.  remove True: take it off.  Only clips whose speech can be trusted
    (captions) or that show no text may carry a hook: a hook is never written from untrusted speech.
    """
    folder, clips_file, data, clip, out = _load_clip(job_id, clip_id)
    state = dict(textmode.text_state(clip))
    old = dict(state.get("hook") or {})

    if remove:
        if not old:
            raise ValueError("This clip has no hook.")
        was_drawn = bool(old.get("approved"))
        state["hook"] = None
        if not was_drawn:                                  # only a draft: nothing on the video to redo
            clip["text"] = state
            jobs.write_atomic(clips_file, json.dumps(data, ensure_ascii=False))
            return clip
    else:
        if state.get("mode") not in ("captions", "none") or textmode.is_untrusted(clip):
            raise ValueError("A hook can only be added to a clip with trustworthy captions or with no other text. "
                             "Use a headline for this clip.")
        if text is None and not old:
            raise ValueError("Type a hook first.")
        if text is not None:
            clean = captionstyles.clean_headline(text)
            old_style = {k: v for k, v in (old.get("style") or {}).items() if k != "preset"}
            chosen = (captionstyles.resolve_headline(preset, style or {}) if preset
                      else captionstyles.resolve_headline((old.get("style") or {}).get("preset", captionstyles.DEFAULT_HEADLINE_PRESET),
                                                          {**old_style, **(style or {})}))
            state["hook"] = {"text": clean, "style": chosen.as_dict(), "approved": False,
                             "source": "user" if text != old.get("text") else old.get("source", "user")}
        if not approve:                                    # a draft: saved, not drawn
            clip["text"] = state
            jobs.write_atomic(clips_file, json.dumps(data, ensure_ascii=False))
            return clip
        state["hook"]["approved"] = True

    def change(clip, m):
        clip["text"] = state
        hook = state.get("hook")
        m["text"]["hook"] = ({"text": hook["text"], "style": hook["style"]}
                             if hook and hook.get("approved") else None)
    return _apply(job_id, clip_id, change, force={render.TEXT})


def apply_style(job_id: str, clip_id: int, style_id: str) -> dict:
    """Change a finished video to follow an editing style (see styles.py): its framing, motion,
    fades, caption look, music level and how firmly pauses are tightened. Text you wrote, an approved
    hook and the words themselves stay. Only the parts that change are remade."""
    style = styles.get(style_id)
    if style is None:
        raise KeyError("Unknown style")
    folder = jobs.job_dir(job_id)

    def change(clip, m):
        skipped = []
        if style["framing"]:
            m["framing"]["mode"] = style["framing"]
        m["effects"], m["fades"] = dict(style["effects"]), dict(style["fades"])
        caps = m["text"]["captions"]
        if m["text"]["mode"] == "captions" and caps:
            caps["style"] = captionstyles.resolve(style["caption_preset"],
                                                  {"script": caps["style"].get("script", "original")}).as_dict()
        wanted = style["music"]
        if wanted is not None:
            if not wanted["enabled"]:
                m["audio"]["music"] = None
            elif m["audio"]["music"]:
                m["audio"]["music"]["volume"] = wanted["volume"]
            else:
                track = music.pick_track(clip.get("mood", "other"), f"{job_id}-{clip_id}")
                if track:
                    m["audio"]["music"] = {"track_id": track["id"], "volume": wanted["volume"]}
                else:
                    skipped.append("no music track available")
        # long pauses: measured again on the saved audio, so the clip can be tightened (or loosened)
        wav, transcript = folder / "audio.wav", folder / "transcript.json"
        if wav.exists() and transcript.exists():
            silences = cuts.detect_silences(wav)
            words = [w for seg in json.loads(transcript.read_text())["segments"] for w in seg["words"]]
            start, end = m["clip"]["start"], m["clip"]["end"]
            params = styles.pause_params(style["pauses"])
            kept = cuts.pause_segments(silences, words, start, end, **params) if params else [(start, end)]
            m["segments"] = [{"start": a, "end": b} for a, b in kept]
        else:
            skipped.append("pauses unchanged: the audio of this project is no longer saved")
        clip["edit"] = {**(clip.get("edit") or {}), "style_id": style_id, "style_name": style["name"],
                        "pauses": style["pauses"], "skipped": skipped}
    return _apply(job_id, clip_id, change)


def reset_to_ai(job_id: str, clip_id: int) -> dict:
    """Go back to the edit CocoGenie first made: cuts, trim, motion, fades, music and the caption
    words. What you chose for the text (your caption look, a headline, a hook) stays."""
    folder = jobs.job_dir(job_id)
    saved = manifest.load_baseline(folder, clip_id)
    if saved is None:
        raise ValueError("CocoGenie did not keep its original edit for this video (it was made before that "
                         "was saved), so there is nothing to go back to.")
    ai, how = saved

    def change(clip, m):
        for key in ("clip", "segments", "framing", "effects", "fades", "transitions"):
            m[key] = copy.deepcopy(ai[key])
        m["audio"] = copy.deepcopy(ai["audio"])
        if m["audio"]["music"] and music.get_track(m["audio"]["music"]["track_id"]) is None:
            m["audio"]["music"] = None                       # that track is gone from the library
        if m["text"]["mode"] == "captions" and m["text"]["captions"] and ai["text"]["captions"]:
            m["text"]["captions"]["words"] = copy.deepcopy(ai["text"]["captions"]["words"])
        if how:
            clip["edit"] = dict(how)
    return _apply(job_id, clip_id, change)


def set_clip_effects(job_id: str, clip_id: int, settings: dict) -> dict:
    """Change the zoom and pan of one finished clip. The picture is made again from the source
    video, then the same text (captions or headline) and music go back on top."""
    new_effects = effects.normalize(settings)      # ValueError with a readable message if invalid

    def change(clip, m):
        m["effects"] = new_effects
    return _apply(job_id, clip_id, change, force={render.PICTURE})


def apply_manifest(job_id: str, clip_id: int, document: dict) -> dict:
    """The editor's single 'Apply': take a whole manifest, check it, and make the clip from it.

    Text is not changed here: captions and headlines have their own tools, which keep the rule
    that the user previews and approves text and that untrusted speech is never turned into captions."""
    new = manifest.validate(document)

    def change(clip, m):
        if new["text"] != m["text"]:
            raise ValueError("Change the text with the captions and headline tools, not here.")
        wanted = new["audio"]["music"]
        if wanted and music.get_track(wanted["track_id"]) is None:
            raise KeyError("Unknown music track")
        before, after = m["clip"], new["clip"]
        if after != before:
            tol = 1e-6
            if after["start"] < before["start"] - tol or after["end"] > before["end"] + tol:
                raise ValueError("A video can only be shortened for now: choose a start and end "
                                 "inside its current length.")
            if m["text"]["captions"] is not None:      # captions follow the new start
                m["text"]["captions"] = manifest.trim_captions(
                    m["text"]["captions"], after["start"] - before["start"], after["end"] - after["start"])
        for key in ("clip", "segments", "framing", "effects", "fades", "transitions", "transition", "speed", "audio"):
            m[key] = copy.deepcopy(new[key])
    return _apply(job_id, clip_id, change)


def run_pipeline(job_id: str, language: str | None, settings: dict, url: str | None = None) -> None:
    folder = jobs.job_dir(job_id)
    jobs.set_status(job_id, "queued")
    try:
        if url:  # download first, outside the lock: it only needs the network
            jobs.set_status(job_id, "downloading", progress="0%")
            info = ytdl.download(
                url, folder,
                lambda pct: jobs.set_status(job_id, "downloading", progress=f"{pct}%"))
            rights.save_source(job_id, settings["rights"], url, info["title"], info["uploader"])
        with heavy_job_lock:
            transcript_file = folder / "transcript.json"
            if not transcript_file.exists():
                jobs.set_status(job_id, "transcribing")
                result = transcribe(folder / "source.mp4", folder, language)
                transcript_file.write_text(json.dumps(result, ensure_ascii=False, indent=2))
            _make_clips(job_id, settings)
    except Exception as e:  # show the error in the UI instead of crashing silently
        jobs.set_status(job_id, "error", error=str(e))


def _pauses(folder) -> tuple[list, object, float]:
    """Pauses and loudness envelope of the speech (for clean cuts) and the video length.
    Never stops a job: with nothing measured, cuts just use plain padding."""
    try:
        wav = folder / "audio.wav"
        if not wav.exists():       # jobs made before audio.wav was kept
            extract_audio(folder / "source.mp4", wav)
        return cuts.detect_silences(wav), cuts.load_envelope(wav), cuts.probe_duration(wav)
    except Exception:
        return [], None, cuts.probe_duration(folder / "source.mp4")


def _text_quality(transcript: dict, words: list[dict], cut: dict, envelope) -> dict:
    """Can the words of this clip be trusted? SHADOW MODE: recorded with the clip, acted on by
    nothing yet. A failure of the check itself must never stop a job."""
    try:
        start, end = cut["cut_start"], cut["cut_end"]
        return quality.assess_clip(
            quality.words_between(words, start, end), start, end, language=transcript.get("language", "hi"),
            asr=transcript.get("asr"), dropped=transcript.get("dropped"),
            lines=quality.lines_between(transcript["segments"], start, end), envelope=envelope)
    except Exception as e:
        return {"verdict": "unchecked", "reasons": [f"The quality check could not run ({type(e).__name__})."],
                "hard": [], "soft": [], "evidence": "none", "trusted_fraction": None,
                "trusted_ranges": [], "signals": {}}


def _make_clips(job_id: str, settings: dict) -> None:
    """Choose the moments, PLAN every clip, then render them one by one. Caller must hold heavy_job_lock."""
    s = {**DEFAULTS, **settings}
    folder = jobs.job_dir(job_id)
    transcript = json.loads((folder / "transcript.json").read_text())
    segments = transcript["segments"]

    jobs.set_status(job_id, "choosing")
    with jobs.timed(job_id, "choose_moments", ai=bool(s["use_ai"])):
        if s["use_ai"]:
            picks, note = pick_ai_clips(segments, s["min_len"], s["max_len"], s["count"])
        else:
            picks, note = pick_clips(segments, s["min_len"], s["max_len"], s["count"]), "ok"

    for old in [*folder.glob("clip_*.mp4"), *folder.glob("clip_*.manifest.json")]:   # clips of an earlier run
        old.unlink()
    (folder / "checklist.json").unlink(missing_ok=True)   # old confirmations no longer apply
    words = [w for seg in segments for w in seg["words"]]
    silences, envelope, media_end = _pauses(folder)
    # the editing style: Auto Edit and AI + Manual use "Natural" (what Auto Edit always did);
    # Custom Style uses the style the user chose. A style only adds choices; it is not another engine.
    mode = s["edit_mode"] if s["edit_mode"] in ("auto", "assist", "custom") else "auto"
    chosen = styles.get(s["style_id"]) if mode == "custom" else None
    edit_style = chosen or styles.get(styles.DEFAULT_STYLE)
    level = edit_style["pauses"] if s["remove_pauses"] else "off"
    style = captionstyles.resolve(edit_style["caption_preset"] if chosen else s["caption_preset"],
                                  {"script": s["caption_script"]})
    framing = edit_style["framing"] or s["framing"]
    music_on, music_volume = s["music"], s["music_volume"]
    if edit_style["music"] is not None:
        music_on, music_volume = edit_style["music"]["enabled"], edit_style["music"]["volume"]
    wants_hook = s["suggest_hook"] and edit_style["hook"]["enabled"]

    # 1. PLAN: every decision that needs no rendering, written down and checked first
    ctx = {"words": words, "silences": silences, "envelope": envelope, "media_end": media_end,
           "style": style, "remove_pauses": level != "off", "pause_params": styles.pause_params(level) or {},
           "assess": lambda cut: _text_quality(transcript, words, cut, envelope)}
    planned = [plan.plan_clip(n, p, ctx) for n, p in enumerate(picks, start=1)]
    hook_note = "ok"
    if wants_hook and s["use_ai"] and note == "ok":              # the model answered before: ask it for hooks
        with jobs.timed(job_id, "suggest_hooks", clips=len(planned)):
            hook_note = plan.suggest_hooks(planned, segments)
    the_plan = plan.build(job_id, planned, {**s, "style_id": edit_style["id"], "edit_mode": mode}, note, hook_note)
    plan.save(folder, the_plan)

    # 2. EXECUTE: render each planned clip (one at a time), then check the finished video
    done = []
    for item in planned:
        n, p, cut = item["id"], item["pick"], item["cut"]
        jobs.set_status(job_id, "exporting", progress=f"Clip {n} of {len(planned)}")
        entry = {"id": n, **p, "duration": round(p["end"] - p["start"], 1), "music": None,
                 "framing": {}, "framing_choice": framing, "cut": cut,
                 "effects": dict(edit_style["effects"]), "fades": dict(edit_style["fades"]),
                 "edit": {"mode": mode, "style_id": edit_style["id"], "style_name": edit_style["name"], "pauses": level},
                 "text_quality": item["text_quality"], "text": item["text"]}
        if item["segments"]:                 # long pauses were shortened: remember which parts are kept
            entry["segments"] = [{"start": a, "end": b} for a, b in item["segments"]]
            entry["duration"] = round(sum(b - a for a, b in item["segments"]), 1)
            entry["transition"] = manifest.new_clip_transition(entry["segments"])
        if item["text"]["mode"] == "captions":
            entry["captions"] = {"style": style.as_dict(), "words": item["cap_words"]}
            plan.attach_hook(entry["text"], item["hook"], edit_style["hook"]["seconds"], edit_style["hook"]["preset"])
        else:
            textmode.withhold(entry)
        track = music.pick_track(entry.get("mood", "other"), f"{job_id}-{n}") if music_on else None
        if track:  # a track that fits the clip's mood
            entry["music"] = _music_info(track, music_volume)
        # the clip is made from its manifest, exactly like every later edit (render.py)
        m = manifest.validate(manifest.from_clip(entry))
        with jobs.timed(job_id, "render", clip=n, stages="create"):
            result = render.create(folder, n, m)
        _sync_clip(entry, m, m, result)
        manifest.save(folder, n, m, reason="created")
        manifest.save_baseline(folder, n, m, edit=entry["edit"])     # CocoGenie's own version, to go back to
        entry["checks"] = checks.safe_check(folder, n, m)
        done.append(entry)

    jobs.write_atomic(folder / "clips.json",
                      json.dumps({"status": "done", "note": note, "clips": done}, ensure_ascii=False))
    jobs.set_status(job_id, "done", language=transcript["language"], note=note)


def run_clips_only(job_id: str, settings: dict) -> None:
    """Re-make clips from an existing transcript (different settings)."""
    jobs.set_status(job_id, "queued")
    try:
        with heavy_job_lock:
            _make_clips(job_id, settings)
    except Exception as e:
        jobs.set_status(job_id, "error", error=str(e))
