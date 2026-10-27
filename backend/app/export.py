"""Cut a clip out of the source video, make it vertical 9:16, and burn the captions in."""
import json
import subprocess
from pathlib import Path

from app.captions import build_caption_track

OUT_W, OUT_H = 1080, 1920
CAPTION_Y = "H*0.58"   # captions sit in the lower middle, above the YouTube Shorts buttons


def video_size(video: Path) -> tuple[int, int]:
    out = subprocess.run(
        ["ffprobe", "-v", "error", "-select_streams", "v:0",
         "-show_entries", "stream=width,height", "-of", "json", str(video)],
        check=True, capture_output=True, text=True,
    ).stdout
    s = json.loads(out)["streams"][0]
    return s["width"], s["height"]


def _framing_filter(framing: str, src_w: int, src_h: int) -> str:
    """Video filter that produces the 1080x1920 picture, labelled [bg]."""
    # Centre crop only makes sense for landscape-ish sources.
    if framing == "crop" and src_w / src_h > OUT_W / OUT_H:
        return f"[0:v]crop=ih*9/16:ih,scale={OUT_W}:{OUT_H},setsar=1[bg]"
    # "blur": the whole picture, fitted in the middle over a blurred, enlarged copy of itself
    return (
        f"[0:v]split[a][b];"
        f"[a]scale={OUT_W}:{OUT_H}:force_original_aspect_ratio=increase,"
        f"crop={OUT_W}:{OUT_H},boxblur=40:4[blurred];"
        f"[b]scale={OUT_W}:{OUT_H}:force_original_aspect_ratio=decrease[fit];"
        f"[blurred][fit]overlay=(W-w)/2:(H-h)/2,setsar=1[bg]"
    )


def export_clip(video: Path, words: list[dict], start: float, end: float,
                out: Path, work: Path, framing: str = "crop") -> None:
    src_w, src_h = video_size(video)
    duration = end - start
    captions = build_caption_track(words, start, end, work, out.stem)

    cmd = ["ffmpeg", "-loglevel", "error", "-y",
           "-ss", f"{start:.2f}", "-t", f"{duration:.2f}", "-i", str(video)]
    graph = _framing_filter(framing, src_w, src_h)
    if captions:
        cmd += ["-i", str(captions)]
        graph += f";[bg][1:v]overlay=0:{CAPTION_Y}:eof_action=pass:format=auto[v]"
    else:
        graph = graph.replace("[bg]", "[v]")
    cmd += ["-filter_complex", graph, "-map", "[v]", "-map", "0:a?",
            "-t", f"{duration:.2f}",
            "-c:v", "libx264", "-preset", "veryfast", "-crf", "20", "-pix_fmt", "yuv420p",
            "-c:a", "aac", "-b:a", "160k", str(out)]
    try:
        subprocess.run(cmd, check=True, capture_output=True, text=True)
    except subprocess.CalledProcessError as e:
        raise RuntimeError(f"ffmpeg failed: {e.stderr[-400:]}") from e
    finally:
        if captions:
            captions.unlink(missing_ok=True)
