"""Typed requests that change one photo of a photo video, and the transitions and frames in the render."""
import pytest

from app import photoedit, photovideo


@pytest.mark.parametrize("message,expected", [
    ("change the text on photo 2 to Good morning", {"action": "text", "photo": 2, "text": "Good morning"}),
    ("add text 'Hello there' to photo 2", {"action": "text", "photo": 2, "text": "Hello there"}),
    ("remove the text from photo 5", {"action": "text", "photo": 5, "text": ""}),
    ("fade into photo 3", {"action": "transition", "photo": 3, "value": "fade"}),
    ("slide into photo 4", {"action": "transition", "photo": 4, "value": "slide", "direction": "right"}),
    ("white frame on photo 1", {"action": "frame", "photo": 1, "value": "white"}),
    ("make photo 3 black border", {"action": "frame", "photo": 3, "value": "black"}),
    ("no frame on photo 2", {"action": "frame", "photo": 2, "value": "none"}),
])
def test_the_rules_understand_typed_requests(message, expected):
    assert photoedit._rule(message) == expected


def test_a_request_with_no_photo_number_is_not_guessed(monkeypatch):
    monkeypatch.setattr(photoedit, "_from_model", lambda message: None)   # the model is not needed here
    assert photoedit.understand("make it nicer") is None


def test_a_request_the_rules_miss_goes_to_the_model_and_its_answer_is_checked(monkeypatch):
    monkeypatch.setattr(photoedit, "ask_json",
                        lambda system, user, timeout=60: {"action": "transition", "photo": 2, "value": "fade"})
    monkeypatch.setattr(photoedit, "_rule", lambda message: None)
    assert photoedit.understand("make the second one come in softly") == \
        {"action": "transition", "photo": 2, "value": "fade", "speed": "medium"}


def test_the_model_cannot_ask_for_an_unknown_change(monkeypatch):
    monkeypatch.setattr(photoedit, "ask_json",
                        lambda system, user, timeout=60: {"action": "delete_video", "photo": 1, "value": "x"})
    monkeypatch.setattr(photoedit, "_rule", lambda message: None)
    assert photoedit.understand("do something") is None


def _project(tmp_path, monkeypatch, photos):
    monkeypatch.setattr(photovideo, "PROJECTS_DIR", tmp_path)
    pid = "0123456789ab"
    folder = tmp_path / pid
    (folder / "input").mkdir(parents=True)
    data = {"id": pid, "status": "done", "song_file": "song.mp3", "song_seconds": 30.0, "song_start": 0.0,
            "photos": photos}
    photovideo._write(folder, data)
    return pid


def test_a_photo_change_is_saved_and_the_video_is_marked_for_a_new_render(tmp_path, monkeypatch):
    pid = _project(tmp_path, monkeypatch, [{"file": "photo_01.jpg", "name": "a.jpg", "text": "", "transition": "cut", "frame": "none"}])
    data = photovideo.change_photo(pid, 1, text="Namaste", transition="fade", frame="white")
    assert data["status"] == "queued"
    assert data["photos"][0]["text"] == "Namaste"
    assert (data["photos"][0]["transition"], data["photos"][0]["frame"]) == ("fade", "white")
    assert data["version"] == 1


@pytest.mark.parametrize("kwargs", [{"index": 2}, {"index": 0}, {"index": 1, "transition": "spin"},
                                    {"index": 1, "frame": "gold"}])
def test_bad_photo_changes_are_refused(tmp_path, monkeypatch, kwargs):
    pid = _project(tmp_path, monkeypatch, [{"file": "photo_01.jpg", "name": "a.jpg", "text": ""}])
    with pytest.raises(ValueError):
        photovideo.change_photo(pid, **kwargs)


def test_the_render_command_has_the_slide_and_fade_and_frame(tmp_path):
    (tmp_path / "input").mkdir()
    data = {"song_file": "song.mp3", "song_seconds": 30.0, "song_start": 0.0, "photos": [
        {"file": "p1.jpg", "text": "", "transition": "cut", "frame": "white"},
        {"file": "p2.jpg", "text": "Hi", "transition": "slide", "frame": "none"},
        {"file": "p3.jpg", "text": "", "transition": "fade", "frame": "black"}]}
    cmd = photovideo._command(tmp_path, data, tmp_path / "out.mp4")
    graph = cmd[cmd.index("-filter_complex") + 1]
    assert "overlay=x='0+1080*(1-(1-(1-min(t/0.60,1))^2))':y='0'" in graph   # slide in from the right, medium
    assert "fade=t=in:st=0:d=0.60" in graph            # the fade, medium
    assert "pad=1080:1920:24:24:color=white" in graph  # the white frame
    assert "pad=1080:1920:24:24:color=black" in graph  # the black frame


@pytest.mark.parametrize("transition,expected", [
    ("slide_left", "overlay=x='0-1080*(1-(1-(1-min(t/0.30,1))^2))':y='0'"),
    ("slide_top", "overlay=x='0':y='0-1920*(1-(1-(1-min(t/0.30,1))^2))'"),
    ("slide_bottom", "overlay=x='0':y='0+1920*(1-(1-(1-min(t/0.30,1))^2))'"),
])
def test_each_side_slides_from_its_own_edge_at_the_chosen_speed(tmp_path, transition, expected):
    (tmp_path / "input").mkdir()
    data = {"song_file": "song.mp3", "song_seconds": 30.0, "song_start": 0.0, "photos": [
        {"file": "p1.jpg", "text": "", "transition": "cut", "frame": "none"},
        {"file": "p2.jpg", "text": "", "transition": transition, "transition_speed": "fast", "frame": "none"}]}
    graph = photovideo._command(tmp_path, data, tmp_path / "out.mp4")
    assert expected in graph[graph.index("-filter_complex") + 1]


def test_text_can_come_in_from_a_side_and_stays_still_when_asked(tmp_path):
    (tmp_path / "input").mkdir()
    base = {"file": "p1.jpg", "text": "Hi", "transition": "cut", "frame": "none", "transition_speed": "medium"}
    moving = {**base, "text_motion": "left", "text_speed": "slow"}
    still = {**base, "text_motion": "none"}
    for photo, expected in [(moving, "x='(W-w)/2-1080*(1-(1-(1-min(t/1.00,1))^2))'"),
                            (still, "x='(W-w)/2':y='")]:
        data = {"song_file": "song.mp3", "song_seconds": 30.0, "song_start": 0.0, "photos": [photo]}
        cmd = photovideo._command(tmp_path, data, tmp_path / "out.mp4")
        assert expected in cmd[cmd.index("-filter_complex") + 1]


def test_typed_direction_and_speed_reach_the_change(monkeypatch):
    seen = []
    monkeypatch.setattr(photovideo, "change_photo", lambda pid, index, **kw: seen.append((index, kw)) or {})
    reply = photoedit.apply("0123456789ab", "slide in from the top on photo 2, fast")
    assert reply["changed"]
    assert seen == [(2, {"transition": "slide_top", "transition_speed": "fast"})]
