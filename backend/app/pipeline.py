"""The whole job in one go: transcribe -> choose moments -> edit clips."""
import json
import threading

from app import captionstyles, cuts, jobs, music, rights, ytdl
from app.captions import words_in_clip
from app.clips import pick_clips
from app.export import apply_captions, base_path, export_clip
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


def set_clip_captions(job_id: str, clip_id: int, preset: str | None, overrides: dict,
                      texts: list[str] | None) -> dict:
    """Change the caption look and/or fix caption words of one finished clip.

    Only the captions are drawn again (over the saved caption-free base clip), then the music is
    mixed back in. The change is a new version of the clip, so its checklist must be confirmed again.
    """
    folder = jobs.job_dir(job_id)
    clips_file = folder / "clips.json"
    data = json.loads(clips_file.read_text())
    clip = next((c for c in data["clips"] if c["id"] == clip_id), None)
    if clip is None:
        raise KeyError("Unknown clip")
    caps, out = clip.get("captions"), folder / f"clip_{clip_id}.mp4"
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

    if not heavy_job_lock.acquire(blocking=False):
        raise Busy("ClipGenie is busy processing a video. Try again in a minute.")
    try:
        apply_captions(base_path(out), words, style, out, folder)
        clip["captions"] = {"style": style.as_dict(), "words": words}
        if clip.get("music"):     # the picture changed, so mix the music under it again
            jobs.write_atomic(clips_file, json.dumps(data, ensure_ascii=False))
            return set_clip_music(job_id, clip_id, clip["music"]["track_id"], clip["music"]["volume"])
        clip["version"] = clip.get("version", 0) + 1   # lets the page reload the video
        jobs.write_atomic(clips_file, json.dumps(data, ensure_ascii=False))
        return clip
    finally:
        heavy_job_lock.release()


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
        # the caption words are saved with the clip, so they can be edited and re-drawn later
        cap_words = words_in_clip(words, cut["cut_start"], cut["cut_end"])
        framing_info = export_clip(folder / "source.mp4", words, cut["cut_start"], cut["cut_end"],
                                   folder / f"clip_{n}.mp4", folder, s["framing"],
                                   style=style, cap_words=cap_words)
        audio_info = framing_info.pop("audio")
        entry = {"id": n, **p, "duration": round(p["end"] - p["start"], 1), "music": None,
                 "framing": framing_info, "cut": cut, "audio": audio_info,
                 "captions": {"style": style.as_dict(), "words": cap_words}}
        track = music.pick_track(p.get("mood", "other"), f"{job_id}-{n}") if s["music"] else None
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
