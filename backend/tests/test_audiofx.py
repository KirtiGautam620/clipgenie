"""Tests for the voice clean-up. The parsing is checked on sample FFmpeg logs; the loudness
and fades are measured on a real exported file made from a synthetic quiet recording."""
import re
import subprocess

import pytest

from app import audiofx, export

LOUDNORM_LOG = """noise
{
\t"input_i" : "-31.42",
\t"input_tp" : "-20.10",
\t"input_lra" : "1.20",
\t"input_thresh" : "-41.60",
\t"output_i" : "-14.5",
\t"target_offset" : "0.12"
}"""


def test_parse_loudnorm():
    m = audiofx.parse_loudnorm(LOUDNORM_LOG)
    assert m["input_i"] == -31.42 and m["target_offset"] == 0.12


def test_parse_loudnorm_silence_returns_none():
    assert audiofx.parse_loudnorm(LOUDNORM_LOG.replace("-31.42", "-inf")) is None
    assert audiofx.parse_loudnorm("nothing here") is None


def test_parse_noise_floor_uses_the_overall_section():
    log = "RMS trough dB: -70.1\nOverall\nRMS trough dB: -48.5\n"
    assert audiofx.parse_noise_floor(log) == -48.5
    assert audiofx.parse_noise_floor("Overall\nRMS through dB: -41.0") == -41.0   # FFmpeg's own typo
    assert audiofx.parse_noise_floor("RMS trough dB: -inf") is None
    assert audiofx.parse_noise_floor("") is None


def _video(path, with_audio=True, volume=0.03, noise=0.0):
    """3 s video; audio = a 220 Hz tone (stand-in for a voice, only during seconds 1-2 when
    `noise` is set), plus optional constant hiss."""
    cmd = ["ffmpeg", "-loglevel", "error", "-y", "-f", "lavfi", "-i", "testsrc2=size=1280x720:rate=25:d=3"]
    if with_audio:
        src = f"sine=f=220:d=3,volume={volume}"
        if noise:
            src += ",volume='between(t,1,2)':eval=frame"
        if noise:
            cmd += ["-f", "lavfi", "-i", f"anoisesrc=d=3:c=white:a={noise}",
                    "-f", "lavfi", "-i", src,
                    "-filter_complex", "[1][2]amix=inputs=2:normalize=0[a]", "-map", "0:v", "-map", "[a]"]
        else:
            cmd += ["-f", "lavfi", "-i", src]
    cmd += ["-c:v", "libx264", "-pix_fmt", "yuv420p", "-c:a", "aac", "-shortest", str(path)]
    subprocess.run(cmd, check=True)


def _lufs(path):
    log = subprocess.run(["ffmpeg", "-hide_banner", "-nostats", "-i", str(path), "-af", "ebur128",
                          "-f", "null", "-"], capture_output=True, text=True).stderr
    return float(re.findall(r"I:\s+(-?[\d.]+) LUFS", log)[-1])


def _rms_db(path, start, length):
    log = subprocess.run(["ffmpeg", "-hide_banner", "-nostats", "-ss", str(start), "-t", str(length),
                          "-i", str(path), "-vn", "-af", "astats", "-f", "null", "-"],
                         capture_output=True, text=True).stderr
    return float(re.findall(r"RMS level dB: (-?[\d.]+)", log)[-1])


def test_no_audio_means_no_filter(tmp_path):
    src = tmp_path / "in.mp4"
    _video(src, with_audio=False)
    chain, report = audiofx.voice_filter(src, 0, 3)
    assert chain is None and report["applied"] is False


def test_quiet_clean_audio_is_levelled_and_not_denoised(tmp_path):
    src, out = tmp_path / "in.mp4", tmp_path / "out.mp4"
    _video(src, volume=0.1)
    assert _lufs(src) < -40                         # really quiet to start with (-42 LUFS)
    info = export.export_clip(src, [], 0, 3, out, tmp_path, "crop")
    assert info["audio"]["applied"] and not info["audio"]["denoised"]
    assert _lufs(out) == pytest.approx(audiofx.TARGET_LUFS, abs=1.5)


def test_parse_rms_level():
    assert audiofx.parse_rms_level("RMS level dB: -30.0\nOverall\nRMS level dB: -25.5") == -25.5
    assert audiofx.parse_rms_level("") is None


def test_continuous_voice_without_pauses_is_not_denoised(tmp_path):
    src = tmp_path / "in.mp4"
    _video(src, volume=0.3)       # a steady tone: no separate quiet floor to measure
    assert audiofx.voice_filter(src, 0, 3)[1]["denoised"] is False


def test_noisy_audio_triggers_denoise(tmp_path):
    src = tmp_path / "in.mp4"
    _video(src, volume=0.8, noise=0.02)
    _, report = audiofx.voice_filter(src, 0, 3)
    assert report["denoised"] is True


def test_cut_edges_fade_to_silence(tmp_path):
    src, out = tmp_path / "in.mp4", tmp_path / "out.mp4"
    _video(src, volume=0.3)
    export.export_clip(src, [], 0, 3, out, tmp_path, "crop")
    middle = _rms_db(out, 1.0, 0.5)
    assert _rms_db(out, 0, 0.01) < middle - 15      # first 10 ms: fading in
    assert _rms_db(out, 2.97, 0.03) < middle - 15   # last 30 ms: faded out


def test_clean_audio_can_be_switched_off(tmp_path):
    src, out = tmp_path / "in.mp4", tmp_path / "out.mp4"
    _video(src, volume=0.03)
    info = export.export_clip(src, [], 0, 3, out, tmp_path, "crop", clean_audio=False)
    assert info["audio"]["applied"] is False
    assert _lufs(out) < -30


def test_almost_silent_audio_is_not_boosted(tmp_path):
    src, out = tmp_path / "in.mp4", tmp_path / "out.mp4"
    _video(src, volume=0.0002)                      # about -75 LUFS: hiss, not a voice
    info = export.export_clip(src, [], 0, 3, out, tmp_path, "crop")
    assert "skipped" in info["audio"]["loudness"]
    assert _lufs(out) < -45
