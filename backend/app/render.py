"""Render one clip from its editing manifest: only the stages that changed, written safely.

A clip is made in three stages (see export.py and mix.py):

    picture  source video -> clip_N_base.mp4   (trim, framing, zoom/pan, voice; no text)
    text     base + text -> clip_N.mp4         (captions / headline / nothing)
    music    clip_N.mp4  -> clip_N_music.mp4   (music mixed in; the picture is copied)

`stages(old, new)` says which of them a change needs, so a caption tweak never redoes the picture
and a volume change never redoes the text. `render()` writes every result to a temporary folder
first and only then moves the files into place, so a failed render (or a crash) leaves the clip
exactly as it was.
"""
import os
import shutil
from pathlib import Path

from app import captionstyles, manifest, mix, music
from app.export import apply_captions, apply_headline, apply_no_text, base_path, render_base

PICTURE, TEXT, MUSIC = "picture", "text", "music"


def _speed(m: dict) -> float:
    return m.get("speed", 1.0)


def _transition_key(m: dict):
    """What the picture depends on for transitions. Old manifests have none, which means no dissolve."""
    t = m.get("transition") or {"type": "none"}
    return (t.get("type"), t.get("seconds") if t.get("type") == "dissolve" else None)


def stages(old: dict | None, new: dict, force: set | frozenset = frozenset()) -> list[str]:
    """Which stages must run to turn a clip made from `old` into one made from `new`.
    `force` adds stages even when nothing changed (an explicit 'apply'). With no `old` (a clip
    that does not exist yet) every stage runs."""
    if old is None:
        return [PICTURE, TEXT, MUSIC]
    todo = set(force)
    if any(old[k] != new[k] for k in ("clip", "segments", "framing", "effects")) \
            or old["audio"]["clean_voice"] != new["audio"]["clean_voice"] \
            or _transition_key(old) != _transition_key(new) or _speed(old) != _speed(new):
        todo.add(PICTURE)
    if (PICTURE in todo or old["text"] != new["text"] or old["fades"] != new["fades"]
            or old["audio"]["fade_with_video"] != new["audio"]["fade_with_video"]):
        todo.add(TEXT)
    if TEXT in todo or old["audio"]["music"] != new["audio"]["music"]:
        todo.add(MUSIC)
    return [s for s in (PICTURE, TEXT, MUSIC) if s in todo]


def text_drawer(spec: dict, folder: Path, fades: dict | None = None, fade_audio: bool = True):
    """A function(base, target) that puts the manifest's text on the picture, in the same pass
    that applies the video fades (so fades cost no extra encode and also fade the text)."""
    if spec["kind"] == "captions":
        style = captionstyles.resolve(spec["style"].get("preset"),
                                      {k: v for k, v in spec["style"].items() if k != "preset"})
        return lambda base, target: apply_captions(base, spec["words"], style, target, folder, fades, fade_audio,
                                                   spec.get("hook"))
    if spec["kind"] == "headline":
        style = captionstyles.resolve_headline(spec["style"].get("preset"), spec["style"])
        return lambda base, target: apply_headline(base, spec["text"], style, target, folder, fades, fade_audio)
    return lambda base, target: apply_no_text(base, target, fades, fade_audio, spec.get("hook"))   # "none" or "pending"


def create(folder: Path, clip_id: int, new: dict) -> dict:
    """Make clip `clip_id` for the first time (or from scratch) from the manifest `new`."""
    return render(folder, clip_id, None, new)


def render(folder: Path, clip_id: int, old: dict | None, new: dict, force: set | frozenset = frozenset()) -> dict:
    """Rebuild clip `clip_id` in `folder` from the manifest `new`. Returns what happened:
    {"stages": [...], "framing": info or None, "music": track dict or None}.
    Raises (and changes nothing on disk) if any stage fails."""
    todo = stages(old, new, force)
    result = {"stages": todo, "framing": None, "music": None}
    if not todo:
        return result
    if PICTURE in todo or TEXT in todo:
        manifest.check_renderable(new)

    out = folder / f"clip_{clip_id}.mp4"
    base = base_path(out)
    if TEXT in todo and PICTURE not in todo and not base.exists():
        raise ValueError("This clip was made before its text could be changed. Make new clips from this video.")
    music_out = folder / f"clip_{clip_id}_music.mp4"
    tmp = folder / f".render_{clip_id}"
    shutil.rmtree(tmp, ignore_errors=True)
    tmp.mkdir()
    t_base, t_out, t_music = tmp / base.name, tmp / out.name, tmp / music_out.name
    try:
        if PICTURE in todo:
            source = folder / "source.mp4"
            if not source.exists():
                raise ValueError("The original video for this clip is no longer on this computer, "
                                 "so its picture cannot be remade.")
            result["framing"] = render_base(source, base=t_base, **manifest.render_args(new))
        if TEXT in todo:
            text_drawer(manifest.text_drawer_spec(new), tmp, new["fades"], new["audio"]["fade_with_video"])(
                t_base if PICTURE in todo else base, t_out)
        final = t_out if TEXT in todo else out

        track = None
        wanted = new["audio"]["music"]
        if MUSIC in todo and wanted:
            track = music.get_track(wanted["track_id"])
            if track is None:
                raise KeyError("Unknown music track")
            mix.apply_music(final, music.track_path(track), t_music, wanted["volume"], wanted.get("start", 0.0))
        result["music"] = track

        # every stage succeeded: move the results into place
        if PICTURE in todo:
            os.replace(t_base, base)
        if TEXT in todo:
            os.replace(t_out, out)
        if MUSIC in todo:
            if track is not None:
                os.replace(t_music, music_out)
            else:
                music_out.unlink(missing_ok=True)   # no music wanted: never serve a stale mix
    finally:
        shutil.rmtree(tmp, ignore_errors=True)
    return result
