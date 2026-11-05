"""Zoom and pan for a clip's picture (app/effects.py) and how stage 1 uses it."""
import subprocess

import pytest

from app import effects
from app.export import render_base


def test_defaults_do_nothing():
    assert effects.normalize(None) == {"zoom": 1.0, "pan": "none"}
    assert effects.is_active(None) is False
    assert effects.zoom_filter(None, 5, 1080, 1920) is None


def test_valid_settings_are_kept_and_rounded():
    assert effects.normalize({"zoom": 1.234, "pan": "left"}) == {"zoom": 1.23, "pan": "left"}


@pytest.mark.parametrize("bad", [{"zoom": 0.9}, {"zoom": 1.6}, {"zoom": "big"}, {"pan": "up"}])
def test_invalid_settings_are_refused(bad):
    with pytest.raises(ValueError):
        effects.normalize(bad)


def test_zoom_filter_text():
    f = effects.zoom_filter({"zoom": 1.25, "pan": "none"}, 4.0, 1080, 1920)
    # 4 seconds at 25 frames = 100 frames; zoom grows from 1.0 to 1.25 across them
    assert f == "fps=25,zoompan=z='1.0+(0.25)*on/100':x='(iw-iw/zoom)/2':y='(ih-ih/zoom)/2':d=1:s=1080x1920"


def test_pan_directions():
    left = effects.zoom_filter({"zoom": 1.2, "pan": "left"}, 2.0, 1080, 1920)
    right = effects.zoom_filter({"zoom": 1.2, "pan": "right"}, 2.0, 1080, 1920)
    assert "x='(iw-iw/zoom)*on/50'" in left
    assert "x='(iw-iw/zoom)*(1-on/50)'" in right


def test_pan_without_zoom_still_pans():
    f = effects.zoom_filter({"zoom": 1.0, "pan": "left"}, 2.0, 1080, 1920)
    assert "z='1.0'" in f and "x='(iw-iw/zoom)*on/50'" in f


def _make_video(path, seconds=2.0):
    subprocess.run(["ffmpeg", "-loglevel", "error", "-y", "-f", "lavfi", "-i",
                    f"testsrc2=size=1280x720:rate=25:duration={seconds}",
                    "-f", "lavfi", "-i", f"sine=frequency=440:duration={seconds}",
                    "-c:v", "libx264", "-pix_fmt", "yuv420p", "-c:a", "aac", str(path)], check=True)
    return path


def _probe(path):
    out = subprocess.run(["ffprobe", "-v", "error", "-select_streams", "v:0",
                          "-count_frames", "-show_entries", "stream=width,height,nb_read_frames",
                          "-of", "csv=p=0", str(path)], check=True, capture_output=True, text=True).stdout
    w, h, n = out.strip().split(",")
    return int(w), int(h), int(n)


def test_render_base_applies_zoom_and_keeps_size(tmp_path):
    src = _make_video(tmp_path / "src.mp4")
    base = tmp_path / "base.mp4"
    render_base(src, 0.0, 2.0, base, framing="blur", clean_audio=False,
                effects={"zoom": 1.5, "pan": "left"})
    w, h, n = _probe(base)
    assert (w, h) == (1080, 1920)
    assert n == 50                       # 2 seconds at 25 frames


def test_render_base_without_effects_is_unchanged_size(tmp_path):
    src = _make_video(tmp_path / "src.mp4")
    base = tmp_path / "plain.mp4"
    render_base(src, 0.0, 2.0, base, framing="blur", clean_audio=False)
    assert _probe(base)[:2] == (1080, 1920)


def test_zoom_really_changes_the_picture(tmp_path):
    """The last frame of a zoomed clip must differ from the plain one (the effect is applied)."""
    src = _make_video(tmp_path / "src.mp4")
    plain, zoomed = tmp_path / "plain.mp4", tmp_path / "zoomed.mp4"
    render_base(src, 0.0, 2.0, plain, framing="blur", clean_audio=False)
    render_base(src, 0.0, 2.0, zoomed, framing="blur", clean_audio=False,
                effects={"zoom": 1.5, "pan": "none"})

    def last_frame(path):
        return subprocess.run(["ffmpeg", "-loglevel", "error", "-sseof", "-0.1", "-i", str(path),
                               "-frames:v", "1", "-f", "rawvideo", "-pix_fmt", "gray", "-"],
                              check=True, capture_output=True).stdout
    assert last_frame(plain) != last_frame(zoomed)
