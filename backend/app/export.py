"""Cut a clip out of the source video, make it vertical 9:16, and burn the captions in.

Two stages: (1) picture + voice -> clip_N_base.mp4 (no captions), (2) captions over the base ->
clip_N.mp4. Changing the caption style later only repeats stage 2.
"""
import json
import shutil
import subprocess
from pathlib import Path

from app.audiofx import voice_filter
from app.captions import render_track, strip_y, words_in_clip
from app.captionstyles import CaptionStyle, resolve
from app.framing import Plan, crop_x_expression, plan_for_clip

OUT_W, OUT_H = 1080, 1920


def video_size(video: Path) -> tuple[int, int]:
    out = subprocess.run(
        ["ffprobe", "-v", "error", "-select_streams", "v:0",
         "-show_entries", "stream=width,height", "-of", "json", str(video)],
        check=True, capture_output=True, text=True,
    ).stdout
    s = json.loads(out)["streams"][0]
    return s["width"], s["height"]


def _framing_filter(framing: str, src_w: int, src_h: int, plan: Plan | None = None) -> str:
    """Video filter that produces the 1080x1920 picture, labelled [bg]."""
    # Cropping only makes sense for landscape-ish sources.
    if framing == "crop" and src_w / src_h > OUT_W / OUT_H:
        if plan is not None and plan.mode in ("track", "static"):
            # Scale up first, then cut a 1080-wide window whose left edge follows the speaker.
            x = crop_x_expression(plan.keys, OUT_H / src_h)
            return f"[0:v]scale=-2:{OUT_H},crop={OUT_W}:{OUT_H}:x='{x}':y=0,setsar=1[bg]"
        return f"[0:v]crop=ih*9/16:ih,scale={OUT_W}:{OUT_H},setsar=1[bg]"   # plain centre crop
    # "blur": the whole picture, fitted in the middle over a blurred, enlarged copy of itself
    return (
        f"[0:v]split[a][b];"
        f"[a]scale={OUT_W}:{OUT_H}:force_original_aspect_ratio=increase,"
        f"crop={OUT_W}:{OUT_H},boxblur=40:4[blurred];"
        f"[b]scale={OUT_W}:{OUT_H}:force_original_aspect_ratio=decrease[fit];"
        f"[blurred][fit]overlay=(W-w)/2:(H-h)/2,setsar=1[bg]"
    )


def base_path(out: Path) -> Path:
    return out.with_name(out.stem + "_base.mp4")


def apply_captions(base: Path, cap_words: list[dict], style: CaptionStyle, out: Path,
                   work: Path) -> None:
    """Stage 2: lay the captions over the caption-free base clip. The sound is copied as it is."""
    duration = float(subprocess.run(
        ["ffprobe", "-v", "error", "-show_entries", "format=duration", "-of", "csv=p=0", str(base)],
        check=True, capture_output=True, text=True).stdout)
    track = render_track(cap_words, duration, style, work, out.stem)
    if track is None:                       # nobody speaks: no captions to draw
        shutil.copyfile(base, out)
        return
    cmd = ["ffmpeg", "-loglevel", "error", "-y", "-i", str(base), "-i", str(track),
           "-filter_complex",
           f"[0:v][1:v]overlay=0:{strip_y(style, OUT_H)}:eof_action=pass:format=auto[v]",
           "-map", "[v]", "-map", "0:a?", "-c:v", "libx264", "-preset", "veryfast", "-crf", "20",
           "-pix_fmt", "yuv420p", "-c:a", "copy", "-t", f"{duration:.3f}", str(out)]
    try:
        subprocess.run(cmd, check=True, capture_output=True, text=True)
    except subprocess.CalledProcessError as e:
        raise RuntimeError(f"ffmpeg failed: {e.stderr[-400:]}") from e
    finally:
        track.unlink(missing_ok=True)


def export_clip(video: Path, words: list[dict], start: float, end: float,
                out: Path, work: Path, framing: str = "crop", clean_audio: bool = True,
                style: CaptionStyle | None = None, cap_words: list[dict] | None = None) -> dict:
    """Make one finished clip from video[start:end] (the caller picks padded cut points).

    cap_words = the caption words (see captions.words_in_clip); made from `words` if not given.
    Returns how the picture was framed, e.g. {"mode": "track", ...}, plus an "audio" report.
    """
    src_w, src_h = video_size(video)
    duration = end - start
    plan = None
    if framing == "crop" and src_w / src_h > OUT_W / OUT_H:
        plan = plan_for_clip(video, start, duration, src_w, src_h)   # find the speaker's face
        if plan.mode == "blur":       # several faces too far apart: show the whole picture
            framing = "blur"
    if cap_words is None:
        cap_words = words_in_clip(words, start, end)

    # stage 1: picture + voice, no captions
    graph = _framing_filter(framing, src_w, src_h, plan).replace("[bg]", "[v]")
    audio_report = {"applied": False}
    voice = None
    if clean_audio:
        voice, audio_report = voice_filter(video, start, duration)
    if voice:
        graph += f";[0:a]{voice}[a]"
    base = base_path(out)
    cmd = ["ffmpeg", "-loglevel", "error", "-y",
           "-ss", f"{start:.3f}", "-t", f"{duration:.3f}", "-i", str(video),
           "-filter_complex", graph, "-map", "[v]", "-map", "[a]" if voice else "0:a?",
           "-t", f"{duration:.3f}",
           "-c:v", "libx264", "-preset", "veryfast", "-crf", "16", "-pix_fmt", "yuv420p",
           "-c:a", "aac", "-b:a", "160k", str(base)]
    try:
        subprocess.run(cmd, check=True, capture_output=True, text=True)
    except subprocess.CalledProcessError as e:
        raise RuntimeError(f"ffmpeg failed: {e.stderr[-400:]}") from e

    # stage 2: captions
    apply_captions(base, cap_words, style or resolve(), out, work)
    if plan is None:
        info = {"mode": framing, "reason": "portrait video or blur framing chosen"}
    else:
        info = plan.summary()
    return {**info, "audio": audio_report}
