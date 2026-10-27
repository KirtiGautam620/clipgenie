import json

import pytest

from app import music, rights
from tests.conftest import make_clips_job, music_info


def add(folders, **kw):
    args = dict(data=b"x", filename="a.mp3", title="T", moods=["funny"], license="cc0",
                attribution="", source="")
    args.update(kw)
    return music.add_track(**args)


# ------------------------------------------------------------------ music library

def test_pick_track_matches_mood_and_is_stable(folders):
    funny = add(folders, moods=["funny"])
    add(folders, moods=["emotional"])
    assert music.pick_track("funny", "job-1")["id"] == funny["id"]
    assert music.pick_track("funny", "job-1") == music.pick_track("funny", "job-1")


def test_pick_track_falls_back_and_handles_empty_library(folders):
    assert music.pick_track("funny", "x") is None
    calm = add(folders, moods=["educational"])
    assert music.pick_track("spiritual", "x")["id"] == calm["id"]


def test_unlicensed_and_unrecorded_tracks_warn(folders):
    _, tracks = folders
    add(folders, title="no-licence", license="unknown")
    add(folders, title="cc-by-no-credit", license="cc-by", attribution="")
    (tracks / "dropped-in.mp3").write_bytes(b"x")          # file with no record at all
    warned = {t["title"]: t["warning"] for t in music.list_tracks()}
    assert all(warned.values()) and len(warned) == 3
    assert "unknown" in warned["dropped-in"].lower()


def test_cc_by_with_credit_and_cc0_have_no_warning(folders):
    add(folders, license="cc-by", attribution="Jane Doe")
    add(folders, license="cc0")
    assert not any(t["warning"] for t in music.list_tracks())


def test_add_track_rejects_bad_input(folders):
    with pytest.raises(ValueError):
        add(folders, filename="song.exe")
    with pytest.raises(ValueError):
        add(folders, license="free-i-guess")


# ------------------------------------------------------------------ checklist

def test_checklist_items_depend_on_source_and_music():
    own = {"rights": "own"}
    ids = lambda s, c: [i["id"] for i in rights.required_items(s, c)]  # noqa: E731
    assert "source_rights" in ids(own, {}) and "music_licence" not in ids(own, {})
    assert "music_licence" in ids(own, {"music": music_info()})
    assert "source_unsure" in ids({"rights": "unsure"}, {}) and "source_rights" not in ids({"rights": "unsure"}, {})


def test_confirm_requires_every_box(folders):
    work, _ = folders
    job, _, clip = make_clips_job(work)
    need = [i["id"] for i in rights.required_items(rights.load_source(job), clip)]
    assert rights.confirm(job, clip, need[:-1]) == [need[-1]]
    assert not rights.is_confirmed(job, clip)
    assert rights.confirm(job, clip, need) == []
    assert rights.is_confirmed(job, clip)


def test_new_clip_version_needs_a_new_confirmation(folders):
    work, _ = folders
    job, _, clip = make_clips_job(work)
    rights.confirm(job, clip, [i["id"] for i in rights.required_items(rights.load_source(job), clip)])
    assert rights.is_confirmed(job, clip)
    assert not rights.is_confirmed(job, {**clip, "version": 1})      # music was changed


def test_warnings_and_credits():
    own, unsure = {"rights": "own"}, {"rights": "unsure"}
    assert rights.warnings(own, {}) == []
    assert any("not sure" in w for w in rights.warnings(unsure, {}))
    bad = {"music": music_info(license="Unknown licence", warning="Licence unknown.")}
    assert any("Licence unknown" in w for w in rights.warnings(own, bad))
    by = {"music": music_info(license="CC BY (credit the artist)", attribution="Jane Doe")}
    assert "Jane Doe" in rights.credits_text(own, by)
    assert any("credit" in w.lower() for w in rights.warnings(own, by))
    src = {"rights": "permission", "url": "https://youtu.be/x", "title": "Talk", "uploader": "Sam"}
    assert "Original video: Talk by Sam" in rights.credits_text(src, {})
    assert rights.credits_text({"rights": "own", "url": "https://youtu.be/x"}, {}) == ""


def test_report_contains_the_disclaimer_and_confirmation(folders):
    work, _ = folders
    job, _, clip = make_clips_job(work, music_info=music_info())
    need = [i["id"] for i in rights.required_items(rights.load_source(job), clip)]
    rights.confirm(job, clip, need)
    r = rights.report(job, clip)
    assert "NOT automatically copyright-free" in r["disclaimer"]
    assert r["checklist_confirmed"]["items"] == need
    json.dumps(r)    # must be serialisable
