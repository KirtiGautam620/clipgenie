"""FFmpeg commands for a Photo Story, written as plain lists of text.

Nothing here RUNS anything: these functions only build the command lists (a later step hands them
to FFmpeg). That keeps them testable in milliseconds with no video, no model and almost no memory.

Pipeline the commands describe:
  1. one short silent clip per scene (the photo, with its move)
  2. the scene clips joined with their transitions            -> the "base" video
  3. the narration audio placed on the timeline and put on the picture (if any)
Then the existing finishing code takes over, unchanged: captions or headline (export.py), the
voice levelling (audiofx.py) and the music mix (mix.py).
"""
from pathlib import Path

from app.photostory import motion, timing
from app.photostory.manifest import Manifest, Scene, image_files
from app.photostory.timing import FPS

W, H = 1080, 1920
UPSCALE = 2                 # moving scenes are drawn from a 2x picture, so slow moves do not step
PREVIEW_SCALE = 0.25        # a preview is drawn a quarter of the size: quick, and light on memory
TO_STANDARD_RANGE = "scale=out_range=tv"    # the normal video colour range, as the rest of CocoGenie makes
XFADE = {"fade": "fade", "slide_left": "slideleft", "slide_right": "slideright", "wipe_left": "wipeleft"}


def canvas(scale: float = 1.0) -> tuple[int, int]:
    """The picture size, always even numbers (video needs that)."""
    return 2 * round(W * scale / 2), 2 * round(H * scale / 2)


def _encode(preview: bool) -> list[str]:
    if preview:
        return ["-c:v", "libx264", "-preset", "ultrafast", "-crf", "30", "-pix_fmt", "yuv420p"]
    return ["-c:v", "libx264", "-preset", "veryfast", "-crf", "16", "-pix_fmt", "yuv420p"]


def scene_filter(scene: Scene, keys: list[motion.Key], scale: float, seconds: float) -> str:
    """The filter graph for one scene, ending in the label [v]."""
    w, h = canvas(scale)
    still = len(keys) == 1
    up = 1 if still else UPSCALE
    pw, ph = w * up, h * up
    if scene.fit == "fill":          # crop the photo to fill the whole 9:16 frame
        base = f"[0:v]scale={pw}:{ph}:force_original_aspect_ratio=increase,crop={pw}:{ph},setsar=1"
    else:                            # the whole photo, fitted over a blurred, enlarged copy of itself
        radius = max(2, round(40 * scale * up))
        base = (f"[0:v]split[a][b];"
                f"[a]scale={pw}:{ph}:force_original_aspect_ratio=increase,crop={pw}:{ph},boxblur={radius}:4[bg];"
                f"[b]scale={pw}:{ph}:force_original_aspect_ratio=decrease[fg];"
                f"[bg][fg]overlay=(W-w)/2:(H-h)/2,setsar=1")
    # JPEG photos are full-range colour. Without TO_STANDARD_RANGE the video comes out labelled
    # yuvj420p, which some players and platforms show with slightly wrong colours.
    if still:
        return f"{base},fps={FPS},{TO_STANDARD_RANGE},format=yuv420p[v]"
    z, x, y = motion.zoompan_expressions(keys, FPS)
    return (f"{base},zoompan=z='{z}':x='{x}':y='{y}':d={timing.frames(seconds)}:s={w}x{h}:fps={FPS},"
            f"{TO_STANDARD_RANGE},format=yuv420p[v]")


def scene_command(scene: Scene, image_path: Path | str, out_path: Path | str, seconds: float,
                  *, preview: bool = False) -> list[str]:
    """FFmpeg command that turns one photo into a silent clip `seconds` long."""
    scale = PREVIEW_SCALE if preview else 1.0
    keys = motion.path(scene.motion, scene.intensity, seconds, scene.focus)
    cmd = ["ffmpeg", "-loglevel", "error", "-y"]
    if len(keys) == 1:               # a still picture needs the image repeated for its whole length
        cmd += ["-loop", "1", "-framerate", str(FPS)]
    cmd += ["-i", str(image_path), "-t", f"{seconds:.3f}",
            "-filter_complex", scene_filter(scene, keys, scale, seconds), "-map", "[v]", "-an",
            *_encode(preview), str(out_path)]
    return cmd


def join_graph(scenes: list[Scene]) -> str:
    """Join the scene clips: a crossfade, slide or wipe where a scene has one, a plain cut otherwise.
    Each transition starts exactly where the next scene starts, and the clips were rendered long
    enough (timing.render_lengths) to have picture on both sides of it."""
    if len(scenes) == 1:
        return "[0:v]null[v]"
    overlap, begin = timing.overlaps(scenes), timing.starts(scenes)
    # xfade only joins two streams with the SAME frame rate and timebase, and concat (a cut) returns
    # a different timebase than a rendered clip has: so every clip, and every cut, is put on one.
    parts = [f"[{i}:v]fps={FPS},settb=AVTB[n{i}]" for i in range(len(scenes))]
    cur = "n0"
    for i in range(1, len(scenes)):
        out = "v" if i == len(scenes) - 1 else f"x{i}"
        if overlap[i] == 0:
            parts.append(f"[{cur}][n{i}]concat=n=2:v=1:a=0,fps={FPS},settb=AVTB[{out}]")
        else:
            parts.append(f"[{cur}][n{i}]xfade=transition={XFADE[scenes[i].transition]}"
                         f":duration={overlap[i]:.3f}:offset={begin[i]:.3f}[{out}]")
        cur = out
    return ";".join(parts)


def join_command(clip_paths: list, scenes: list[Scene], out_path: Path | str, *,
                 preview: bool = False) -> list[str]:
    if len(clip_paths) != len(scenes):
        raise ValueError("There must be one clip per scene.")
    cmd = ["ffmpeg", "-loglevel", "error", "-y"]
    for p in clip_paths:
        cmd += ["-i", str(p)]
    return cmd + ["-filter_complex", join_graph(scenes), "-map", "[v]", "-an", *_encode(preview), str(out_path)]


def narration_command(scenes: list[Scene], audio_paths: list, out_path: Path | str) -> list[str] | None:
    """Place each scene's narration at its start on the timeline. None if nobody narrates."""
    begin = timing.starts(scenes)
    placed = [(p, b) for p, b in zip(audio_paths, begin) if p]
    if not placed:
        return None
    cmd = ["ffmpeg", "-loglevel", "error", "-y"]
    delays = []
    for k, (path, at) in enumerate(placed):
        cmd += ["-i", str(path)]
        ms = round((at + timing.LEAD_IN) * 1000)
        delays.append(f"[{k}:a]adelay={ms}|{ms}[a{k}]")
    labels = "".join(f"[a{k}]" for k in range(len(placed)))
    total = timing.total_seconds(scenes)
    # padded with silence to the full length, so the audio is exactly as long as the video
    mix = (f"{labels}amix=inputs={len(placed)}:normalize=0,apad=whole_dur={total:.3f}[a]"
           if len(placed) > 1 else f"[a0]apad=whole_dur={total:.3f}[a]")
    return cmd + ["-filter_complex", ";".join(delays + [mix]), "-map", "[a]", "-t", f"{total:.3f}",
                  "-c:a", "aac", "-b:a", "160k", str(out_path)]


def mux_command(video_path: Path | str, audio_path: Path | str, out_path: Path | str, total: float) -> list[str]:
    """Put the narration on the joined picture. The finishing code (captions, headline, music
    ducking) expects its base video to carry the voice, so this must come first."""
    return ["ffmpeg", "-loglevel", "error", "-y", "-i", str(video_path), "-i", str(audio_path),
            "-map", "0:v", "-map", "1:a", "-c:v", "copy", "-c:a", "copy", "-t", f"{total:.3f}", str(out_path)]


def build_plan(m: Manifest, project_dir: Path | str, work_dir: Path | str, *, preview: bool = False) -> dict:
    """Everything needed to render this project, worked out from the manifest alone.

    Returns the ordered FFmpeg steps plus the data the existing finishing code needs (caption words,
    headline, music). Nothing is run.
    """
    project_dir, work_dir = Path(project_dir), Path(work_dir)
    tag = "preview_" if preview else ""
    lengths = timing.render_lengths(m.scenes)
    steps, clips = [], []
    for n, (scene, seconds) in enumerate(zip(m.scenes, lengths), 1):
        clip = work_dir / f"{tag}scene_{n}.mp4"
        clips.append(clip)
        steps.append({"name": f"scene {n}", "output": str(clip),
                      "argv": scene_command(scene, project_dir / scene.image, clip, seconds, preview=preview)})
    base = work_dir / f"{tag}story_base.mp4"
    steps.append({"name": "join scenes", "output": str(base),
                  "argv": join_command(clips, m.scenes, base, preview=preview)})
    narration = work_dir / f"{tag}narration.m4a"
    audio_cmd = narration_command(
        m.scenes, [project_dir / s.narration_audio if s.narration_audio else None for s in m.scenes], narration)
    total = timing.total_seconds(m.scenes)
    if audio_cmd:
        voiced = work_dir / f"{tag}story_with_voice.mp4"
        steps.append({"name": "place narration", "output": str(narration), "argv": audio_cmd})
        steps.append({"name": "add narration", "output": str(voiced),
                      "argv": mux_command(base, narration, voiced, total)})
        base = voiced                    # from here on, the base video carries the voice
    return {
        "steps": steps, "base_video": str(base),
        "narration_audio": str(narration) if audio_cmd else None,
        "caption_words": timing.caption_words(m) if m.captions["on"] else [],
        "caption_preset": m.captions["preset"], "headline": m.headline, "music": m.music,
        "photos": image_files(m), "total_seconds": round(total, 3),
    }
