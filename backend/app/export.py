"""Cut a clip out of the source video, make it vertical 9:16, and burn the captions in.

Two stages: (1) picture + voice -> clip_N_base.mp4 (no captions), (2) captions over the base ->
clip_N.mp4. Changing the caption style later only repeats stage 2.
"""
import json
import shutil
import subprocess
from pathlib import Path

from app.audiofx import has_audio, voice_filter
from app.captions import headline_png, headline_y, render_track, strip_y, words_in_clip
from app.captionstyles import CaptionStyle, HeadlineStyle, resolve, resolve_headline
from app.effects import zoom_filter
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


def fades_active(fades: dict | None) -> bool:
    return bool(fades) and (float(fades.get("in", 0)) > 0 or float(fades.get("out", 0)) > 0)


def _tail(base: Path, filter_graph: str, label: str, fades: dict | None, fade_audio: bool,
          duration: float) -> tuple[str, str, list[str]]:
    """The end of the text pass: (filter graph, final picture label, audio options).
    With no fades this is exactly what the pass always did (picture as drawn, sound copied).
    With fades the picture fades in/out in the same encode (no extra generation), and the sound
    fades with it unless the user turned that off (then it is re-encoded only when it must fade)."""
    if not fades_active(fades):
        return filter_graph, label, ["-c:a", "copy"]
    fin, fout = float(fades.get("in", 0)), float(fades.get("out", 0))
    video, audio = [], []
    if fin > 0:
        video.append(f"fade=t=in:st=0:d={fin:.3f}")
        audio.append(f"afade=t=in:st=0:d={fin:.3f}")
    if fout > 0:
        start = max(0.0, duration - fout)
        video.append(f"fade=t=out:st={start:.3f}:d={fout:.3f}")
        audio.append(f"afade=t=out:st={start:.3f}:d={fout:.3f}")
    filter_graph += f";[{label}]{','.join(video)}[vf]"
    if fade_audio and has_audio(base):
        return filter_graph, "vf", ["-af", ",".join(audio), "-c:a", "aac", "-b:a", "160k"]
    return filter_graph, "vf", ["-c:a", "copy"]


def _hook_card(hook: dict, work: Path, out: Path, duration: float, index: int) -> tuple[Path, str, int]:
    """The hook as a card picture: (png, filter that fades it in/out, where it sits on the video)."""
    style = resolve_headline(hook["style"].get("preset"), {k: v for k, v in hook["style"].items() if k != "preset"})
    png = work / f"{out.stem}_hook.png"
    png.write_bytes(headline_png(hook["text"], style))
    fades = f"fade=t=in:st=0:d={FADE}:alpha=1"
    if style.seconds and style.seconds < duration:
        fades += f",fade=t=out:st={style.seconds - FADE:.2f}:d={FADE}:alpha=1"
    return png, f"[{index}:v]format=rgba,{fades}[h]", headline_y(style, OUT_H)


def apply_captions(base: Path, cap_words: list[dict], style: CaptionStyle, out: Path,
                   work: Path, fades: dict | None = None, fade_audio: bool = True,
                   hook: dict | None = None) -> None:
    """Stage 2: lay the captions over the caption-free base clip. The sound is copied as it is
    (unless fades are asked for: then the picture, captions included, fades in and out).
    `hook` = {"text", "style"}: a title card shown over the first seconds, together with the captions."""
    duration = float(subprocess.run(
        ["ffprobe", "-v", "error", "-show_entries", "format=duration", "-of", "csv=p=0", str(base)],
        check=True, capture_output=True, text=True).stdout)
    track = render_track(cap_words, duration, style, work, out.stem)
    if track is None:                       # nobody speaks: no captions to draw
        apply_no_text(base, out, fades, fade_audio, hook)
        return
    overlay = f"[0:v][1:v]overlay=0:{strip_y(style, OUT_H)}:eof_action=pass:format=auto"
    inputs, card = ["-i", str(base), "-i", str(track)], None
    if hook:
        card, card_filter, card_y = _hook_card(hook, work, out, duration, 2)
        inputs += ["-loop", "1", "-framerate", "25", "-t", f"{duration:.3f}", "-i", str(card)]
        overlay += f"[c];{card_filter};[c][h]overlay=0:{card_y}:eof_action=pass:format=auto"
    graph, label, audio = _tail(base, overlay + "[v]", "v", fades, fade_audio, duration)
    cmd = ["ffmpeg", "-loglevel", "error", "-y", *inputs,
           "-filter_complex", graph,
           "-map", f"[{label}]", "-map", "0:a?", "-c:v", "libx264", "-preset", "veryfast", "-crf", "20",
           "-pix_fmt", "yuv420p", *audio, "-t", f"{duration:.3f}", str(out)]
    try:
        subprocess.run(cmd, check=True, capture_output=True, text=True)
    except subprocess.CalledProcessError as e:
        raise RuntimeError(f"ffmpeg failed: {e.stderr[-400:]}") from e
    finally:
        track.unlink(missing_ok=True)
        if card:
            card.unlink(missing_ok=True)


FADE = 0.35


def _duration(media: Path) -> float:
    return float(subprocess.run(
        ["ffprobe", "-v", "error", "-show_entries", "format=duration", "-of", "csv=p=0", str(media)],
        check=True, capture_output=True, text=True).stdout)


def apply_headline(base: Path, text: str, style: HeadlineStyle, out: Path, work: Path,
                   fades: dict | None = None, fade_audio: bool = True) -> None:
    """Stage 2 alternative: lay a headline card over the caption-free base clip. It fades in, stays
    for style.seconds (0 = the whole clip) and fades out. The sound is copied as it is
    (unless the whole picture is asked to fade)."""
    duration = _duration(base)
    png = work / f"{out.stem}_headline.png"
    png.write_bytes(headline_png(text, style))
    card_fades = f"fade=t=in:st=0:d={FADE}:alpha=1"
    if style.seconds and style.seconds < duration:
        card_fades += f",fade=t=out:st={style.seconds - FADE:.2f}:d={FADE}:alpha=1"
    graph, label, audio = _tail(
        base, f"[1:v]format=rgba,{card_fades}[h];[0:v][h]overlay=0:{headline_y(style, OUT_H)}:eof_action=pass:format=auto[v]",
        "v", fades, fade_audio, duration)
    cmd = ["ffmpeg", "-loglevel", "error", "-y", "-i", str(base),
           "-loop", "1", "-framerate", "25", "-t", f"{duration:.3f}", "-i", str(png),
           "-filter_complex", graph,
           "-map", f"[{label}]", "-map", "0:a?", "-c:v", "libx264", "-preset", "veryfast", "-crf", "20",
           "-pix_fmt", "yuv420p", *audio, "-t", f"{duration:.3f}", str(out)]
    try:
        subprocess.run(cmd, check=True, capture_output=True, text=True)
    except subprocess.CalledProcessError as e:
        raise RuntimeError(f"ffmpeg failed: {e.stderr[-400:]}") from e
    finally:
        png.unlink(missing_ok=True)


def apply_no_text(base: Path, out: Path, fades: dict | None = None, fade_audio: bool = True,
                  hook: dict | None = None) -> None:
    """The finished clip with no captions: the caption-free base, as it is (or, when fades or a hook
    are asked for, the same picture with them added in one encode)."""
    if not fades_active(fades) and not hook:
        shutil.copyfile(base, out)
        return
    duration = _duration(base)
    inputs, card, source = ["-i", str(base)], None, "[0:v]null[v]"
    if hook:
        card, card_filter, card_y = _hook_card(hook, out.parent, out, duration, 1)
        inputs += ["-loop", "1", "-framerate", "25", "-t", f"{duration:.3f}", "-i", str(card)]
        source = f"{card_filter};[0:v][h]overlay=0:{card_y}:eof_action=pass:format=auto[v]"
    graph, label, audio = _tail(base, source, "v", fades, fade_audio, duration)
    cmd = ["ffmpeg", "-loglevel", "error", "-y", *inputs, "-filter_complex", graph,
           "-map", f"[{label}]", "-map", "0:a?", "-c:v", "libx264", "-preset", "veryfast", "-crf", "18",
           "-pix_fmt", "yuv420p", *audio, "-t", f"{duration:.3f}", str(out)]
    try:
        subprocess.run(cmd, check=True, capture_output=True, text=True)
    except subprocess.CalledProcessError as e:
        raise RuntimeError(f"ffmpeg failed: {e.stderr[-400:]}") from e
    finally:
        if card:
            card.unlink(missing_ok=True)


def _select(spans: list[tuple[float, float]]) -> str:
    """Filter expression that keeps only these (start, end) spans of the clip, in seconds."""
    return "+".join(f"between(t\\,{a:.3f}\\,{b:.3f})" for a, b in spans)


def render_base(video: Path, start: float, end: float, base: Path, framing: str = "crop",
                clean_audio: bool = True, effects: dict | None = None,
                segments: list[tuple[float, float]] | None = None) -> dict:
    """Stage 1 alone: picture (framed, with the optional zoom/pan effect) + voice, no captions.
    `segments` = the (start, end) parts of video[start:end] to keep, in source seconds; the gaps
    between them (pauses) are removed. None keeps everything.
    Writes `base`. Returns how the picture was framed plus an "audio" report."""
    src_w, src_h = video_size(video)
    duration = end - start
    plan = None
    if framing == "crop" and src_w / src_h > OUT_W / OUT_H:
        plan = plan_for_clip(video, start, duration, src_w, src_h)   # find the speaker's face
        if plan.mode == "blur":       # several faces too far apart: show the whole picture
            framing = "blur"

    spans = [(a - start, b - start) for a, b in segments] if segments else None
    out_duration = sum(b - a for a, b in spans) if spans else duration
    effect = zoom_filter(effects, out_duration, OUT_W, OUT_H)

    # the picture: framed first (the speaker tracking works in the clip's own time), then the
    # removed parts are dropped, then zoom/pan runs over the finished timeline
    steps = []
    if spans:
        steps.append(f"fps=25,select={_select(spans)},setpts=N/(25*TB)")
    if effect:
        steps.append(f"{effect},setsar=1")
    graph = _framing_filter(framing, src_w, src_h, plan).replace("[bg]", "[vf]" if steps else "[v]")
    if steps:
        graph += f";[vf]{','.join(steps)}[v]"

    audio_report = {"applied": False}
    voice = None
    if clean_audio:
        voice, audio_report = voice_filter(video, start, duration, out_duration)
    pieces = []
    if spans and (voice or has_audio(video)):
        pieces.append(f"aselect={_select(spans)},asetpts=N/SR/TB")
    if voice:
        pieces.append(voice)
    if pieces:
        graph += f";[0:a]{','.join(pieces)}[a]"
    cmd = ["ffmpeg", "-loglevel", "error", "-y",
           "-ss", f"{start:.3f}", "-t", f"{duration:.3f}", "-i", str(video),
           "-filter_complex", graph, "-map", "[v]", "-map", "[a]" if pieces else "0:a?",
           "-t", f"{out_duration:.3f}",
           "-c:v", "libx264", "-preset", "veryfast", "-crf", "16", "-pix_fmt", "yuv420p",
           "-c:a", "aac", "-b:a", "160k", str(base)]
    try:
        subprocess.run(cmd, check=True, capture_output=True, text=True)
    except subprocess.CalledProcessError as e:
        raise RuntimeError(f"ffmpeg failed: {e.stderr[-400:]}") from e
    if plan is None:
        info = {"mode": framing, "reason": "portrait video or blur framing chosen"}
    else:
        info = plan.summary()
    return {**info, "audio": audio_report}


def export_clip(video: Path, words: list[dict], start: float, end: float,
                out: Path, work: Path, framing: str = "crop", clean_audio: bool = True,
                style: CaptionStyle | None = None, cap_words: list[dict] | None = None,
                effects: dict | None = None) -> dict:
    """Make one finished clip from video[start:end] (the caller picks padded cut points).

    cap_words = the caption words (see captions.words_in_clip); made from `words` if not given.
    effects = optional zoom/pan (see effects.py). Returns how the picture was framed, e.g.
    {"mode": "track", ...}, plus an "audio" report.
    """
    if cap_words is None:
        cap_words = words_in_clip(words, start, end)
    info = render_base(video, start, end, base_path(out), framing, clean_audio, effects)   # stage 1
    apply_captions(base_path(out), cap_words, style or resolve(), out, work)                # stage 2
    return info
