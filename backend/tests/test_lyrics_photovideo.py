"""Lyrics in a photo video: timing them to the song (Whisper replaced by a fake transcript), checking the
times, and making the video with them. The real speech model is not run here."""
import pytest

from app import photovideo
from app import transcribe as transcribe_module


@pytest.fixture
def project(tmp_path, monkeypatch):
    monkeypatch.setattr(photovideo, "PROJECTS_DIR", tmp_path)

    def fake_image(data, dest):
        dest.write_bytes(b"jpg")
        return {"width": 1080, "height": 1920}
    monkeypatch.setattr(photovideo.ingest, "normalize_image", fake_image)
    monkeypatch.setattr(photovideo.cuts, "probe_duration", lambda path: 120.0)

    def make(lyrics_text, photos=3, start=0.0, seconds=60.0):
        return photovideo.create([(b"x", f"p{i}.jpg") for i in range(photos)], (b"song", "song.mp3"),
                                 "", True, start, seconds, lyrics_text)
    return make


LYRICS = "Hello there\nmy friend\n\ngoodbye now\nsee you"


def fake_transcript(monkeypatch, words):
    def fake(video, work, language=None):
        return {"language": "en", "segments": [{"start": 0, "end": 60, "text": "",
                                                "words": [{"word": w, "start": t} for w, t in words]}]}
    monkeypatch.setattr(transcribe_module, "transcribe", fake)


def test_pasting_lyrics_puts_the_video_into_timing(project):
    data = project(LYRICS)
    assert data["status"] == "timing"
    assert data["lyrics"] == ["Hello there", "my friend", "goodbye now", "see you"]


def test_the_song_is_timed_and_the_user_is_asked_to_check_it(project, monkeypatch):
    data = project(LYRICS)
    fake_transcript(monkeypatch, [("hello", 2.0), ("there", 2.4), ("my", 8.0), ("friend", 8.3),
                                  ("goodbye", 30.0), ("now", 30.4)])
    photovideo.time_lyrics(data["id"])
    done = photovideo.read(data["id"])
    assert done["status"] == "timed"
    lines = done["timing"]["lines"]
    assert [l["start"] for l in lines][:3] == [2.0, 8.0, 30.0]
    assert [l["heard"] for l in lines] == [True, True, True, False]    # "see you" was not heard


def test_a_check_that_does_not_match_the_lines_is_refused(project, monkeypatch):
    data = project(LYRICS)
    fake_transcript(monkeypatch, [("hello", 2.0)])
    photovideo.time_lyrics(data["id"])
    with pytest.raises(ValueError, match="do not match"):
        photovideo.set_timing(data["id"], [1.0, 2.0])


@pytest.mark.parametrize("starts,message", [
    ([5.0, 3.0, 9.0, 12.0], "in order"),
    ([0.0, 5.0, 9.0, 999.0], "inside the song"),
    ([0.0, 5.0, float("nan"), 12.0], "inside the song"),
])
def test_bad_times_are_refused(project, monkeypatch, starts, message):
    data = project(LYRICS)
    fake_transcript(monkeypatch, [("hello", 2.0)])
    photovideo.time_lyrics(data["id"])
    with pytest.raises(ValueError, match=message):
        photovideo.set_timing(data["id"], starts)


def test_checked_times_plan_the_photo_changes_and_their_lines(project, monkeypatch):
    data = project(LYRICS, photos=2, seconds=60.0)
    fake_transcript(monkeypatch, [("hello", 2.0)])
    photovideo.time_lyrics(data["id"])
    done = photovideo.set_timing(data["id"], [2.0, 8.0, 30.0, 45.0])
    assert done["status"] == "queued"
    assert sum(done["photo_times"]) == pytest.approx(60.0, abs=0.05)
    assert [p["text"] for p in done["photos"]] == ["Hello there", "goodbye now"]   # lines that start each photo


def test_the_ffmpeg_command_uses_the_planned_photo_times(project, monkeypatch, tmp_path):
    data = project(LYRICS, photos=2, seconds=60.0)
    fake_transcript(monkeypatch, [("hello", 2.0)])
    photovideo.time_lyrics(data["id"])
    done = photovideo.set_timing(data["id"], [2.0, 8.0, 30.0, 45.0])
    folder = photovideo._folder(data["id"])
    cmd = photovideo._command(folder, done, folder / "out.mp4")
    durations = [cmd[i + 1] for i, a in enumerate(cmd) if a == "-t"]
    first = done["photo_times"][0]
    assert f"{first:.2f}" in durations


def test_rendering_waits_until_the_lyrics_are_checked(project, monkeypatch):
    data = project(LYRICS)
    photovideo.render(data["id"])                        # status 'timing': nothing is rendered
    assert photovideo.read(data["id"])["status"] == "timing"
