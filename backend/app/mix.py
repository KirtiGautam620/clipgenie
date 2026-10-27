"""Mix background music under a clip's speech: levelling, ducking and fades.

The video picture is copied untouched (-c:v copy), so changing the music is fast.
"""
import subprocess
from pathlib import Path

# The music is first levelled to a steady loudness (so every track starts equally loud),
# then the volume slider scales it. 1.0 = a clear music bed in the pauses.
MUSIC_LEVEL_LUFS = -20
FADE_IN = 1.0
FADE_OUT = 1.5
# Ducking: when the voice is louder than `threshold`, music is pushed down.
# Tuned by measurement: lowers the music by roughly 8-10 dB while someone speaks.
DUCK = "threshold=0.06:ratio=4:attack=15:release=350:makeup=1"


def _has_audio(video: Path) -> bool:
    out = subprocess.run(
        ["ffprobe", "-v", "error", "-select_streams", "a", "-show_entries", "stream=index",
         "-of", "csv=p=0", str(video)], capture_output=True, text=True, check=True).stdout
    return bool(out.strip())


def _duration(video: Path) -> float:
    out = subprocess.run(
        ["ffprobe", "-v", "error", "-show_entries", "format=duration", "-of", "csv=p=0",
         str(video)], capture_output=True, text=True, check=True).stdout
    return float(out.strip())


def apply_music(base: Path, track: Path, out: Path, volume: float) -> None:
    """Write `out` = `base` video with `track` mixed in under the speech.

    volume: 0.0 (silent) .. 1.0 (full music bed). Values above 1 are clamped.
    """
    volume = max(0.0, min(1.0, volume))
    dur = _duration(base)
    fade_out = min(FADE_OUT, dur / 3)
    music = (
        f"[1:a]atrim=0:{dur:.3f},asetpts=PTS-STARTPTS,"
        f"loudnorm=I={MUSIC_LEVEL_LUFS}:TP=-2:LRA=11,volume={volume:.3f},"
        f"afade=t=in:st=0:d={FADE_IN},afade=t=out:st={dur - fade_out:.3f}:d={fade_out:.3f}"
    )
    if _has_audio(base):
        graph = (
            f"{music}[m];"
            f"[0:a]asplit=2[voice][key];"
            f"[m][key]sidechaincompress={DUCK}[ducked];"          # music, lowered by the voice
            f"[voice][ducked]amix=inputs=2:duration=first:normalize=0,alimiter=limit=0.95[a]"
        )
    else:  # a silent video: nothing to duck under
        graph = f"{music},alimiter=limit=0.95[a]"

    cmd = ["ffmpeg", "-loglevel", "error", "-y", "-i", str(base),
           "-stream_loop", "-1", "-i", str(track),      # loop short tracks to fill the clip
           "-filter_complex", graph, "-map", "0:v", "-map", "[a]",
           "-c:v", "copy", "-c:a", "aac", "-b:a", "160k", "-t", f"{dur:.3f}", str(out)]
    try:
        subprocess.run(cmd, check=True, capture_output=True, text=True)
    except subprocess.CalledProcessError as e:
        raise RuntimeError(f"Mixing the music failed: {e.stderr[-400:]}") from e
