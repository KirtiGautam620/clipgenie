"""The edit plan, hook drafts, pause tightening at creation, and the usage log."""
import json

import numpy as np
import pytest

from app import jobs, pipeline, plan
from app.llm import LLMError
from tests.test_quality import speech_envelope

RELIABLE = {"verdict": "reliable", "reasons": [], "hard": [], "soft": [], "evidence": "full",
            "trusted_fraction": 1.0, "trusted_ranges": [], "signals": {}}
UNTRUSTED = {**RELIABLE, "verdict": "unusable"}


# ---------------------------------------------------------------- the plan document

def clip_plan(**extra):
    base = {"id": 1, "cut": {"cut_start": 0.0, "cut_end": 20.0}, "segments": None, "hook": None}
    base.update(extra)
    return base


def doc(*clips):
    return {"version": plan.PLAN_VERSION, "clips": list(clips)}


def test_a_good_plan_passes():
    plan.validate(doc(clip_plan(segments=[[0.0, 8.0], [10.0, 20.0]],
                                hook={"text": "A hook", "status": "draft", "source": "ai"}), clip_plan(id=2)))


@pytest.mark.parametrize("bad, message", [
    (doc(clip_plan(), clip_plan()), "twice"),
    (doc(clip_plan(cut={"cut_start": 5.0, "cut_end": 5.0})), "unusable cut"),
    (doc(clip_plan(segments=[[0.0, 8.0], [7.0, 20.0]])), "overlapping"),
    (doc(clip_plan(segments=[[0.0, 25.0]])), "outside its cut"),
    (doc(clip_plan(hook={"text": "x", "status": "approved", "source": "ai"})), "draft"),
    ({"version": 9, "clips": []}, "Unknown plan version"),
    ({"version": plan.PLAN_VERSION, "clips": "no"}, "list of clips"),
])
def test_a_bad_plan_is_refused(bad, message):
    with pytest.raises(ValueError, match=message):
        plan.validate(bad)


# ---------------------------------------------------------------- hooks are checked drafts

@pytest.mark.parametrize("raw, expected", [
    ("  \"Why this changes everything\"  ", "Why this changes everything"),
    ("x" * 61, None), ("", None), (None, None), (5, None),
    ("Read more at https://spam.example", None), ("Big news #viral", None), ("Ask @someone now", None),
])
def test_hook_lines_are_checked(raw, expected):
    from app.highlights import clean_hook
    assert clean_hook(raw) == expected


def planned_clips(*modes):
    return [{"id": i + 1, "text": {"mode": m}, "cut": {"cut_start": 0.0, "cut_end": 10.0}, "hook": None}
            for i, m in enumerate(modes)]


def test_only_clips_with_trusted_speech_get_a_hook_draft(monkeypatch):
    asked = []
    monkeypatch.setattr(plan, "suggest_hook", lambda text: asked.append(text) or "A curious hook")
    unloaded = []
    monkeypatch.setattr(plan, "unload", lambda: unloaded.append(1))
    segments = [{"start": 1.0, "end": 4.0, "text": "something clear was said"}]
    items = planned_clips("captions", "pending")
    assert plan.suggest_hooks(items, segments) == "ok"
    assert items[0]["hook"] == {"text": "A curious hook", "status": "draft", "source": "ai"}
    assert items[1]["hook"] is None and len(asked) == 1          # the model never read the untrusted clip
    assert unloaded                                                # and its memory was given back


def test_an_unreachable_model_stops_asking_and_never_fails_the_job(monkeypatch):
    calls = []

    def down(text):
        calls.append(1)
        raise LLMError("no ollama")
    monkeypatch.setattr(plan, "suggest_hook", down)
    monkeypatch.setattr(plan, "unload", lambda: None)
    items = planned_clips("captions", "captions", "captions")
    assert "hooks skipped" in plan.suggest_hooks(items, [])
    assert len(calls) == 1 and all(i["hook"] is None for i in items)   # one failure, not three long waits


def test_a_hook_draft_is_not_burned_in_and_needs_approval():
    text = {"mode": "captions", "headline": None, "hook": None}
    plan.attach_hook(text, {"text": "A curious hook", "status": "draft", "source": "ai"})
    assert text["mode"] == "captions"                                  # still captions: nothing drawn
    assert text["hook"]["approved"] is False and text["hook"]["source"] == "ai"
    assert text["hook"]["style"]["seconds"] == 3
    plan.attach_hook(text, None)                                       # no hook: unchanged


# ---------------------------------------------------------------- creation: plan, then execute

def transcript_with_a_pause(folder):
    """20 s of speech with a 3 s silence in the middle (words stop at 8 s and resume at 11 s)."""
    ws, t = [], 0.0
    for i in range(40):
        if abs(t - 8.0) < 0.01:
            t = 11.0
        ws.append({"word": f"w{i}", "start": round(t, 2), "end": round(t + 0.35, 2), "probability": 0.9})
        t += 0.4
    seg = {"start": ws[0]["start"], "end": ws[-1]["end"], "text": " ".join(w["word"] for w in ws), "words": ws}
    (folder / "transcript.json").write_text(json.dumps({"language": "hi", "segments": [seg]}))
    return ws


def run_creation(monkeypatch, work, *, remove_pauses=True, suggest_hook=True, verdict=RELIABLE, hook="A curious hook"):
    folder = work / "abcdef0123"
    folder.mkdir()
    (folder / "status.json").write_text(json.dumps({"status": "uploaded"}))
    ws = transcript_with_a_pause(folder)
    created = []

    def fake_create(f, n, m):
        created.append(m)
        return {"stages": ["picture", "text", "music"], "music": None,
                "framing": {"mode": "center", "reason": "test", "audio": {"applied": False}}}
    monkeypatch.setattr(pipeline.render, "create", fake_create)
    monkeypatch.setattr(pipeline, "_pauses", lambda f: ([(8.1, 10.9)], speech_envelope(30), 30.0))
    monkeypatch.setattr(pipeline, "_text_quality", lambda *a, **k: verdict)
    monkeypatch.setattr(pipeline.music, "pick_track", lambda mood, key: None)
    monkeypatch.setattr(pipeline, "pick_ai_clips", lambda *a: ([{"start": 0.0, "end": ws[-1]["end"], "title": "T",
                                                                  "reason": "R", "mood": "funny", "score": 7}], "ok"))
    monkeypatch.setattr(plan, "suggest_hook", lambda text: hook)
    monkeypatch.setattr(plan, "unload", lambda: None)
    pipeline._make_clips("abcdef0123", dict(use_ai=True, music=False, count=1, min_len=5, max_len=30,
                                            remove_pauses=remove_pauses, suggest_hook=suggest_hook))
    clip = json.loads((folder / "clips.json").read_text())["clips"][0]
    return folder, clip, created[0], json.loads((folder / "plan.json").read_text())


def test_creation_plans_first_tightens_the_pause_and_saves_everything(folders, monkeypatch):
    folder, clip, m, saved_plan = run_creation(monkeypatch, folders[0])
    assert len(clip["segments"]) == 2 and len(m["segments"]) == 2                 # the long pause was cut
    gap = m["segments"][1]["start"] - m["segments"][0]["end"]
    assert 2.0 < gap < 2.6                                                        # 2.8 s of silence -> a 0.5 s beat stays
    assert clip["duration"] < 20.0
    assert saved_plan["clips"][0]["removed_seconds"] > 2.0 and saved_plan["options"]["remove_pauses"] is True
    assert (folder / "clip_1.manifest.json").exists() and (folder / "plan.json").exists()
    assert clip["checks"]["status"] == "unchecked"                                 # checks are off in tests, never fatal


def test_the_hook_is_a_draft_on_the_clip_and_in_the_plan(folders, monkeypatch):
    folder, clip, m, saved_plan = run_creation(monkeypatch, folders[0])
    assert clip["text"]["mode"] == "captions"
    assert clip["text"]["hook"] == {**clip["text"]["hook"], "text": "A curious hook", "approved": False, "source": "ai"}
    assert saved_plan["clips"][0]["hook"]["status"] == "draft"
    assert m["text"]["hook"] is None and m["text"]["captions"]["words"]           # a draft is not drawn on the video


def test_both_helpers_can_be_turned_off(folders, monkeypatch):
    folder, clip, m, saved_plan = run_creation(monkeypatch, folders[0], remove_pauses=False, suggest_hook=False)
    whole = [{"start": m["clip"]["start"], "end": m["clip"]["end"]}]
    assert m["segments"] == whole and clip["segments"] == whole                    # nothing removed
    assert clip["text"].get("hook") is None and saved_plan["clips"][0]["hook"] is None


def test_an_untrusted_clip_gets_no_hook_and_no_ai_text_in_the_plan(folders, monkeypatch):
    folder, clip, m, saved_plan = run_creation(monkeypatch, folders[0], verdict=UNTRUSTED)
    assert clip["text"]["mode"] == "pending" and clip["text"].get("hook") is None
    plan_clip = saved_plan["clips"][0]
    assert plan_clip["hook"] is None and "title" not in plan_clip["pick"] and plan_clip["caption_words"] == 0


def test_a_model_that_is_down_still_gives_a_finished_job(folders, monkeypatch):
    def down(text):
        raise LLMError("no ollama")
    folder, clip, m, saved_plan = (lambda: None, None, None, None)
    monkeypatch.setattr(plan, "suggest_hook", down)
    folder = folders[0] / "abcdef0123"
    folder.mkdir()
    (folder / "status.json").write_text(json.dumps({"status": "uploaded"}))
    ws = transcript_with_a_pause(folder)
    monkeypatch.setattr(pipeline.render, "create", lambda f, n, m: {"stages": [], "music": None, "framing": {"mode": "center", "audio": {}}})
    monkeypatch.setattr(pipeline, "_pauses", lambda f: ([], speech_envelope(30), 30.0))
    monkeypatch.setattr(pipeline, "_text_quality", lambda *a, **k: RELIABLE)
    monkeypatch.setattr(pipeline.music, "pick_track", lambda mood, key: None)
    monkeypatch.setattr(pipeline, "pick_ai_clips", lambda *a: ([{"start": 0.0, "end": 12.0, "title": "T", "reason": "R", "mood": "funny"}], "ok"))
    monkeypatch.setattr(plan, "unload", lambda: None)
    pipeline._make_clips("abcdef0123", dict(use_ai=True, music=False, count=1, min_len=5, max_len=30))
    saved = json.loads((folder / "clips.json").read_text())
    assert saved["status"] == "done" and saved["clips"][0]["text"].get("hook") is None
    assert any("hooks skipped" in n for n in json.loads((folder / "plan.json").read_text())["notes"])


# ---------------------------------------------------------------- owner and usage

def test_new_projects_record_an_owner_and_old_ones_default_to_local(folders):
    job_id, folder = jobs.create_job()
    assert json.loads((folder / "meta.json").read_text())["owner_id"] == jobs.LOCAL_OWNER
    old = folders[0] / "abcdef0123"
    old.mkdir()
    assert jobs.owner_of("abcdef0123") == jobs.LOCAL_OWNER           # a project from before owners existed


def test_usage_is_logged_per_project_and_never_breaks_work(folders):
    job_id, folder = jobs.create_job()
    with jobs.timed(job_id, "render", clip=1):
        pass
    with pytest.raises(RuntimeError):
        with jobs.timed(job_id, "render", clip=2):
            raise RuntimeError("boom")
    lines = [json.loads(l) for l in (folder / "usage.jsonl").read_text().splitlines()]
    assert [(l["kind"], l["clip"], l["ok"]) for l in lines] == [("render", 1, True), ("render", 2, False)]
    assert all(l["owner_id"] == "local" and l["seconds"] >= 0 for l in lines)
    jobs.record_usage("0000000000", "x", 1.0)                       # an unknown project: silently ignored
