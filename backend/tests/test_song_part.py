"""A long song: the clip uses the part of the song the user chose (the 'start' offset)."""
import re
import subprocess

import pytest

from app import manifest, mix, music


def _ffmpeg(*args):
    subprocess.run(["ffmpeg", "-loglevel", "error", "-y", *args], check=True)


@pytest.fixture
def song_dir(tmp_path, monkeypatch):
    """A 60 second song: 30 s of silence, then 30 s of tone. Only the start point decides what is heard."""
    monkeypatch.setattr(music, "MUSIC_DIR", tmp_path)
    _ffmpeg("-f", "lavfi", "-t", "30", "-i", "anullsrc=r=44100:cl=mono",
            "-f", "lavfi", "-t", "30", "-i", "sine=frequency=440:sample_rate=44100",
            "-filter_complex", "[0][1]concat=n=2:v=0:a=1", "-c:a", "libmp3lame", str(tmp_path / "song.mp3"))
    return tmp_path


def _mean_volume(path) -> float:
    out = subprocess.run(["ffmpeg", "-i", str(path), "-af", "volumedetect", "-f", "null", "-"],
                         capture_output=True, text=True).stderr
    return float(re.search(r"mean_volume: (-?[\d.]+) dB", out).group(1))


def test_track_length_is_read_from_the_file(song_dir):
    track = {"file": "song.mp3", "id": "x"}
    assert music.track_seconds(track) == pytest.approx(60, abs=0.1)


def test_start_point_chooses_the_part_of_the_song(song_dir, tmp_path):
    base = tmp_path / "base.mp4"
    _ffmpeg("-f", "lavfi", "-t", "5", "-i", "color=c=black:s=160x120:r=10", "-an", "-c:v", "libx264", str(base))
    track = music.MUSIC_DIR / "song.mp3"

    intro = tmp_path / "intro.mp4"
    mix.apply_music(base, track, intro, volume=1.0, start=0.0)     # the silent intro
    middle = tmp_path / "middle.mp4"
    mix.apply_music(base, track, middle, volume=1.0, start=35.0)   # inside the tone
    assert _mean_volume(intro) < -50
    assert _mean_volume(middle) > -30


def _with_music(music_block):
    m = manifest.default_manifest(0.0, 20.0)
    m["audio"]["music"] = music_block
    return m


def test_start_is_saved_in_the_manifest_and_defaults_to_the_beginning():
    m = manifest.validate(_with_music({"track_id": "t1", "volume": 0.5, "start": 42.5}))
    assert m["audio"]["music"] == {"track_id": "t1", "volume": 0.5, "start": 42.5}
    old = manifest.validate(_with_music({"track_id": "t1", "volume": 0.5}))
    assert old["audio"]["music"]["start"] == 0.0


def test_a_negative_start_is_refused():
    with pytest.raises(ValueError):
        manifest.validate(_with_music({"track_id": "t1", "volume": 0.5, "start": -3}))
