"""The hook: a title card over the first seconds, together with the captions. Drafts are never drawn;
only an approved hook reaches the video, and never on a clip whose speech is untrusted."""
import copy
import json
import shutil

import pytest
from fastapi.testclient import TestClient

from app import captionstyles, main, manifest
import subprocess

import numpy as np

from tests.test_render import clip_entry, frames, make_job


def gray_frame(path, t):
    raw = subprocess.run(["ffmpeg", "-loglevel", "error", "-ss", f"{t}", "-i", str(path), "-frames:v", "1",
                          "-vf", "scale=108:192", "-f", "rawvideo", "-pix_fmt", "gray", "-"],
                         check=True, capture_output=True).stdout
    return np.frombuffer(raw, dtype=np.uint8).astype(float)


def changed(a, b) -> float:
    """How much two frames differ (mean absolute difference, 0 to 255)."""
    return float(np.abs(a - b).mean())


STYLE = captionstyles.resolve_headline("poster", {"seconds": 3}).as_dict()


@pytest.fixture
def client(folders):
    with TestClient(main.app) as c:
        yield c


def hook_url(job):
    return f"/api/jobs/{job}/clips/1/hook"


# ---------------------------------------------------------------- the manifest

def doc(mode="captions", hook=True, captions=True):
    d = manifest.default_manifest(0.0, 6.0)
    d["text"] = {"mode": mode, "headline": None,
                 "captions": {"style": {}, "words": []} if captions and mode == "captions" else None,
                 "hook": {"text": "A curious hook", "style": copy.deepcopy(STYLE)} if hook else None}
    return d


def test_a_hook_is_allowed_with_captions_or_no_text():
    for mode in ("captions", "none"):
        assert manifest.validate(doc(mode))["text"]["hook"]["text"] == "A curious hook"


@pytest.mark.parametrize("mode", ["pending", "headline"])
def test_a_hook_is_refused_with_anything_else(mode):
    d = doc(mode, captions=False)
    if mode == "headline":
        d["text"]["headline"] = {"text": "T", "style": {}}
    with pytest.raises(ValueError, match="hook can only"):
        manifest.validate(d)


@pytest.mark.parametrize("hook, message", [({"text": "  ", "style": {}}, "needs its text"),
                                            ({"text": "x" * 200, "style": {}}, "not usable"),
                                            ({"text": "ok", "style": {"text_color": "red"}}, "not usable"),
                                            ("nope", "needs its text")])
def test_bad_hooks_are_refused(hook, message):
    d = doc()
    d["text"]["hook"] = hook
    with pytest.raises(ValueError, match=message):
        manifest.validate(d)


def test_only_an_approved_hook_becomes_part_of_the_manifest():
    base = clip_entry()
    draft = {**base["text"], "hook": {"text": "Draft", "style": STYLE, "approved": False, "source": "ai"}}
    assert manifest.from_clip({**base, "text": draft})["text"]["hook"] is None
    approved = {**base["text"], "hook": {"text": "Yes", "style": STYLE, "approved": True}}
    assert manifest.from_clip({**base, "text": approved})["text"]["hook"]["text"] == "Yes"


# ---------------------------------------------------------------- the endpoint

def test_a_draft_is_saved_but_not_drawn(client, folders):
    job, folder = make_job(folders[0], clip_entry())
    before = frames(folder / "clip_1.mp4")
    r = client.post(hook_url(job), json={"text": "Why this matters"})
    assert r.status_code == 200, r.text
    assert r.json()["text"]["hook"]["approved"] is False and r.json()["version"] == 0
    assert frames(folder / "clip_1.mp4") == before                              # nothing drawn
    assert client.get(f"/api/jobs/{job}/clips/1/manifest").json()["text"]["hook"] is None


def test_approving_draws_the_hook_for_a_few_seconds_beside_the_captions(client, folders):
    job, folder = make_job(folders[0], clip_entry())
    clip = folder / "clip_1.mp4"
    plain_early, plain_late = gray_frame(clip, 1.0), gray_frame(clip, 2.4)
    r = client.post(hook_url(job), json={"text": "Why this matters", "preset": "poster", "style": {"seconds": 2}, "approve": True})
    assert r.status_code == 200, r.text
    assert r.json()["version"] == 1 and r.json()["text"]["hook"]["approved"] is True
    got = client.get(f"/api/jobs/{job}/clips/1/manifest").json()
    assert got["text"]["hook"]["text"] == "Why this matters" and got["text"]["captions"]["words"]   # captions kept
    assert changed(gray_frame(clip, 1.0), plain_early) > 3                     # the card is on screen early on
    assert changed(gray_frame(clip, 2.4), plain_late) < 0.5                    # and gone after its 2 seconds


def test_an_ai_draft_can_be_approved_as_it_is(client, folders):
    entry = clip_entry()
    entry["text"]["hook"] = {"text": "A curious hook", "style": copy.deepcopy(STYLE), "approved": False, "source": "ai"}
    job, folder = make_job(folders[0], entry)
    r = client.post(hook_url(job), json={"approve": True})
    assert r.status_code == 200, r.text
    assert r.json()["text"]["hook"]["source"] == "ai" and r.json()["text"]["hook"]["approved"] is True
    assert client.get(f"/api/jobs/{job}/clips/1/manifest").json()["text"]["hook"]["text"] == "A curious hook"


def test_editing_an_ai_hook_makes_it_the_users_own(client, folders):
    entry = clip_entry()
    entry["text"]["hook"] = {"text": "A curious hook", "style": copy.deepcopy(STYLE), "approved": False, "source": "ai"}
    job, folder = make_job(folders[0], entry)
    r = client.post(hook_url(job), json={"text": "My own words", "approve": True})
    assert r.json()["text"]["hook"]["source"] == "user"


def test_removing_a_drawn_hook_restores_the_original_picture(client, folders):
    job, folder = make_job(folders[0], clip_entry())
    original = frames(folder / "clip_1.mp4")
    assert client.post(hook_url(job), json={"text": "A hook", "approve": True}).status_code == 200
    assert frames(folder / "clip_1.mp4") != original
    r = client.post(hook_url(job), json={"remove": True})
    assert r.status_code == 200 and r.json()["text"]["hook"] is None
    assert frames(folder / "clip_1.mp4") == original


def test_a_hook_works_on_a_clip_with_no_text(client, folders):
    clip = clip_entry(text={"mode": "none", "verdict": "reliable", "reasons": [], "headline": None})
    clip.pop("captions")
    job, folder = make_job(folders[0], clip, build=False)
    from app import export
    export.export_clip(folder / "source.mp4", [], 0.0, 2.6, folder / "clip_1.mp4", folder, "crop", cap_words=[])
    before = gray_frame(folder / "clip_1.mp4", 1.0)
    assert client.post(hook_url(job), json={"text": "Why this matters", "preset": "poster", "approve": True}).status_code == 200
    assert changed(gray_frame(folder / "clip_1.mp4", 1.0), before) > 3


def test_untrusted_or_headline_clips_cannot_have_a_hook(client, folders):
    untrusted = clip_entry(text={"mode": "pending", "verdict": "unusable", "reasons": [], "headline": None})
    untrusted.pop("captions")
    job, folder = make_job(folders[0], untrusted, build=False)
    shutil.copyfile(folder / "source.mp4", folder / "clip_1.mp4")
    shutil.copyfile(folder / "source.mp4", folder / "clip_1_base.mp4")
    before = (folder / "clips.json").read_text()
    r = client.post(hook_url(job), json={"text": "A hook", "approve": True})
    assert r.status_code == 400 and "hook can only" in r.json()["detail"]
    assert (folder / "clips.json").read_text() == before


def test_a_headline_replaces_the_hook_on_the_video(client, folders):
    job, folder = make_job(folders[0], clip_entry())
    assert client.post(hook_url(job), json={"text": "A hook", "approve": True}).status_code == 200
    r = client.post(f"/api/jobs/{job}/clips/1/text", json={"headline": {"text": "Big title"}, "approve": True})
    assert r.status_code == 200, r.text
    got = client.get(f"/api/jobs/{job}/clips/1/manifest").json()
    assert got["text"]["mode"] == "headline" and got["text"]["hook"] is None


def test_bad_hook_text_and_missing_hooks_are_refused(client, folders):
    job, folder = make_job(folders[0], clip_entry())
    assert client.post(hook_url(job), json={"text": "   ", "approve": True}).status_code == 400
    assert client.post(hook_url(job), json={"remove": True}).status_code == 400            # nothing to remove
    assert client.post(hook_url(job), json={"approve": True}).status_code == 400           # nothing to approve
