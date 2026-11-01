"""Tests for the Photo Story manifest. Pure data checks: no files, no video, no models."""
import copy

import pytest

from app.photostory import manifest as mf


def good():
    return {
        "id": "0123456789ab", "title": "A day in Jaipur",
        "scenes": [
            {"id": "s1", "image": "fort.jpg", "duration": 5, "motion": "zoom_in", "rights": "own",
             "narration_text": "The fort stands above the old city."},
            {"id": "s2", "image": "market.png", "duration": 4, "motion": "pan_left", "transition": "slide_left",
             "rights": "own", "people": "consent"},
        ],
    }


def with_scene(**changes):
    raw = good()
    raw["scenes"][0].update(changes)
    return raw


def test_a_minimal_project_is_accepted_and_has_sensible_defaults():
    m = mf.parse(good())
    assert [s.id for s in m.scenes] == ["s1", "s2"]
    s = m.scenes[0]
    assert (s.intensity, s.fit, s.transition, s.transition_seconds, s.focus) == (0.5, "fill", "fade", 0.6, (0.5, 0.5))
    assert m.voice["mode"] == "none" and m.captions["on"] is False and m.music["track_id"] is None


def test_a_project_survives_being_saved_and_loaded_unchanged():
    raw = good()
    raw["sources"] = [{"id": "wiki", "title": "Amber Fort", "url": "https://example.org/amber", "retrieved": "2026-11-01"}]
    raw["scenes"][0]["claims"] = [{"text": "Built in 1592.", "label": "sourced", "source_id": "wiki"},
                                  {"text": "I loved the view.", "label": "user"}]
    raw["headline"] = {"text": "Jaipur in a day"}
    first = mf.to_dict(mf.parse(raw))
    assert mf.to_dict(mf.parse(first)) == first


@pytest.mark.parametrize("change,message", [
    ({"duration": 0.5}, "between 1 and 30"), ({"duration": 31}, "between 1 and 30"),
    ({"duration": True}, "must be a number"), ({"duration": "5"}, "must be a number"),
    ({"intensity": 1.5}, "between 0 and 1"), ({"motion": "spin"}, "motion must be one of"),
    ({"fit": "stretch"}, "fit must be one of"), ({"transition": "explode"}, "transition must be one of"),
    ({"transition_seconds": 5}, "between 0.2 and 2"), ({"focus": [0.5]}, "two numbers"),
    ({"focus": [2, 0.5]}, "between 0 and 1"), ({"rights": "stolen"}, "rights must be one of"),
    ({"people": "maybe"}, "people in the photo must be one of"), ({"id": "Bad Id!"}, "id must be"),
    ({"narration_text": "x" * 601}, "at most 600"), ({"narration_audio": "voice.exe"}, "narration audio"),
    ({"narration_seconds": -1}, "between 0.1 and 600"),
])
def test_bad_scene_values_are_refused_with_a_clear_message(change, message):
    with pytest.raises(ValueError, match=message):
        mf.parse(with_scene(**change))


@pytest.mark.parametrize("image", ["../secret.jpg", "folder/photo.jpg", "/etc/passwd.jpg", "photo.gif", "photo",
                                   ".hidden.jpg", "a" * 90 + ".jpg", "photo.jpg.exe", "pho to.jpg"])
def test_image_names_cannot_escape_the_project_folder(image):
    with pytest.raises(ValueError, match="plain .jpg or .png"):
        mf.parse(with_scene(image=image))


def test_the_error_names_which_scene_is_wrong():
    raw = good()
    raw["scenes"][1]["duration"] = 99
    with pytest.raises(ValueError, match="Scene 2"):
        mf.parse(raw)


@pytest.mark.parametrize("mutate,message", [
    (lambda r: r.update(id="short"), "12 lowercase hex"),
    (lambda r: r.update(id="0123456789AB"), "12 lowercase hex"),
    (lambda r: r.update(scenes=[]), "at least one scene"),
    (lambda r: r.update(scenes="x"), "at least one scene"),
    (lambda r: r.update(scenes=[dict(good()["scenes"][0], id=f"s{i}") for i in range(41)]), "at most 40"),
    (lambda r: r["scenes"][1].update(id="s1"), "share the same id"),
    (lambda r: r.update(title=""), "cannot be empty"),
    (lambda r: r.update(title="x" * 121), "at most 120"),
    (lambda r: r.update(schema=99), "different version"),
    (lambda r: r.update(voice={"mode": "robot"}), "Voice mode must be"),
    (lambda r: r.update(voice={"mode": "tts"}), "needs an engine"),
    (lambda r: r.update(music={"track_id": 5}), "music must say"),
    (lambda r: r.update(music={"track_id": None, "volume": 2}), "between 0 and 1"),
    (lambda r: r.update(captions={"on": "yes"}), "whether they are on"),
    (lambda r: r.update(captions={"on": True, "preset": "neon"}), "Unknown caption look"),
    (lambda r: r.update(headline={"text": ""}), "type a headline"),
    (lambda r: r.update(headline={"text": "Hi", "preset": "nope"}), "Unknown headline look"),
])
def test_bad_project_values_are_refused(mutate, message):
    raw = good()
    mutate(raw)
    with pytest.raises(ValueError, match=message):
        mf.parse(raw)


def test_a_project_must_be_an_object():
    for bad in (None, [], "x", 5):
        with pytest.raises(ValueError):
            mf.parse(bad)


def test_the_original_input_is_never_changed():
    raw = good()
    before = copy.deepcopy(raw)
    mf.parse(raw)
    assert raw == before


# ---------------------------------------------------------------- sources and claims

def sourced():
    raw = good()
    raw["sources"] = [{"id": "wiki", "title": "Amber Fort", "url": "https://example.org/amber",
                       "retrieved": "2026-11-01", "excerpt": "Construction began in 1592."}]
    return raw


def test_a_sourced_claim_must_point_to_a_real_source():
    raw = sourced()
    raw["scenes"][0]["claims"] = [{"text": "Built in 1592.", "label": "sourced", "source_id": "wiki"}]
    assert mf.parse(raw).scenes[0].claims[0].source_id == "wiki"
    raw["scenes"][0]["claims"][0]["source_id"] = "nowhere"
    with pytest.raises(ValueError, match="must point to one of the project's sources"):
        mf.parse(raw)
    raw["scenes"][0]["claims"][0].pop("source_id")
    with pytest.raises(ValueError, match="must point to one of the project's sources"):
        mf.parse(raw)


def test_only_sourced_claims_may_have_a_source():
    raw = sourced()
    raw["scenes"][0]["claims"] = [{"text": "I loved it.", "label": "user", "source_id": "wiki"}]
    with pytest.raises(ValueError, match="only 'sourced' claims"):
        mf.parse(raw)


def test_every_claim_needs_one_of_the_three_labels():
    raw = sourced()
    for label in ("fact", None, ""):
        raw["scenes"][0]["claims"] = [{"text": "Something.", "label": label}]
        with pytest.raises(ValueError, match="label must be one of"):
            mf.parse(raw)


@pytest.mark.parametrize("change,message", [
    ({"url": "ftp://x.org/a"}, "http:// or https://"), ({"url": "javascript:alert(1)"}, "http:// or https://"),
    ({"url": "https://"}, "http:// or https://"), ({"url": 5}, "http:// or https://"),
    ({"retrieved": "yesterday"}, "date like"), ({"id": "wiki wiki"}, "id must be"), ({"title": ""}, "cannot be empty"),
    ({"excerpt": "x" * 1001}, "at most 1000"),
])
def test_bad_sources_are_refused(change, message):
    raw = sourced()
    raw["sources"][0].update(change)
    with pytest.raises(ValueError, match=message):
        mf.parse(raw)


def test_two_sources_cannot_share_an_id():
    raw = sourced()
    raw["sources"].append(dict(raw["sources"][0]))
    with pytest.raises(ValueError, match="share the same id"):
        mf.parse(raw)


# ---------------------------------------------------------------- rights and consent

def test_nothing_can_be_exported_until_rights_and_consent_are_settled():
    raw = good()
    raw["scenes"][0]["rights"] = "unsure"
    raw["scenes"][1]["people"] = "no_consent"
    blockers = mf.publish_blockers(mf.parse(raw))
    assert any("Scene 1" in b and "right to use" in b for b in blockers)
    assert any("Scene 2" in b and "agreed" in b for b in blockers)


def test_a_cleared_project_has_no_blockers():
    assert mf.publish_blockers(mf.parse(good())) == []


def test_a_new_scene_defaults_to_rights_not_confirmed():
    raw = good()
    del raw["scenes"][0]["rights"]
    assert mf.parse(raw).scenes[0].rights == "unsure"
    assert mf.publish_blockers(mf.parse(raw))


def test_image_files_lists_each_photo_once_in_order():
    raw = good()
    raw["scenes"].append(dict(raw["scenes"][0], id="s3"))
    assert mf.image_files(mf.parse(raw)) == ["fort.jpg", "market.png"]
