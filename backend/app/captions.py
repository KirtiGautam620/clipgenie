"""Captions: a few words at a time, drawn in a chosen style, as one transparent video.

The caption *data* is just the clip's words with their times (cap_words). The *style* decides how
they look (see captionstyles.py). Pillow draws the frames (it shapes Hindi correctly) and FFmpeg
turns them into ONE transparent video that export.py overlays on the clip.
"""
import functools
import shutil
import subprocess
from pathlib import Path

from PIL import Image, ImageDraw, ImageFilter, ImageFont

from app.captionstyles import CaptionStyle, contrast_text, font_path, resolve

CANVAS_W, CANVAS_H = 1080, 420      # caption strip for a 1080x1920 video
MAX_TEXT_W = int(CANVAS_W * 0.88)
MAX_LINES = 2
MIN_SHRINK = 0.6                    # a long line may shrink to 60% of the chosen size, no further
MAX_WORDS_PER_GROUP = 4
MAX_WORD_SECONDS = 1.5      # a word never stays highlighted longer (bad timings from Whisper)
GROUP_PAUSE = 0.7           # a pause this long starts a new caption
LEAD = 0.04                 # captions react a touch before the voice: it feels in sync
HOLD = 0.25                 # a caption lingers a moment after its last word
FPS = 25
POP_SCALES = (1.0, 1.12, 1.16, 1.10)   # one step per frame, then it settles at POP_HOLD
POP_HOLD = 1.06
BREAK_AFTER = set(".,?!;:।")        # a group ends after punctuation like this


# ---------------------------------------------------------------- the caption data

def words_in_clip(words: list[dict], clip_start: float, clip_end: float) -> list[dict]:
    """The clip's words as [{"text", "start", "end"}] with times counted from the clip start.
    This is the editable caption data."""
    out = []
    for w in words:
        if w["start"] >= clip_start - 0.05 and w["end"] <= clip_end + 0.05:
            text = w["word"].strip()
            if text:
                start = max(0.0, w["start"] - clip_start)
                out.append({"text": text, "start": start,
                            "end": min(w["end"] - clip_start, start + MAX_WORD_SECONDS)})
    return out


def group_words(cap_words: list[dict], max_words: int = MAX_WORDS_PER_GROUP) -> list[list[dict]]:
    """Split the words into short captions: by size, by punctuation and by pauses."""
    groups, cur = [], []
    for w in cap_words:
        if cur and (len(cur) >= max_words or w["start"] - cur[-1]["end"] > GROUP_PAUSE):
            groups.append(cur)
            cur = []
        cur.append(w)
        if w["text"][-1] in BREAK_AFTER:
            groups.append(cur)
            cur = []
    if cur:
        groups.append(cur)
    return groups


def make_groups(words: list[dict], clip_start: float, clip_end: float,
                max_words: int = MAX_WORDS_PER_GROUP) -> list[list[dict]]:
    return group_words(words_in_clip(words, clip_start, clip_end), max_words)


# ---------------------------------------------------------------- drawing one frame

@functools.lru_cache(maxsize=16)
def _font(weight: str, size: int) -> ImageFont.FreeTypeFont:
    return ImageFont.truetype(str(font_path(weight)), size, layout_engine=ImageFont.Layout.RAQM)


class _Layout:
    def __init__(self, size, line_h, items, bounds):
        self.size, self.line_h = size, line_h
        self.items = items      # (word index, left x, top y, width)
        self.bounds = bounds    # (left, top, right, bottom) of all the text


@functools.lru_cache(maxsize=256)
def _layout(texts: tuple[str, ...], style: CaptionStyle) -> _Layout:
    """Fit the words into at most two lines; shrink the letters when a line is too long."""
    size = style.size
    while True:
        font = _font(style.weight, size)
        # extra room so a pill, a dark edge or a pop never crowds the next word
        space = (font.getlength(" ") + style.outline * 2 + (size * 0.28 if style.box == "pill" else 0)
                 + (size * 0.06 if style.animation == "pop" else 0))
        widths = [font.getlength(t) for t in texts]
        rows, row, row_w = [], [], 0.0
        for i, w in enumerate(widths):
            if row and row_w + space + w > MAX_TEXT_W:
                rows.append((row, row_w))
                row, row_w = [], 0.0
            row_w += (space if row else 0) + w
            row.append(i)
        rows.append((row, row_w))
        fits = len(rows) <= MAX_LINES and max(widths) <= MAX_TEXT_W
        if fits or size * 0.94 < style.size * MIN_SHRINK:
            break
        size = int(size * 0.94)

    ascent, descent = font.getmetrics()
    line_h, gap = ascent + descent, int(size * 0.12)
    top = (CANVAS_H - (len(rows) * line_h + (len(rows) - 1) * gap)) // 2
    items = []
    for r, (idxs, total) in enumerate(rows):
        x, y = (CANVAS_W - total) / 2, top + r * (line_h + gap)
        for i in idxs:
            items.append((i, int(x), y, widths[i]))
            x += widths[i] + space
    left = min(x for _, x, _, _ in items)
    right = max(x + w for _, x, _, w in items)
    return _Layout(size, line_h, items, (left, top, right, top + len(rows) * line_h + (len(rows) - 1) * gap))


@functools.lru_cache(maxsize=512)
def _word_layer(text: str, size: int, style: CaptionStyle, fill: str,
                pill: str | None) -> tuple[Image.Image, int]:
    """One word, drawn on its own transparent layer (with room around it for shadow / pill)."""
    font = _font(style.weight, size)
    ascent, descent = font.getmetrics()
    advance, pad = int(round(font.getlength(text))), int(size * 0.5)
    layer = Image.new("RGBA", (advance + 2 * pad, ascent + descent + 2 * pad), (0, 0, 0, 0))
    draw = ImageDraw.Draw(layer)
    if pill:
        px = int(size * 0.14)
        draw.rounded_rectangle((pad - px, pad + int(size * 0.02), pad + advance + px,
                                pad + ascent + descent - int(size * 0.02)),
                               radius=int(size * 0.3), fill=pill)
    if style.shadow:
        shadow = Image.new("RGBA", layer.size, (0, 0, 0, 0))
        ImageDraw.Draw(shadow).text((pad, pad + int(size * 0.06)), text, font=font,
                                    fill=(0, 0, 0, 200))
        layer = Image.alpha_composite(layer, shadow.filter(ImageFilter.GaussianBlur(size * 0.06)))
        draw = ImageDraw.Draw(layer)
    draw.text((pad, pad), text, font=font, fill=fill,
              stroke_width=style.outline, stroke_fill="#000000")
    return layer, pad


def _blend(img: Image.Image, layer: Image.Image, x: int, y: int) -> None:
    """Lay `layer` over `img` at (x, y); parts outside the picture are simply dropped."""
    left, top = max(0, -x), max(0, -y)
    right, bottom = min(layer.width, img.width - x), min(layer.height, img.height - y)
    if right <= left or bottom <= top:
        return
    region = layer.crop((left, top, right, bottom))
    box = (x + left, y + top, x + right, y + bottom)
    img.paste(Image.alpha_composite(img.crop(box), region), box[:2])


def display_text(text: str, style: CaptionStyle) -> str:
    return text.upper() if style.uppercase else text   # Hindi has no capitals: unchanged


def _render_frame(texts: list[str], active: int, scale: float, style: CaptionStyle) -> Image.Image:
    """The strip for one moment. `active` = the spoken word (-1 for none), `scale` = its pop."""
    lay = _layout(tuple(texts), style)
    img = Image.new("RGBA", (CANVAS_W, CANVAS_H), (0, 0, 0, 0))
    if style.box == "bar":
        pad = int(lay.size * 0.35)
        left, top, right, bottom = lay.bounds
        ImageDraw.Draw(img).rounded_rectangle(
            (left - pad, top - pad // 2, right + pad, bottom + pad // 2),
            radius=int(lay.size * 0.4), fill=(12, 12, 12, 160))
    for i, x, y, width in lay.items:
        is_active = i == active and style.animation != "none"
        fill, pill = style.text_color, None
        if is_active and style.box == "pill":
            pill, fill = style.highlight_color, contrast_text(style.highlight_color)
        elif is_active:
            fill = style.highlight_color
        layer, pad = _word_layer(texts[i], lay.size, style, fill, pill)
        if is_active and scale != 1.0:
            layer = layer.resize((round(layer.width * scale), round(layer.height * scale)),
                                 Image.LANCZOS)
            _blend(img, layer, round(x + width / 2 - layer.width / 2),
                   round(y + lay.line_h / 2 - layer.height / 2))
        else:
            _blend(img, layer, x - pad, y - pad)
    return img


# ---------------------------------------------------------------- the caption video

def _timeline(groups: list[list[dict]], duration: float, style: CaptionStyle) -> list[tuple]:
    """[(frame key, seconds)] covering the whole clip. Key None = nothing on screen,
    else (group, active word, pop scale)."""
    timeline, t = [], 0.0

    def add(key, until):
        nonlocal t
        until = min(until, duration)
        if until - t >= 0.02:
            timeline.append((key, until - t))
            t = until

    for gi, g in enumerate(groups):
        show_start = max(t, g[0]["start"] - LEAD)
        if show_start >= duration:
            break
        next_start = groups[gi + 1][0]["start"] - LEAD if gi + 1 < len(groups) else duration
        show_end = min(g[-1]["end"] + HOLD, max(next_start, show_start), duration)
        add(None, show_start)
        if style.animation == "none":
            add((gi, -1, 1.0), show_end)
            continue
        for wi, w in enumerate(g):
            ws = max(show_start if wi == 0 else w["start"] - LEAD, t)
            if ws >= show_end:
                break
            we = g[wi + 1]["start"] - LEAD if wi + 1 < len(g) else show_end
            we = min(max(we, ws + 0.05), show_end)
            add((gi, -1, 1.0), ws)                   # the line, before this word is reached
            if style.animation == "pop":
                for scale in POP_SCALES:
                    add((gi, wi, scale), min(we, t + 1 / FPS))
                add((gi, wi, POP_HOLD), we)
            else:
                add((gi, wi, 1.0), we)
        add((gi, -1, 1.0), show_end)
    add(None, duration)
    return timeline


def strip_y(style: CaptionStyle, video_h: int = 1920) -> int:
    """Where the top of the caption strip goes on the video."""
    return max(0, min(video_h - CANVAS_H, round(style.position / 100 * video_h - CANVAS_H / 2)))


def render_track(cap_words: list[dict], duration: float, style: CaptionStyle,
                 work: Path, name: str) -> Path | None:
    """Make a transparent caption video as long as the clip. None if nobody speaks."""
    groups = group_words(cap_words, style.words_per_line)
    if not groups:
        return None
    timeline = _timeline(groups, duration, style)
    tmp = work / f"caps_{name}"
    tmp.mkdir(exist_ok=True)
    try:
        blank = tmp / "blank.png"
        Image.new("RGBA", (CANVAS_W, CANVAS_H), (0, 0, 0, 0)).save(blank)
        files: dict[tuple, Path] = {}
        lines = []
        for key, secs in timeline:
            if key is None:
                png = blank
            else:
                if key not in files:
                    gi, active, scale = key
                    texts = [display_text(w["text"], style) for w in groups[gi]]
                    files[key] = tmp / f"f{len(files)}.png"
                    _render_frame(texts, active, scale, style).save(files[key], compress_level=1)
                png = files[key]
            lines += [f"file '{png}'", f"duration {secs:.3f}"]
        lines.append(f"file '{png}'")      # concat needs the last file repeated
        listing = tmp / "list.txt"
        listing.write_text("\n".join(lines))
        track = work / f"{name}_captions.mov"
        subprocess.run(
            ["ffmpeg", "-loglevel", "error", "-y", "-f", "concat", "-safe", "0", "-i", str(listing),
             "-vf", f"fps={FPS},format=argb", "-c:v", "qtrle", str(track)],
            check=True)
        return track
    finally:
        shutil.rmtree(tmp, ignore_errors=True)


def build_caption_track(words: list[dict], clip_start: float, clip_end: float,
                        work: Path, name: str, style: CaptionStyle | None = None) -> Path | None:
    """Caption video for a clip cut from raw transcript words."""
    return render_track(words_in_clip(words, clip_start, clip_end), clip_end - clip_start,
                        style or resolve(), work, name)


SAMPLE_WORDS = ["Your", "words", "stand", "out"]


@functools.lru_cache(maxsize=64)
def preview_png(style: CaptionStyle) -> bytes:
    """A picture of this style (same drawing code as the real captions), on a neutral backdrop.
    The page shows it while the user is choosing, before anything is re-rendered."""
    import io
    backdrop = Image.new("RGBA", (CANVAS_W, CANVAS_H))
    ImageDraw.Draw(backdrop).rectangle((0, 0, CANVAS_W, CANVAS_H), fill=(92, 98, 110, 255))
    for y in range(CANVAS_H):    # a soft vertical fade so light and dark text are both judged fairly
        shade = 70 + int(60 * y / CANVAS_H)
        ImageDraw.Draw(backdrop).line((0, y, CANVAS_W, y), fill=(shade, shade + 4, shade + 14, 255))
    texts = [display_text(w, style) for w in SAMPLE_WORDS[:max(2, min(style.words_per_line, 4))]]
    active = 1 if style.animation != "none" else -1
    scale = POP_HOLD if style.animation == "pop" else 1.0
    frame = _render_frame(texts, active, scale, style)
    out = io.BytesIO()
    Image.alpha_composite(backdrop, frame).convert("RGB").save(out, "PNG")
    return out.getvalue()
