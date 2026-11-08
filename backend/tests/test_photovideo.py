"""Photo videos (MVP): the text lines, the timing and the input checks. The FFmpeg render is run once in a test."""
import pytest

from app import photovideo


def test_lines_map_one_per_photo_and_trailing_blanks_do_not_count():
    assert photovideo.parse_lines("a\n\nc\n\n", 3) == ["a", "", "c"]
    assert photovideo.parse_lines("", 2) == []
    with pytest.raises(ValueError, match="2 lines for 1 photo"):
        photovideo.parse_lines("a\nb", 1)


def test_each_photo_gets_an_equal_share_and_the_last_takes_the_rounding():
    shares = photovideo.plan_seconds(10.0, 3)
    assert shares == [3.33, 3.33, 3.34]
    assert round(sum(shares), 2) == 10.0


def test_create_refuses_without_rights_and_for_bad_inputs(tmp_path, monkeypatch):
    monkeypatch.setattr(photovideo, "PROJECTS_DIR", tmp_path)
    photo = (b"not a photo", "x.jpg")
    with pytest.raises(ValueError, match="right to use"):
        photovideo.create([photo], (b"", "s.mp3"), "", False)
    with pytest.raises(ValueError, match="at least one photo"):
        photovideo.create([], (b"", "s.mp3"), "", True)
    with pytest.raises(ValueError, match="MP3, WAV"):
        photovideo.create([photo], (b"", "s.txt"), "", True)
    assert list(tmp_path.iterdir()) == []                 # nothing is left behind after a refusal


def test_unknown_or_malformed_ids_are_refused(tmp_path, monkeypatch):
    monkeypatch.setattr(photovideo, "PROJECTS_DIR", tmp_path)
    with pytest.raises(ValueError):
        photovideo.read("../../etc")
    with pytest.raises(ValueError):
        photovideo.video_path("0123456789ab")              # well-formed but never made


# ---- a long song: the user picks the part of it that the video uses

@pytest.fixture
def song_of(tmp_path, monkeypatch):
    """Fake the photo and the song length so create() can run without real media."""
    monkeypatch.setattr(photovideo, "PROJECTS_DIR", tmp_path)
    def fake_image(data, dest):
        dest.write_bytes(b"jpg")
        return {"width": 1080, "height": 1920}
    monkeypatch.setattr(photovideo.ingest, "normalize_image", fake_image)

    def make(seconds):
        monkeypatch.setattr(photovideo.cuts, "probe_duration", lambda path: seconds)
        return tmp_path
    return make


def _create(start, photos=1, seconds=60.0):
    return photovideo.create([(b"x", "a.jpg")] * photos, (b"song", "long.mp3"), "", True, start, seconds)


@pytest.mark.parametrize("seconds", [30.0, 45.0, 60.0])
def test_a_short_can_be_30_to_60_seconds_from_any_part_of_the_song(song_of, seconds):
    song_of(600.0)
    assert _create(300.0, seconds=seconds)["song_seconds"] == seconds


@pytest.mark.parametrize("seconds", [10.0, 29.9, 61.0, 180.0])
def test_a_short_outside_30_to_60_seconds_is_refused(song_of, tmp_path, seconds):
    song_of(600.0)
    with pytest.raises(ValueError, match="30 to 60 seconds"):
        _create(0.0, seconds=seconds)
    assert list(tmp_path.iterdir()) == []


def test_a_long_song_is_accepted_and_the_short_uses_the_chosen_length_from_the_start_point(song_of):
    song_of(600.0)
    data = _create(120.0)
    assert data["song_start"] == 120.0
    assert data["song_seconds"] == 60.0            # the default short length
    assert data["song_total_seconds"] == 600.0


def test_the_video_is_shorter_when_the_song_ends_first(song_of):
    song_of(200.0)
    data = _create(150.0)
    assert data["song_seconds"] == 50.0


def test_the_song_part_is_cut_out_in_the_ffmpeg_command(song_of, tmp_path):
    song_of(600.0)
    data = _create(120.0)
    cmd = photovideo._command(tmp_path / data["id"], data, tmp_path / "out.mp4")
    graph = cmd[cmd.index("-filter_complex") + 1]
    assert "atrim=start=120.00:duration=60.00" in graph


def test_old_projects_without_a_start_still_use_the_song_from_the_beginning(song_of, tmp_path):
    song_of(60.0)
    data = _create(0.0)
    del data["song_start"]                           # a project saved before song parts existed
    cmd = photovideo._command(tmp_path / data["id"], data, tmp_path / "out.mp4")
    assert "atrim=start=0.00:duration=60.00" in cmd[cmd.index("-filter_complex") + 1]


@pytest.mark.parametrize("start", [600.0, 900.0, float("nan"), -1.0])
def test_a_start_outside_the_song_is_refused_and_nothing_is_left(song_of, tmp_path, start):
    song_of(600.0)
    with pytest.raises(ValueError, match="outside the song"):
        _create(start)
    assert list(tmp_path.iterdir()) == []


def test_a_song_over_thirty_minutes_is_refused(song_of, tmp_path):
    song_of(1801.0)
    with pytest.raises(ValueError, match="30 minutes"):
        _create(0.0)
    assert list(tmp_path.iterdir()) == []
