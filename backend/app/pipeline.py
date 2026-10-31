"""The whole job in one go: transcribe -> choose moments -> edit clips."""
import json
import threading

from app import captionstyles, cuts, jobs, music, quality, rights, textmode, ytdl
from app.captions import words_in_clip
from app.clips import pick_clips
from app.export import apply_captions, apply_headline, apply_no_text, base_path, export_clip
from app.highlights import pick_ai_clips
from app.mix import apply_music
from app.transcribe import extract_audio, transcribe

# Whisper can only handle one job at a time (it isn't thread-safe, and
# 8 GB of RAM is tight). Other jobs wait here for their turn.
heavy_job_lock = threading.Lock()

DEFAULTS = {"min_len": 30, "max_len": 60, "count": 5, "use_ai": True, "framing": "crop",
            "music": True, "music_volume": 0.6, "caption_preset": captionstyles.DEFAULT_PRESET}


def _music_info(track: dict, volume: float) -> dict:
    return {"track_id": track["id"], "title": track["title"], "volume": volume,
            "license": track["license_label"], "attribution": track["attribution"],
            "warning": track["warning"]}


def _mix_clip(folder, clip_id: int, track: dict, volume: float) -> dict:
    """Mix `track` under clip_N.mp4 -> clip_N_music.mp4 and describe what was used."""
    apply_music(folder / f"clip_{clip_id}.mp4", music.track_path(track),
                folder / f"clip_{clip_id}_music.mp4", volume)
    return _music_info(track, volume)


def set_clip_music(job_id: str, clip_id: int, track_id: str | None, volume: float) -> dict:
    """Change (or remove) the music of one finished clip. Only the audio is re-mixed."""
    folder = jobs.job_dir(job_id)
    clips_file = folder / "clips.json"
    data = json.loads(clips_file.read_text())
    clip = next((c for c in data["clips"] if c["id"] == clip_id), None)
    if clip is None:
        raise KeyError("Unknown clip")
    if track_id is None:
        (folder / f"clip_{clip_id}_music.mp4").unlink(missing_ok=True)
        clip["music"] = None
    else:
        track = music.get_track(track_id)
        if track is None:
            raise KeyError("Unknown music track")
        clip["music"] = _mix_clip(folder, clip_id, track, volume)
    clip["version"] = clip.get("version", 0) + 1   # lets the page reload the video
    jobs.write_atomic(clips_file, json.dumps(data, ensure_ascii=False))
    return clip


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


def _redraw(job_id: str, clip_id: int, folder, clips_file, data, clip, out, draw) -> dict:
    """Draw the clip's text layer again (draw(base, out) does it), then mix the music back in.
    Only one heavy job at a time; a new version of the clip, so its checklist resets."""
    if not heavy_job_lock.acquire(blocking=False):
        raise Busy("ClipGenie is busy processing a video. Try again in a minute.")
    try:
        draw(base_path(out), out)
        if clip.get("music"):     # the picture changed, so mix the music under it again
            jobs.write_atomic(clips_file, json.dumps(data, ensure_ascii=False))
            return set_clip_music(job_id, clip_id, clip["music"]["track_id"], clip["music"]["volume"])
        clip["version"] = clip.get("version", 0) + 1   # lets the page reload the video
        jobs.write_atomic(clips_file, json.dumps(data, ensure_ascii=False))
        return clip
    finally:
        heavy_job_lock.release()


def set_clip_captions(job_id: str, clip_id: int, preset: str | None, overrides: dict,
                      texts: list[str] | None) -> dict:
    """Change the caption look and/or fix caption words of one finished clip.

    Only the captions are drawn again (over the saved caption-free base clip), then the music is
    mixed back in. The change is a new version of the clip, so its checklist must be confirmed again.
    """
    folder, clips_file, data, clip, out = _load_clip(job_id, clip_id)
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

    def draw(base, target):
        apply_captions(base, words, style, target, folder)
        clip["captions"] = {"style": style.as_dict(), "words": words}
    return _redraw(job_id, clip_id, folder, clips_file, data, clip, out, draw)


def set_clip_text(job_id: str, clip_id: int, mode: str | None, headline: dict | None,
                  approve: bool) -> dict:
    """Choose what text a clip shows.

    headline = {"text", "preset"?, "style"?}: saved as a DRAFT (nothing is drawn) until approve=True,
               so the user always previews and approves a headline before it is burned in.
    mode "none": export without any text.   mode "captions": back to captions, only if trustworthy.
    """
    folder, clips_file, data, clip, out = _load_clip(job_id, clip_id)
    if mode not in (None, "captions", "none", "headline"):
        raise ValueError("mode must be captions, headline or none")
    if not base_path(out).exists():
        raise ValueError("This clip was made before its text could be changed. Make new clips from this video.")
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
            clip["text"] = state
            jobs.write_atomic(clips_file, json.dumps(data, ensure_ascii=False))
            return clip
        mode = mode or "headline"

    if mode == "headline" or (approve and mode is None):
        if not state["headline"]:
            raise ValueError("Type a headline first.")
        if not approve:
            raise ValueError("Preview the headline and approve it before it is added to the video.")
        text = state["headline"]["text"]
        style = captionstyles.resolve_headline(state["headline"]["style"]["preset"], state["headline"]["style"])
        state.update(mode="headline")
        state["headline"]["approved"] = True

        def draw(base, target):
            apply_headline(base, text, style, target, folder)
            clip["text"] = state
            clip["title"] = text           # the user's own words now name the clip
    elif mode == "none":
        state.update(mode="none")

        def draw(base, target):
            apply_no_text(base, target)
            clip["text"] = state
    elif mode == "captions":
        caps = clip.get("captions")
        if textmode.is_untrusted(clip) or not caps:
            raise ValueError(textmode.CAPTIONS_UNAVAILABLE)
        style = captionstyles.resolve(caps["style"]["preset"], {k: v for k, v in caps["style"].items() if k != "preset"})
        state.update(mode="captions")

        def draw(base, target):
            apply_captions(base, caps["words"], style, target, folder)
            clip["text"] = state
    else:
        raise ValueError("Nothing to change.")
    return _redraw(job_id, clip_id, folder, clips_file, data, clip, out, draw)


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
    """Choose the moments and export them. Caller must hold heavy_job_lock."""
    s = {**DEFAULTS, **settings}
    folder = jobs.job_dir(job_id)
    transcript = json.loads((folder / "transcript.json").read_text())
    segments = transcript["segments"]

    jobs.set_status(job_id, "choosing")
    if s["use_ai"]:
        picks, note = pick_ai_clips(segments, s["min_len"], s["max_len"], s["count"])
    else:
        picks, note = pick_clips(segments, s["min_len"], s["max_len"], s["count"]), "ok"

    for old in folder.glob("clip_*.mp4"):   # clips of an earlier run
        old.unlink()
    (folder / "checklist.json").unlink(missing_ok=True)   # old confirmations no longer apply
    words = [w for seg in segments for w in seg["words"]]
    silences, envelope, media_end = _pauses(folder)
    style = captionstyles.resolve(s["caption_preset"])
    done = []
    for n, p in enumerate(picks, start=1):
        jobs.set_status(job_id, "exporting", progress=f"Clip {n} of {len(picks)}")
        # start/end = the speech; cut = a little wider, ending inside real pauses where possible
        cut = cuts.refine(words, silences, p["start"], p["end"], media_end, envelope)
        text_quality = _text_quality(transcript, words, cut, envelope)
        text = textmode.initial_state(text_quality)
        # Words are only drawn (and stored) when they can be trusted. Otherwise the clip is made
        # with no text and waits for the user's choice; the raw transcript stays in transcript.json.
        cap_words = (words_in_clip(words, cut["cut_start"], cut["cut_end"])
                     if text["mode"] == "captions" else [])
        framing_info = export_clip(folder / "source.mp4", words, cut["cut_start"], cut["cut_end"],
                                   folder / f"clip_{n}.mp4", folder, s["framing"],
                                   style=style, cap_words=cap_words)
        audio_info = framing_info.pop("audio")
        entry = {"id": n, **p, "duration": round(p["end"] - p["start"], 1), "music": None,
                 "framing": framing_info, "cut": cut, "audio": audio_info,
                 "text_quality": text_quality, "text": text}
        if text["mode"] == "captions":
            entry["captions"] = {"style": style.as_dict(), "words": cap_words}
        else:
            textmode.withhold(entry)
        track = music.pick_track(entry.get("mood", "other"), f"{job_id}-{n}") if s["music"] else None
        if track:  # a track that fits the clip's mood
            entry["music"] = _mix_clip(folder, n, track, s["music_volume"])
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
