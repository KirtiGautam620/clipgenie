"""Automatic checks on a finished video (app/checks.py). Each case is a 3-4 second synthetic video
with one thing wrong with it (or nothing)."""
import json
import subprocess

import pytest
from fastapi.testclient import TestClient

from app import checks, main, manifest
from tests.test_render import clip_entry, make_job

pytestmark = pytest.mark.real_checks


def make_video(path, *, seconds=4, size="1080x1920", video="testsrc2", audio="sine=frequency=440", audio_filter=None, with_audio=True):
    sep = ":" if "=" in video else "="              # "color=c=black" already has options
    cmd = ["ffmpeg", "-loglevel", "error", "-y", "-f", "lavfi", "-i", f"{video}{sep}size={size}:rate=25:duration={seconds}"]
    if with_audio:
        cmd += ["-f", "lavfi", "-i", f"{audio}:duration={seconds}"]
        if audio_filter:
            cmd += ["-af", audio_filter]
    cmd += ["-c:v", "libx264", "-pix_fmt", "yuv420p"] + (["-c:a", "aac"] if with_audio else []) + [str(path)]
    subprocess.run(cmd, check=True)
    return path


def m(seconds=4.0, **fades):
    doc = manifest.default_manifest(0.0, seconds)
    if fades:
        doc["fades"] = {"in": fades.get("fade_in", 0.0), "out": fades.get("fade_out", 0.0)}
    return manifest.validate(doc)


def codes(report):
    return {i["code"] for i in report["issues"]}


def test_a_healthy_video_passes(tmp_path):
    report = checks.check_clip(make_video(tmp_path / "ok.mp4"), m())
    assert report["status"] == "ok" and report["issues"] == []
    assert report["metrics"]["size"] == [1080, 1920] and report["metrics"]["loudness_lufs"] is not None


def test_the_wrong_size_is_a_problem(tmp_path):
    report = checks.check_clip(make_video(tmp_path / "small.mp4", size="640x360"), m())
    assert report["status"] == "problems" and "wrong_size" in codes(report)


def test_a_video_with_no_sound_gets_a_note(tmp_path):
    report = checks.check_clip(make_video(tmp_path / "mute.mp4", with_audio=False), m())
    assert report["status"] == "notes" and "no_audio" in codes(report)


def test_the_length_must_match_the_plan(tmp_path):
    report = checks.check_clip(make_video(tmp_path / "short.mp4", seconds=4), m(seconds=8.0))
    assert "wrong_length" in codes(report)


def test_a_black_stretch_is_found_but_a_fade_may_be_dark(tmp_path):
    black = make_video(tmp_path / "black.mp4", video="color=c=black")
    assert "black_frames" in codes(checks.check_clip(black, m()))
    # a clip that is dark only at its start while a 1 s fade-in runs is fine
    fading = tmp_path / "fade.mp4"
    subprocess.run(["ffmpeg", "-loglevel", "error", "-y", "-f", "lavfi", "-i", "testsrc2=size=1080x1920:rate=25:duration=4",
                    "-f", "lavfi", "-i", "sine=frequency=440:duration=4", "-vf", "fade=t=in:st=0:d=1.0",
                    "-c:v", "libx264", "-pix_fmt", "yuv420p", "-c:a", "aac", str(fading)], check=True)
    assert "black_frames" not in codes(checks.check_clip(fading, m(fade_in=1.0)))


def test_a_long_silence_is_noticed(tmp_path):
    quiet_middle = make_video(tmp_path / "gap.mp4", seconds=6, audio_filter="volume=enable='between(t,1,4.5)':volume=0")
    report = checks.check_clip(quiet_middle, m(seconds=6.0))
    assert "long_silence" in codes(report) and report["metrics"]["longest_silence"] >= 2.0


def test_quiet_sound_is_flagged(tmp_path):
    report = checks.check_clip(make_video(tmp_path / "q.mp4", audio_filter="volume=-38dB"), m())
    assert "quiet" in codes(report)


def test_empty_captions_are_reported():
    doc = manifest.default_manifest(0.0, 4.0)
    doc["text"] = {"mode": "captions", "headline": None, "captions": {"style": {}, "words": []}}
    # nothing to measure against a missing file: use a real one
    import tempfile, pathlib
    with tempfile.TemporaryDirectory() as d:
        report = checks.check_clip(make_video(pathlib.Path(d) / "c.mp4"), manifest.validate(doc))
    assert "no_captions" in codes(report)


def test_a_check_that_cannot_run_is_reported_not_raised(tmp_path):
    assert checks.safe_check(tmp_path, 1, m())["status"] == "unchecked"          # no such file
    bad = tmp_path / "clip_1.mp4"
    bad.write_bytes(b"not a video")
    assert checks.safe_check(tmp_path, 1, m())["status"] == "unchecked"          # unreadable file


def test_the_music_mix_is_what_gets_checked(tmp_path):
    (tmp_path / "clip_1.mp4").write_bytes(b"x")
    (tmp_path / "clip_1_music.mp4").write_bytes(b"y")
    assert checks.served_file(tmp_path, 1).name == "clip_1_music.mp4"


def test_editing_a_clip_re_checks_the_finished_video(folders):
    job, folder = make_job(folders[0], clip_entry())
    with TestClient(main.app) as client:
        r = client.post(f"/api/jobs/{job}/clips/1/effects", json={"zoom": 1.2, "pan": "none"})
    assert r.status_code == 200
    report = r.json()["checks"]
    assert report["status"] in ("ok", "notes") and "metrics" in report
    saved = json.loads((folder / "clips.json").read_text())["clips"][0]
    assert saved["checks"]["checked_at"]
