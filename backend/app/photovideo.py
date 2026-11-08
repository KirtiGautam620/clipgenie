"""Photo videos (MVP): several photos + one song + one line of text per photo -> one 9:16 MP4.

Each photo is shown for an equal share of a part of the song: the song file may be long (up to 30 minutes),
and the user picks where the video's part starts. The video uses at most 3 minutes from that point. A line of text (if the line is not blank) is drawn
on that photo with the same "Plain" headline look as the shorts. Nothing here calls a model or the network.

Files live in data/photovideos/<id>/: the uploaded photos and song, the rendered video, and project.json
(which holds the status, so a page reload or a restart can still show what happened).
"""
import json
import re
import shutil
import subprocess
import uuid
from datetime import datetime, timezone
from pathlib import Path

import math

from app import captions, captionstyles, cuts, lyrics
from app.config import DATA_DIR
from app.photostory import ingest

PROJECTS_DIR = DATA_DIR / "photovideos"
MAX_PHOTOS = 30
MIN_SECONDS = 3.0                         # the shortest song that can be used at all
SHORT_MIN, SHORT_MAX, SHORT_DEFAULT = 30.0, 60.0, 60.0   # the video's length: 30 to 60 seconds
MAX_SONG_SECONDS = 1800.0                 # the song file itself may be up to 30 minutes
MIN_PER_PHOTO = 1.5                       # no photo is shown for less time than this
AUDIO_SUFFIXES = {".mp3", ".wav", ".m4a", ".ogg", ".flac", ".aac"}
W, H, FPS = 1080, 1920, 25
TEXT_STYLE_PRESET = "handwritten"         # thin hand-drawn capitals (Caveat)
DEVANAGARI = re.compile(r"[\u0900-\u097F]")   # Caveat has no Devanagari: such lines use the Plain look (Poppins)
DEVANAGARI_FALLBACK_PRESET = "plain"
# How a photo comes in: a hard cut, a fade from black, or a slide in from one side.
TRANSITIONS = ("cut", "fade", "slide_left", "slide_right", "slide_top", "slide_bottom", "dice")
DICE_GRID = 3                              # the dice transition: the new photo lands in a 3 x 3 grid of tiles
LEGACY_TRANSITIONS = {"slide": "slide_right"}          # saved projects used to say just "slide"
SPEEDS = {"slow": 1.0, "medium": 0.6, "fast": 0.3}     # seconds each move takes
MOTIONS = ("none", "left", "right", "top", "bottom")   # which side the TEXT comes in from
FRAMES = ("none", "white", "black")        # a border round the photo
FRAME_COLOURS = {"white": "white", "black": "black"}
FRAME_PX = 24


def _now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def _folder(project_id: str) -> Path:
    if not (len(project_id) == 12 and all(c in "0123456789abcdef" for c in project_id)):
        raise ValueError("Unknown photo video.")
    return PROJECTS_DIR / project_id


def read(project_id: str) -> dict:
    path = _folder(project_id) / "project.json"
    if not path.exists():
        raise ValueError("Unknown photo video.")
    return json.loads(path.read_text())


def _write(folder: Path, data: dict) -> None:
    tmp = folder / "project.json.tmp"
    tmp.write_text(json.dumps(data, ensure_ascii=False, indent=2))
    tmp.replace(folder / "project.json")


def parse_lines(raw: str, photo_count: int) -> list[str]:
    """One line per photo, in order. A blank line means that photo shows no text.
    Trailing blank lines are ignored. Raises ValueError if there are more lines than photos."""
    lines = [line.strip() for line in (raw or "").splitlines()]
    while lines and not lines[-1]:
        lines.pop()
    if len(lines) > photo_count:
        raise ValueError(f"You wrote {len(lines)} lines for {photo_count} "
                         f"photo{'' if photo_count == 1 else 's'}. Use one line per photo, or fewer lines.")
    return lines


def plan_seconds(total: float, photo_count: int) -> list[float]:
    """Equal shares of the song for each photo, rounded to 0.01 s; the last photo takes the rounding."""
    share = round(total / photo_count, 2)
    times = [share] * (photo_count - 1)
    times.append(round(total - share * (photo_count - 1), 2))
    return times


def create(photos: list[tuple[bytes, str]], song: tuple[bytes, str], raw_lines: str,
           rights_confirmed: bool, song_start: float = 0.0, video_seconds: float = SHORT_DEFAULT,
           lyrics_text: str = "") -> dict:
    """Check the inputs, save them, and write project.json. With lyrics the status is 'timing' (the song
    is listened to next); otherwise 'queued'. Rendering is a separate step."""
    if not rights_confirmed:
        raise ValueError("Please confirm you have the right to use these photos and this song.")
    if not photos:
        raise ValueError("Add at least one photo.")
    if len(photos) > MAX_PHOTOS:
        raise ValueError(f"Use at most {MAX_PHOTOS} photos.")
    song_bytes, song_name = song
    suffix = Path(song_name).suffix.lower()
    if suffix not in AUDIO_SUFFIXES:
        raise ValueError("The song must be an MP3, WAV, M4A, OGG, FLAC or AAC file.")
    song_lyrics = lyrics.lyric_lines(lyrics_text)[:400]
    lines = [] if song_lyrics else parse_lines(raw_lines, len(photos))   # lyrics replace the per-photo lines
    for line in lines:
        if line:
            captionstyles.clean_headline(line)            # same length and content rules as a headline

    project_id = uuid.uuid4().hex[:12]
    folder = PROJECTS_DIR / project_id
    (folder / "input").mkdir(parents=True, exist_ok=True)
    try:
        saved = []
        for i, (data, name) in enumerate(photos, start=1):
            dest = folder / "input" / f"photo_{i:02d}.jpg"
            info = ingest.normalize_image(data, dest)     # refuses files that are not photos
            saved.append({"file": dest.name, "name": Path(name).name[:80], "width": info["width"],
                          "height": info["height"], "transition": "cut", "transition_speed": "medium",
                          "text_motion": "none", "text_speed": "medium", "frame": "none"})
        song_file = folder / "input" / f"song{suffix}"
        song_file.write_bytes(song_bytes)
        total = cuts.probe_duration(song_file)
    except Exception:
        shutil.rmtree(folder, ignore_errors=True)
        raise
    try:
        if total < MIN_SECONDS:
            raise ValueError(f"The song must be at least {MIN_SECONDS:.0f} seconds long.")
        if total > MAX_SONG_SECONDS:
            raise ValueError(f"The song must be at most {MAX_SONG_SECONDS / 60:.0f} minutes long.")
        if not (0 <= song_start < total):             # also refuses NaN and infinity
            raise ValueError("The start point is outside the song. Choose a part that is inside it.")
        if not (SHORT_MIN <= video_seconds <= SHORT_MAX):
            raise ValueError(f"The video must be {SHORT_MIN:.0f} to {SHORT_MAX:.0f} seconds long.")
        length = min(total - song_start, video_seconds)
        if length < SHORT_MIN:
            raise ValueError(f"Less than {SHORT_MIN:.0f} seconds of the song is left from that point. "
                             "Choose an earlier start.")
        if length / len(photos) < MIN_PER_PHOTO:
            raise ValueError("That part of the song is too short for this many photos. "
                             "Use fewer photos or a longer part.")
    except ValueError:
        shutil.rmtree(folder, ignore_errors=True)
        raise

    lines_full = lines + [""] * (len(photos) - len(lines))
    data = {"id": project_id, "status": "timing" if song_lyrics else "queued", "created_at": _now(), "error": None,
            "lyrics": song_lyrics,                         # the lyric lines, in order (empty = no lyrics)
            "song": Path(song_name).name[:80], "song_file": song_file.name,
            "song_seconds": round(length, 2),              # the length of the video (the part used)
            "song_start": round(song_start, 2),            # where that part starts in the song
            "song_total_seconds": round(total, 2),
            "photos": [{**p, "text": lines_full[i]} for i, p in enumerate(saved)],
            "rights_confirmed": True}
    _write(folder, data)
    return data


def _preset_for(text: str) -> str:
    return DEVANAGARI_FALLBACK_PRESET if DEVANAGARI.search(text) else TEXT_STYLE_PRESET


def _text_png(folder: Path, index: int, text: str) -> Path:
    style = captionstyles.resolve_headline(_preset_for(text), {})
    path = folder / "input" / f"text_{index:02d}.png"
    path.write_bytes(captions.headline_png(text, style))
    return path


def _cue_png(folder: Path, index: int, text: str) -> Path:
    style = captionstyles.resolve_headline(_preset_for(text), {})
    path = folder / "input" / f"cue_{index:03d}.png"
    path.write_bytes(captions.headline_png(text, style))
    return path


def _picture(frame: str) -> str:
    """Scale and crop a photo to fill the frame, with an optional border."""
    b = FRAME_PX if frame in FRAME_COLOURS else 0
    iw, ih = W - 2 * b, H - 2 * b
    return (f"scale={iw}:{ih}:force_original_aspect_ratio=increase,crop={iw}:{ih},"
            f"pad={W}:{H}:{b}:{b}:color={FRAME_COLOURS.get(frame, 'black')},setsar=1,format=yuv420p")


def _dice_alpha(seconds: float) -> str:
    """How much of the new photo shows at each moment, per tile (0 = hidden, 255 = shown). Tiles are
    numbered 0..8 across the grid; each one starts in a different order (so it is not a plain wipe) and
    takes 30% of the transition to fill in."""
    n = DICE_GRID
    tile = f"(floor(X*{n}/W)+{n}*floor(Y*{n}/H))"
    start = f"({seconds:.3f}*0.7*mod({tile}*5,{n * n})/{n * n - 1})"
    return f"255*clip((T-{start})/({seconds:.3f}*0.3),0,1)"


def _enter(direction: str, seconds: float, base_x: str, base_y: str) -> tuple[str, str]:
    """Where something is at each moment while it moves in from `direction` over `seconds`.
    It starts just off that edge of the frame and eases to its place (fast first, then slowing)."""
    if direction == "none" or seconds <= 0:
        return base_x, base_y
    q = f"(1-(1-min(t/{seconds:.2f},1))^2)"             # 0 at the start, 1 when it has arrived
    if direction == "right":
        return f"{base_x}+{W}*(1-{q})", base_y
    if direction == "left":
        return f"{base_x}-{W}*(1-{q})", base_y
    if direction == "bottom":
        return base_x, f"{base_y}+{H}*(1-{q})"
    if direction == "top":
        return base_x, f"{base_y}-{H}*(1-{q})"
    raise ValueError(f"Unknown direction: {direction}")


def _command(folder: Path, data: dict, out: Path) -> list[str]:
    photos = data["photos"]
    times = data.get("photo_times") or plan_seconds(data["song_seconds"], len(photos))
    cmd = ["ffmpeg", "-hide_banner", "-loglevel", "error", "-y"]
    n_inputs = 0

    def add(path: Path, seconds: float) -> int:          # a still picture for `seconds`
        nonlocal n_inputs
        cmd.extend(["-loop", "1", "-framerate", str(FPS), "-t", f"{seconds:.2f}", "-i", str(path)])
        n_inputs += 1
        return n_inputs - 1

    for p, seconds in zip(photos, times):
        add(folder / "input" / p["file"], seconds)
    text_index = {}
    for i, p in enumerate(photos):
        if p["text"]:
            text_index[i] = add(_text_png(folder, i + 1, p["text"]), times[i])
    cue_index = []                                       # lyric lines: each one is a picture shown for its time
    for k, cue in enumerate(data.get("cues") or []):
        style = captionstyles.resolve_headline(_preset_for(cue["text"]), {})
        cue_index.append((add(_cue_png(folder, k, cue["text"]), cue["end"]), cue["start"], cue["end"],
                          captions.headline_y(style, H)))
    cmd += ["-i", str(folder / "input" / data["song_file"])]
    song_input = n_inputs
    n_inputs += 1
    style = captionstyles.resolve_headline(TEXT_STYLE_PRESET, {})
    y = captions.headline_y(style, H)

    parts = []
    for i, p in enumerate(photos):
        transition = LEGACY_TRANSITIONS.get(p.get("transition", "cut"), p.get("transition", "cut"))
        if transition in ("dice",) or transition.startswith("slide"):
            if i == 0:
                transition = "cut"                       # nothing to slide or land over
        seconds = min(SPEEDS.get(p.get("transition_speed", "medium"), SPEEDS["medium"]), times[i] / 3)
        parts.append(f"[{i}:v]{_picture(p.get('frame', 'none'))}[p{i}]")
        src = f"p{i}"
        if transition.startswith("slide"):
            # the previous photo stays still while this one slides in from its side over it
            base = add(folder / "input" / photos[i - 1]["file"], times[i])
            direction = transition.split("_", 1)[1]
            x, yy = _enter(direction, seconds, "0", "0")
            parts.append(f"[{base}:v]{_picture(photos[i - 1].get('frame', 'none'))}[b{i}]")
            parts.append(f"[b{i}][p{i}]overlay=x='{x}':y='{yy}':shortest=1[s{i}]")
            src = f"s{i}"
        elif transition == "fade":
            parts.append(f"[p{i}]fade=t=in:st=0:d={seconds:.2f}[f{i}]")
            src = f"f{i}"
        elif transition == "dice":
            # the previous photo stays; the new one shows tile by tile, each tile in its own moment
            # only the transition itself gets the tile effect (it is slow); the rest of the photo is plain
            base = add(folder / "input" / photos[i - 1]["file"], times[i])
            cut_at = f"{seconds:.3f}"
            parts.append(f"[{base}:v]{_picture(photos[i - 1].get('frame', 'none'))}[b{i}]")
            parts.append(f"[p{i}]split=2[pa{i}][pb{i}]")
            parts.append(f"[pa{i}]trim=end={cut_at},setpts=PTS-STARTPTS,format=rgba,"
                         f"geq=r='r(X,Y)':g='g(X,Y)':b='b(X,Y)':a='{_dice_alpha(seconds)}'[da{i}]")
            parts.append(f"[b{i}]trim=end={cut_at},setpts=PTS-STARTPTS[bb{i}]")
            parts.append(f"[bb{i}][da{i}]overlay=0:0:format=auto,format=yuv420p[ds{i}]")
            parts.append(f"[pb{i}]trim=start={cut_at},setpts=PTS-STARTPTS[dr{i}]")
            parts.append(f"[ds{i}][dr{i}]concat=n=2:v=1:a=0[s{i}]")
            src = f"s{i}"
        if i in text_index:
            parts.append(f"[{text_index[i]}:v]format=rgba[t{i}]")
            motion = p.get("text_motion", "none")
            text_seconds = min(SPEEDS.get(p.get("text_speed", "medium"), SPEEDS["medium"]), times[i] / 3)
            tx, ty = _enter(motion, text_seconds, "(W-w)/2", str(y))
            parts.append(f"[{src}][t{i}]overlay=x='{tx}':y='{ty}':format=auto[v{i}]")
        else:
            parts.append(f"[{src}]null[v{i}]")
    joined = "".join(f"[v{i}]" for i in range(len(photos)))
    parts.append(f"{joined}concat=n={len(photos)}:v=1:a=0[vcat]")
    last = "vcat"
    for k, (idx, start, stop, cue_y) in enumerate(cue_index):   # each lyric line shows only while it is sung
        parts.append(f"[{idx}:v]format=rgba[cr{k}]")
        parts.append(f"[{last}][cr{k}]overlay=x='(W-w)/2':y='{cue_y}':"
                     f"enable='between(t,{start:.2f},{stop:.2f})':format=auto[cv{k}]")
        last = f"cv{k}"
    parts.append(f"[{last}]format=yuv420p[vout]")
    total = data["song_seconds"]
    start = data.get("song_start", 0.0)            # projects made before song parts existed start at 0
    parts.append(f"[{song_input}:a]atrim=start={start:.2f}:duration={total:.2f},asetpts=PTS-STARTPTS,"
                 f"afade=t=out:st={max(0, total - 1.5):.2f}:d=1.5[aout]")
    cmd += ["-filter_complex", ";".join(parts), "-map", "[vout]", "-map", "[aout]",
            "-t", f"{total:.2f}", "-r", str(FPS), "-c:v", "libx264", "-preset", "veryfast", "-crf", "20",
            "-pix_fmt", "yuv420p", "-c:a", "aac", "-b:a", "192k", "-movflags", "+faststart", str(out)]
    return cmd


def change_photo(project_id: str, index: int, text: str | None = None, transition: str | None = None,
                 frame: str | None = None, transition_speed: str | None = None,
                 text_motion: str | None = None, text_speed: str | None = None) -> dict:
    """Change one photo: its text and how the text comes in, how the photo comes in, or its frame.
    Marks the video for a new render."""
    return change_photos(project_id, [{"index": index, "text": text, "transition": transition, "frame": frame,
                                       "transition_speed": transition_speed, "text_motion": text_motion,
                                       "text_speed": text_speed}])


def change_photos(project_id: str, changes: list[dict], order: list[int] | None = None,
                  durations: list[float] | None = None) -> dict:
    """Apply several photo changes at once and mark the video for ONE new render. Each change has an
    "index" (1-based, the order BEFORE this call) and any of: text, transition, frame, transition_speed,
    text_motion, text_speed. A field left as None is kept. `order` (optional) is the new order of the
    photos as their old numbers, e.g. [2, 1, 3] puts photo 2 first. Everything is checked before anything
    is saved."""
    if not changes and order is None and durations is None:
        raise ValueError("Nothing to change.")
    data = read(project_id)
    photos = data["photos"]
    for change in changes:
        index = change["index"]
        if isinstance(index, bool) or not isinstance(index, int) or not 1 <= index <= len(photos):
            raise ValueError(f"There is no photo {index}. This video has {len(photos)}.")
        photo = photos[index - 1]
        text = change.get("text")
        if text is not None:
            cleaned = text.strip()
            if cleaned:
                captionstyles.clean_headline(cleaned)        # same rules as a headline
            photo["text"] = cleaned
        transition = change.get("transition")
        if transition is not None:
            transition = LEGACY_TRANSITIONS.get(transition, transition)
            if transition not in TRANSITIONS:
                raise ValueError(f"The transition must be one of: {', '.join(TRANSITIONS)}.")
            photo["transition"] = transition
        if change.get("transition_speed") is not None:
            photo["transition_speed"] = _speed(change["transition_speed"])
        if change.get("text_motion") is not None:
            if change["text_motion"] not in MOTIONS:
                raise ValueError(f"The text must come in from one of: {', '.join(MOTIONS)}.")
            photo["text_motion"] = change["text_motion"]
        if change.get("text_speed") is not None:
            photo["text_speed"] = _speed(change["text_speed"])
        if change.get("frame") is not None:
            if change["frame"] not in FRAMES:
                raise ValueError(f"The frame must be one of: {', '.join(FRAMES)}.")
            photo["frame"] = change["frame"]
    if order is not None:
        if data.get("timing"):
            raise ValueError("Lyric videos keep their photo order, because the lyrics are timed to it.")
        if sorted(order) != list(range(1, len(photos) + 1)):
            raise ValueError(f"The new order must list each photo 1 to {len(photos)} once.")
        data["photos"] = [photos[n - 1] for n in order]
    if durations is not None:
        if data.get("timing"):
            raise ValueError("Lyric videos keep their photo lengths, because the lyrics are timed to them.")
        if len(durations) != len(data["photos"]):
            raise ValueError(f"Give a length for each of the {len(data['photos'])} photos.")
        for d in durations:
            if isinstance(d, bool) or not isinstance(d, (int, float)) or not math.isfinite(d) or d < MIN_PER_PHOTO:
                raise ValueError(f"Each photo shows for at least {MIN_PER_PHOTO} seconds.")
        total = data["song_seconds"]
        if abs(sum(durations) - total) > 0.05:
            raise ValueError(f"The photo lengths must add up to {total:.1f} seconds.")
        data["photo_times"] = [round(float(d), 2) for d in durations]
    data.update(status="queued", error=None, version=data.get("version", 0) + 1)
    _write(_folder(project_id), data)
    return data


def _speed(value: str) -> str:
    if value not in SPEEDS:
        raise ValueError(f"The speed must be one of: {', '.join(SPEEDS)}.")
    return value


def render(project_id: str) -> None:
    """Make the MP4 for a queued project. Sets status to 'done' or 'failed' (with a readable error)."""
    from app.pipeline import heavy_job_lock     # one heavy job at a time on this 8 GB machine
    folder = _folder(project_id)
    data = read(project_id)
    if data.get("status") in ("timing", "timed"):
        return                                  # lyrics are being timed, or are waiting for the user to check
    if not heavy_job_lock.acquire(blocking=False):
        data.update(status="failed", error="Another video is being made right now. Try again in a moment.")
        _write(folder, data)
        return
    try:
        data.update(status="rendering", error=None)
        _write(folder, data)
        out = folder / "video.mp4"
        cmd = _command(folder, data, out)
        result = subprocess.run(cmd, capture_output=True, text=True)
        if result.returncode != 0 or not out.exists() or out.stat().st_size == 0:
            tail = (result.stderr or "").strip().splitlines()[-3:]
            raise RuntimeError("FFmpeg could not make the video: " + " | ".join(tail))
        data.update(status="done", error=None, seconds=round(cuts.probe_duration(out), 2))
    except Exception as e:
        data.update(status="failed", error=str(e)[:500])
    finally:
        heavy_job_lock.release()
        _write(folder, data)


def photo_path(project_id: str, name: str) -> Path:
    """The saved picture of one photo in this project (only a photo the project has)."""
    data = read(project_id)
    if name not in {p["file"] for p in data["photos"]}:
        raise ValueError("This project has no such photo.")
    return _folder(project_id) / "input" / name


def video_path(project_id: str) -> Path:
    path = _folder(project_id) / "video.mp4"
    if not path.exists():
        raise ValueError("This video is not ready yet.")
    return path


def time_lyrics(project_id: str) -> None:
    """Listen to the song, match each lyric line to the words heard, and stop at 'timed' so the user
    can check the times. Runs in the background; sets 'failed' with a readable error if it cannot."""
    from app.pipeline import heavy_job_lock
    from app.transcribe import transcribe
    folder = _folder(project_id)
    data = read(project_id)
    if not heavy_job_lock.acquire(blocking=False):
        data.update(status="failed", error="Another video is being made right now. Try again in a moment.")
        _write(folder, data)
        return
    try:
        work = folder / "timing"
        work.mkdir(exist_ok=True)
        result = transcribe(folder / "input" / data["song_file"], work)
        found = lyrics.match_lines(data["lyrics"], lyrics.heard_words(result["segments"]))
        times = lyrics.fill_gaps(found, data["song_total_seconds"])
        data["timing"] = {"source": "auto", "lines": [
            {"text": t, "start": s, "heard": f is not None}
            for t, s, f in zip(data["lyrics"], times, found)]}
        data.update(status="timed", error=None)
    except Exception as e:                                # NoSpeechError has a readable message already
        data.update(status="failed", error=f"The lyrics could not be timed. {e}"[:500])
    finally:
        heavy_job_lock.release()
        shutil.rmtree(folder / "timing", ignore_errors=True)
        _write(folder, data)


def set_timing(project_id: str, starts: list[float]) -> dict:
    """Save the lyric times the user checked, and plan the photo changes from them. The photos
    change on the lyric lines nearest their share of the video, and show the line that starts them."""
    data = read(project_id)
    timing = data.get("timing")
    if data.get("status") != "timed" or not timing:
        raise ValueError("The lyrics are not timed yet.")
    lines = timing["lines"]
    if len(starts) != len(lines):
        raise ValueError("The times do not match the lyric lines. Reload the page and try again.")
    clean = []
    for t in starts:
        if isinstance(t, bool) or not isinstance(t, (int, float)) or not math.isfinite(t) \
                or t < 0 or t > data["song_total_seconds"]:
            raise ValueError("Each lyric line needs a time inside the song.")
        clean.append(round(float(t), 2))
    if any(later < earlier for earlier, later in zip(clean, clean[1:])):
        raise ValueError("The lines must be in order: a line cannot start before the line above it.")

    begin, end = data["song_start"], data["song_start"] + data["song_seconds"]
    photo_at = lyrics.photo_starts(clean, len(data["photos"]), begin, end)
    # every lyric line is on screen at its checked time (lines not heard use an estimated time, shown
    # as "estimated" on the check page); the photos themselves carry no text
    data["cues"] = lyrics.cues(clean, [l["text"] for l in lines], begin, end, captionstyles.HEADLINE_MAX_CHARS)
    ends = photo_at[1:] + [end]
    data["photo_times"] = [round(e - s, 2) for s, e in zip(photo_at, ends)]
    for photo in data["photos"]:
        photo["text"] = ""
    timing["lines"] = [{**line, "start": t} for line, t in zip(lines, clean)]
    timing["source"] = "edited"
    data.update(status="queued", error=None, version=data.get("version", 0) + 1)
    _write(_folder(project_id), data)
    return data
