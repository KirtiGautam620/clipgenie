"""Quality-aware text: untrusted speech is never shown, the user chooses a headline (previewed and
approved) or no text, and export waits for that choice. Fixtures are made up; the videos are tiny
real files so the headline and "no text" renders are checked on actual pixels."""
import json
import shutil
import subprocess

import numpy as np
import pytest
from fastapi.testclient import TestClient
from PIL import Image

from app import captions, captionstyles, export, jobs, main, pipeline, render, textmode
from tests.test_caption_api import make_job
from tests.test_quality import HINDI, words
from tests.test_text_quality_pipeline import make_transcript_job
from tests.test_quality import speech_envelope


@pytest.fixture
def client(folders):
    with TestClient(main.app) as c:
        yield c


UNTRUSTED_STATE = {"mode": "pending", "verdict": "unreliable", "headline": None,
                   "reasons": ["One word is repeated 74 times in a row."]}


def make_pending_job(work, music=None):
    """A finished job whose speech could not be trusted: no captions, waiting for the user."""
    job, folder = make_job(work, music=music)
    data = json.loads((folder / "clips.json").read_text())
    clip = data["clips"][0]
    clip.pop("captions")
    clip["withheld"] = {"title": "Surprising Opening", "reason": "The repetition of 'रादे' is catchy.", "mood": "funny"}
    clip.update(title="Clip 1", reason="", mood="other", text=dict(UNTRUSTED_STATE))
    (folder / "clips.json").write_text(json.dumps(data, ensure_ascii=False))
    export.apply_no_text(export.base_path(folder / "clip_1.mp4"), folder / "clip_1.mp4")
    return job, folder


def pixels(path, t):
    raw = subprocess.run(["ffmpeg", "-loglevel", "error", "-ss", str(t), "-i", str(path), "-frames:v", "1",
                          "-f", "rawvideo", "-pix_fmt", "rgb24", "-"], capture_output=True, check=True).stdout
    return np.frombuffer(raw, np.uint8).reshape(1920, 1080, 3).astype(int)


def top_zone(path, t):
    return pixels(path, t)[300:800]          # where the default headline sits


def changed(a, b):
    return float(np.abs(a - b).mean())


def saved(folder):
    return json.loads((folder / "clips.json").read_text())["clips"][0]


# ================================================================== the modes module

def test_trusted_verdicts_keep_captions_and_untrusted_ones_wait():
    assert textmode.initial_state({"verdict": "reliable", "reasons": []})["mode"] == "captions"
    assert textmode.initial_state({"verdict": "unchecked", "reasons": ["x"]})["mode"] == "captions"
    for verdict in ("unreliable", "unusable"):
        got = textmode.initial_state({"verdict": verdict, "reasons": ["why"]})
        assert got["mode"] == "pending" and got["reasons"] == ["why"] and got["headline"] is None


def test_withhold_hides_the_ai_text_but_keeps_it_internally():
    entry = {"id": 3, "title": "Surprising Opening", "reason": "A loop.", "mood": "funny"}
    textmode.withhold(entry)
    assert (entry["title"], entry["reason"], entry["mood"]) == ("Clip 3", "", "other")
    assert entry["withheld"]["title"] == "Surprising Opening"


def test_the_public_view_never_contains_withheld_text_or_untrusted_words():
    clip = {"id": 1, "title": "Clip 1", "withheld": {"title": "secret"}, "text": dict(UNTRUSTED_STATE),
            "captions": {"words": [{"text": "bad"}], "style": {}}}
    out = textmode.public(clip)
    assert "withheld" not in out and "captions" not in out and out["text"]["needs_decision"] is True
    assert "secret" not in json.dumps(out) and "bad" not in json.dumps(out)


def test_old_clips_without_a_text_block_count_as_captions():
    clip = {"id": 1, "captions": {"words": [], "style": {}}}
    assert textmode.text_state(clip)["verdict"] == "legacy"
    out = textmode.public(clip)
    assert out["text"]["mode"] == "captions" and out["text"]["needs_decision"] is False and "captions" in out


# ================================================================== headline styles and drawing

def test_headline_presets_and_validation():
    assert [p["id"] for p in captionstyles.headline_preset_list()] == ["poster", "banner", "title", "handwritten", "plain"]
    s = captionstyles.resolve_headline("banner", {"size": 5, "position": 99, "seconds": 1})
    assert (s.size, s.position, s.seconds) == (40, 72, 2)                     # clamped, never below 2 s
    assert captionstyles.resolve_headline("poster", {"seconds": 0}).seconds == 0   # 0 = whole clip
    for bad in ({"text_color": "red"}, {"box": "star"}, {"weight": "comic"}, {"size": "big"},
                {"uppercase": "yes"}, {"font": "Arial"}):
        with pytest.raises(ValueError):
            captionstyles.resolve_headline("poster", bad)
    with pytest.raises(ValueError):
        captionstyles.resolve_headline("nope")


def test_headline_text_is_cleaned_and_checked():
    assert captionstyles.clean_headline("  Learn   fast \n today ") == "Learn fast today"
    for bad in ("", "   ", None, 5, "x" * 121):
        with pytest.raises(ValueError):
            captionstyles.clean_headline(bad)
    assert captionstyles.clean_headline("x" * 120)


def test_every_headline_look_draws_something_different():
    shots = {p: np.asarray(captions.render_headline("Learn faster, every day", captionstyles.resolve_headline(p)))
             for p in captionstyles.HEADLINE_PRESETS}
    for p, a in shots.items():
        assert a.shape == (captions.HEAD_H, captions.HEAD_W, 4) and (a[..., 3] > 0).sum() > 5000, p
        assert a[0, 0, 3] == 0                                   # the corner is see-through
    assert not np.array_equal(shots["poster"], shots["banner"]) and not np.array_equal(shots["banner"], shots["title"])


def test_a_banner_uses_readable_text_on_any_colour():
    img = captions.render_headline("Hello", captionstyles.resolve_headline("banner", {"accent_color": "#101010"}))
    a = np.asarray(img)
    assert (a[..., :3][a[..., 3] > 200].max(axis=1) > 200).any()      # light letters on a dark banner


def test_long_hindi_and_english_headlines_fit_the_canvas():
    style = captionstyles.resolve_headline("poster")
    for text in ("नमस्ते दोस्तों आज हम सीखेंगे कुछ नया और बहुत ही रोचक बातें जो आपकी ज़िंदगी बदल देंगी",
                 "The one habit that quietly changes how you work every single day of your life, explained"):
        size, lines = captions._headline_lines(text, style)
        assert len(lines) <= captions.HEAD_MAX_LINES and size <= style.size
        box = captions.render_headline(text, style).getbbox()
        assert box[0] >= 0 and box[2] <= captions.HEAD_W and box[3] <= captions.HEAD_H
    assert captions._headline_lines("Short one", style)[0] == style.size       # short text keeps its size


# ================================================================== the pipeline decides

def run_pipeline_for(monkeypatch, work, tokens):
    job, folder = make_transcript_job(work, tokens)
    calls = []

    def fake_create(folder, n, m):
        calls.append({"cap_words": (m["text"]["captions"] or {}).get("words", [])})
        return {"stages": ["picture", "text", "music"], "music": None,
                "framing": {"mode": "center", "reason": "test", "audio": {"applied": False}}}
    monkeypatch.setattr(pipeline.render, "create", fake_create)
    monkeypatch.setattr(pipeline, "_pauses", lambda f: ([], speech_envelope(30), 30.0))
    monkeypatch.setattr(pipeline.music, "pick_track", lambda mood, key: calls.append({"mood": mood}) or None)
    # the (made-up) AI picker gives this clip a title, reason and mood taken from the transcript
    monkeypatch.setattr(pipeline, "pick_clips", lambda *a: [{"start": 0.0, "end": 14.0, "title": "Great Hook",
                                                              "reason": "AI reason", "mood": "funny"}])
    pipeline._make_clips(job, dict(use_ai=False, music=True, count=1, min_len=5, max_len=20))
    return json.loads((folder / "clips.json").read_text())["clips"][0], calls


def test_a_trusted_clip_gets_captions_as_before(folders, monkeypatch):
    clip, calls = run_pipeline_for(monkeypatch, folders[0], HINDI)
    assert clip["text"]["mode"] == "captions" and clip["text"]["verdict"] == "reliable"
    assert clip["captions"]["words"] and next(c for c in calls if "cap_words" in c)["cap_words"]
    assert clip["title"] == "Great Hook" and "withheld" not in clip


def test_an_untrusted_clip_is_made_without_text_and_its_ai_text_is_withheld(folders, monkeypatch):
    clip, calls = run_pipeline_for(monkeypatch, folders[0], HINDI[:8] + ["तो"] * 40)
    assert clip["text"]["mode"] == "pending" and clip["text"]["verdict"] in ("unreliable", "unusable")
    assert "captions" not in clip and next(c for c in calls if "cap_words" in c)["cap_words"] == []
    assert (clip["title"], clip["reason"], clip["mood"]) == ("Clip 1", "", "other")
    assert clip["withheld"]["title"] == "Great Hook"                         # kept internally only
    assert {"mood": "other"} in calls                                         # music is not picked from untrusted text
    public = json.dumps(textmode.public(clip), ensure_ascii=False)
    assert "Great Hook" not in public and "AI reason" not in public and "तो तो" not in public


# ================================================================== the API

def test_the_page_never_receives_withheld_text_or_words(client, folders):
    job, folder = make_pending_job(folders[0])
    r = client.get(f"/api/jobs/{job}/clips").json()["clips"][0]
    assert r["title"] == "Clip 1" and r["reason"] == "" and "withheld" not in r and "captions" not in r
    assert r["text"]["mode"] == "pending" and r["text"]["needs_decision"] is True and r["text"]["reasons"]
    assert "Surprising Opening" not in json.dumps(r, ensure_ascii=False)
    assert "withheld" in saved(folder)                                         # still kept internally


def test_captions_are_refused_for_an_untrusted_clip(client, folders):
    job, folder = make_pending_job(folders[0])
    before = (folder / "clips.json").read_text()
    for call in (lambda: client.get(f"/api/jobs/{job}/clips/1/captions"),
                 lambda: client.post(f"/api/jobs/{job}/clips/1/captions", json={"preset": "pill"}),
                 lambda: client.post(f"/api/jobs/{job}/clips/1/text", json={"mode": "captions"})):
        r = call()
        assert r.status_code in (400, 409) and "trusted" in r.json()["detail"]
    assert (folder / "clips.json").read_text() == before


def test_export_waits_for_a_decision(client, folders):
    job, _ = make_pending_job(folders[0])
    r = client.get(f"/api/jobs/{job}/clips/1/download")
    assert r.status_code == 409 and "headline" in r.json()["detail"]
    assert client.get(f"/api/jobs/{job}/clips/1.mp4").status_code == 200       # watching is still allowed


def test_a_draft_headline_changes_nothing_until_it_is_approved(client, folders):
    job, folder = make_pending_job(folders[0])
    video_before = (folder / "clip_1.mp4").read_bytes()
    r = client.post(f"/api/jobs/{job}/clips/1/text", json={"headline": {"text": "  Learn faster   today "}})
    assert r.status_code == 200
    clip = r.json()
    assert clip["text"]["mode"] == "pending" and clip["text"]["headline"]["approved"] is False
    assert clip["text"]["headline"]["text"] == "Learn faster today" and clip["version"] == 0
    assert (folder / "clip_1.mp4").read_bytes() == video_before                 # nothing was drawn
    assert client.get(f"/api/jobs/{job}/clips/1/download").status_code == 409  # still waiting


def test_approving_burns_the_headline_in_and_unblocks_export(client, folders):
    job, folder = make_pending_job(folders[0])
    plain = top_zone(folder / "clip_1.mp4", 1.0)
    r = client.post(f"/api/jobs/{job}/clips/1/text",
                    json={"headline": {"text": "Learn faster today", "preset": "banner", "style": {"seconds": 2}},
                          "approve": True})
    assert r.status_code == 200
    clip = r.json()
    assert clip["text"]["mode"] == "headline" and clip["text"]["headline"]["approved"] is True
    assert clip["title"] == "Learn faster today" and clip["version"] == 1 and clip["confirmed"] is False
    out = folder / "clip_1.mp4"
    assert changed(top_zone(out, 1.0), plain) > 3                               # the card is on the picture
    assert changed(top_zone(out, 2.4), top_zone(export.base_path(out), 2.4)) < 1   # gone after its 2 seconds
    start = changed(top_zone(out, 0.02), top_zone(export.base_path(out), 0.02))
    full = changed(top_zone(out, 1.0), top_zone(export.base_path(out), 1.0))
    assert start < full / 2                                                     # fades in, not a hard cut
    assert saved(folder)["text"]["mode"] == "headline"
    items = [i["id"] for i in clip["checklist"]]
    assert client.post(f"/api/jobs/{job}/clips/1/checklist", json={"items": items}).status_code == 200
    d = client.get(f"/api/jobs/{job}/clips/1/download")
    assert d.status_code == 200 and d.headers["content-type"] == "video/mp4"


def test_a_headline_can_stay_for_the_whole_clip(client, folders):
    job, folder = make_pending_job(folders[0])
    client.post(f"/api/jobs/{job}/clips/1/text", json={"headline": {"text": "Whole clip", "style": {"seconds": 0}},
                                                      "approve": True})
    out = folder / "clip_1.mp4"
    assert changed(top_zone(out, 2.3), top_zone(export.base_path(out), 2.3)) > 3


def test_a_hindi_headline_works(client, folders):
    job, folder = make_pending_job(folders[0])
    r = client.post(f"/api/jobs/{job}/clips/1/text",
                    json={"headline": {"text": "रोज़ थोड़ा अभ्यास, बड़ा बदलाव"}, "approve": True})
    assert r.status_code == 200 and r.json()["title"] == "रोज़ थोड़ा अभ्यास, बड़ा बदलाव"


def test_export_without_text_is_always_allowed(client, folders):
    job, folder = make_pending_job(folders[0])
    r = client.post(f"/api/jobs/{job}/clips/1/text", json={"mode": "none"})
    assert r.status_code == 200 and r.json()["text"]["mode"] == "none" and r.json()["text"]["needs_decision"] is False
    out = folder / "clip_1.mp4"
    assert changed(top_zone(out, 1.0), top_zone(export.base_path(out), 1.0)) < 1
    items = [i["id"] for i in r.json()["checklist"]]
    client.post(f"/api/jobs/{job}/clips/1/checklist", json={"items": items})
    assert client.get(f"/api/jobs/{job}/clips/1/download").status_code == 200


@pytest.mark.parametrize("body", [
    {"mode": "headline"},                                                       # no headline at all
    {"mode": "headline", "headline": {"text": "Hello"}},                        # not approved
    {"approve": True},                                                          # approve nothing
    {"headline": {"text": ""}}, {"headline": {"text": "x" * 121}},
    {"headline": {"text": "Hi", "preset": "nope"}}, {"headline": {"text": "Hi", "style": {"size": "big"}}},
    {"headline": {"text": "Hi", "style": {"font": "Comic"}}}, {"mode": "sparkles"}, {}])
def test_bad_text_choices_are_rejected_and_change_nothing(client, folders, body):
    job, folder = make_pending_job(folders[0])
    before = (folder / "clips.json").read_text()
    video = (folder / "clip_1.mp4").read_bytes()
    assert client.post(f"/api/jobs/{job}/clips/1/text", json=body).status_code == 400
    assert (folder / "clips.json").read_text() == before and (folder / "clip_1.mp4").read_bytes() == video


def test_a_trusted_clip_can_switch_to_a_headline_and_back_to_captions(client, folders):
    job, folder = make_job(folders[0])
    data = json.loads((folder / "clips.json").read_text())
    data["clips"][0]["text"] = {"mode": "captions", "verdict": "reliable", "reasons": [], "headline": None}
    (folder / "clips.json").write_text(json.dumps(data))
    out = folder / "clip_1.mp4"
    with_captions = pixels(out, 1.2)
    assert client.post(f"/api/jobs/{job}/clips/1/text", json={"mode": "none"}).status_code == 200
    assert changed(pixels(out, 1.2), with_captions) > 0.2                        # captions are gone
    r = client.post(f"/api/jobs/{job}/clips/1/captions", json={"preset": "pill"})
    assert r.status_code == 400 and "Switch" in r.json()["detail"]               # must switch back first
    assert client.post(f"/api/jobs/{job}/clips/1/text", json={"mode": "captions"}).status_code == 200
    assert changed(pixels(out, 1.2), with_captions) < 1                          # the same captions again
    assert saved(folder)["text"]["mode"] == "captions"


def test_old_clips_without_a_text_block_keep_working(client, folders):
    job, folder = make_job(folders[0])                                           # no `text` block at all
    r = client.get(f"/api/jobs/{job}/clips").json()["clips"][0]
    assert r["text"]["mode"] == "captions" and r["text"]["verdict"] == "legacy"
    assert client.post(f"/api/jobs/{job}/clips/1/captions", json={"preset": "pill"}).status_code == 200
    assert client.post(f"/api/jobs/{job}/clips/1/text", json={"mode": "none"}).status_code == 200


def test_a_busy_server_says_so(client, folders):
    job, folder = make_pending_job(folders[0])
    before = (folder / "clips.json").read_text()
    with pipeline.heavy_job_lock:
        r = client.post(f"/api/jobs/{job}/clips/1/text", json={"mode": "none"})
    assert r.status_code == 409 and "busy" in r.json()["detail"] and (folder / "clips.json").read_text() == before


def test_music_is_mixed_back_after_a_text_change(client, folders, monkeypatch):
    job, folder = make_pending_job(folders[0], music={"track_id": "t1", "title": "S", "volume": 0.5,
                                                      "license": "CC0", "attribution": "", "warning": None})
    mixed = []
    track = {"id": "t1", "title": "S", "license_label": "CC0", "attribution": "", "warning": None}
    monkeypatch.setattr(render.music, "get_track", lambda tid: track)
    monkeypatch.setattr(render.music, "track_path", lambda t: folder / "t.wav")
    monkeypatch.setattr(render.mix, "apply_music", lambda base, trk, out, vol, start=0.0: mixed.append(vol) or shutil.copyfile(base, out))
    assert client.post(f"/api/jobs/{job}/clips/1/text", json={"mode": "none"}).status_code == 200
    assert mixed == [0.5]


def test_unknown_clip_and_job(client, folders):
    job, _ = make_pending_job(folders[0])
    assert client.post(f"/api/jobs/{job}/clips/9/text", json={"mode": "none"}).status_code == 404
    assert client.post("/api/jobs/0123456789/clips/1/text", json={"mode": "none"}).status_code == 404


# ================================================================== presets and preview

def test_headline_presets_endpoint(client):
    data = client.get("/api/headline-presets").json()
    assert [p["id"] for p in data["presets"]] == ["poster", "banner", "title", "handwritten", "plain"]
    assert data["max_chars"] == 120 and data["limits"]["position"] == [10, 72]


def test_headline_preview_is_a_png_that_follows_the_text_and_look(client):
    a = client.get("/api/headline-preview.png", params={"text": "Learn faster", "preset": "poster"})
    b = client.get("/api/headline-preview.png", params={"text": "Learn slower", "preset": "poster"})
    c = client.get("/api/headline-preview.png", params={"text": "Learn faster", "preset": "banner", "seconds": "6"})
    assert all(r.status_code == 200 and r.content[:4] == b"\x89PNG" for r in (a, b, c))
    assert len({a.content, b.content, c.content}) == 3
    assert client.get("/api/headline-preview.png").status_code == 200           # sample text when none is given


@pytest.mark.parametrize("query", ["text=&preset=poster", "preset=nope", "text=hi&size=huge", "text=hi&bogus=1",
                                   "text=hi&text_color=red"])
def test_headline_preview_rejects_bad_input(client, query):
    assert client.get(f"/api/headline-preview.png?{query}").status_code == 400
