"""Animated captions: a few words at a time, the word being spoken is highlighted.

Pillow draws the frames (it shapes Hindi correctly). ffmpeg turns them into ONE
transparent caption video that export.py overlays on the clip.
"""
import shutil
import subprocess
from pathlib import Path

from PIL import Image, ImageDraw, ImageFont

# Built into macOS; has both Devanagari and English letters (needed for Hinglish)
FONT_PATH = "/System/Library/Fonts/Kohinoor.ttc"
FONT_INDEX = 3  # Bold

CANVAS_W, CANVAS_H = 1080, 360      # caption strip for a 1080x1920 video
FONT_SIZE = 84
LINE_HEIGHT = 108
MAX_TEXT_W = int(CANVAS_W * 0.88)
MAX_WORDS_PER_GROUP = 4
MAX_WORD_SECONDS = 1.5      # a word never stays highlighted longer (bad timings from Whisper)
FPS = 25

WHITE = (255, 255, 255, 255)
HIGHLIGHT = (255, 212, 0, 255)      # yellow
OUTLINE = (0, 0, 0, 255)
BREAK_AFTER = set(".,?!;:।")        # a group ends after punctuation like this


def make_groups(words: list[dict], clip_start: float, clip_end: float) -> list[list[dict]]:
    """Group the clip's words into short captions. Times are relative to the clip start."""
    ws = []
    for w in words:
        if w["start"] >= clip_start - 0.05 and w["end"] <= clip_end + 0.05:
            text = w["word"].strip()
            if text:
                ws.append({"text": text, "start": max(0.0, w["start"] - clip_start),
                           "end": w["end"] - clip_start})
    groups, cur = [], []
    for w in ws:
        if cur and (len(cur) >= MAX_WORDS_PER_GROUP or w["start"] - cur[-1]["end"] > 0.7):
            groups.append(cur)
            cur = []
        cur.append(w)
        if w["text"][-1] in BREAK_AFTER:
            groups.append(cur)
            cur = []
    if cur:
        groups.append(cur)
    return groups


def _layout(draw: ImageDraw.ImageDraw, font, words: list[str]) -> list[list[tuple[str, int]]]:
    """Split words into lines that fit; return [(word, x), ...] per line (x = left edge)."""
    space = draw.textlength(" ", font=font)
    lines, line, width = [], [], 0.0
    for w in words:
        wl = draw.textlength(w, font=font)
        if line and width + space + wl > MAX_TEXT_W:
            lines.append((line, width))
            line, width = [], 0.0
        width += (space if line else 0) + wl
        line.append((w, wl))
    lines.append((line, width))

    placed = []
    for items, total in lines:
        x = (CANVAS_W - total) / 2
        row = []
        for w, wl in items:
            row.append((w, int(x)))
            x += wl + space
        placed.append(row)
    return placed


def _render_frame(texts: list[str], active: int, out: Path) -> None:
    font = ImageFont.truetype(FONT_PATH, FONT_SIZE, index=FONT_INDEX)
    img = Image.new("RGBA", (CANVAS_W, CANVAS_H), (0, 0, 0, 0))
    draw = ImageDraw.Draw(img)
    lines = _layout(draw, font, texts)
    y = (CANVAS_H - len(lines) * LINE_HEIGHT) // 2
    n = 0
    for row in lines:
        for word, x in row:
            draw.text((x, y), word, font=font, fill=HIGHLIGHT if n == active else WHITE,
                      stroke_width=8, stroke_fill=OUTLINE)
            n += 1
        y += LINE_HEIGHT
    img.save(out)


def build_caption_track(words: list[dict], clip_start: float, clip_end: float,
                        work: Path, name: str) -> Path | None:
    """Make a transparent caption video as long as the clip. None if nobody speaks."""
    groups = make_groups(words, clip_start, clip_end)
    if not groups:
        return None
    duration = clip_end - clip_start
    tmp = work / f"caps_{name}"
    tmp.mkdir(exist_ok=True)

    blank = tmp / "blank.png"
    Image.new("RGBA", (CANVAS_W, CANVAS_H), (0, 0, 0, 0)).save(blank)

    timeline: list[tuple[Path, float]] = []   # (image, seconds on screen)
    t = 0.0

    def add(png: Path, until: float) -> None:
        nonlocal t
        if until - t >= 0.02:
            timeline.append((png, until - t))
            t = until

    for gi, group in enumerate(groups):
        texts = [w["text"].upper() for w in group]  # Latin letters in capitals, Hindi unchanged
        for wi, w in enumerate(group):
            start = max(w["start"], t)
            end = group[wi + 1]["start"] if wi + 1 < len(group) else w["end"] + 0.12
            end = min(max(end, start + 0.05), start + MAX_WORD_SECONDS, duration)
            if start >= duration:
                break
            add(blank, start)                       # silence before this word
            png = tmp / f"g{gi}_w{wi}.png"
            _render_frame(texts, wi, png)
            add(png, end)
    add(blank, duration)                            # keep the track as long as the clip

    listing = tmp / "list.txt"
    lines = []
    for png, secs in timeline:
        lines += [f"file '{png}'", f"duration {secs:.3f}"]
    lines.append(f"file '{timeline[-1][0]}'")      # concat needs the last file repeated
    listing.write_text("\n".join(lines))

    track = work / f"{name}_captions.mov"
    subprocess.run(
        ["ffmpeg", "-loglevel", "error", "-y", "-f", "concat", "-safe", "0", "-i", str(listing),
         "-vf", f"fps={FPS},format=argb", "-c:v", "qtrle", str(track)],
        check=True,
    )
    shutil.rmtree(tmp)
    return track
