"""The pipeline records a text-quality verdict with each clip. (Stage 1 only recorded it; since
Stage 2 an untrusted clip is made with no text and waits for the user: see test_text_modes.py.)"""
import json

import numpy as np

from app import jobs, pipeline
from tests.test_quality import HINDI, good_asr, speech_envelope, words


def make_transcript_job(work, tokens, job_id="abcdef0123", with_confidence=True):
    folder = work / job_id
    folder.mkdir()
    (folder / "status.json").write_text(json.dumps({"status": "uploaded"}))
    ws = words(tokens, p=0.9 if with_confidence else None)
    seg = {"start": ws[0]["start"], "end": ws[-1]["end"], "text": " ".join(tokens), "words": ws}
    transcript = {"language": "hi", "segments": [seg]}
    if with_confidence:
        transcript.update(asr=good_asr(ws[-1]["end"]), dropped=[])
    (folder / "transcript.json").write_text(json.dumps(transcript, ensure_ascii=False))
    return job_id, folder


def run(monkeypatch, work, tokens, **kw):
    job, folder = make_transcript_job(work, tokens, **kw)
    exported = []

    def fake_create(folder, n, m):
        exported.append({"cap_words": (m["text"]["captions"] or {}).get("words", [])})   # what it was told to draw
        return {"stages": ["picture", "text", "music"], "music": None,
                "framing": {"mode": "center", "reason": "test", "audio": {"applied": False}}}
    monkeypatch.setattr(pipeline.render, "create", fake_create)
    monkeypatch.setattr(pipeline, "_pauses", lambda f: ([], speech_envelope(30), 30.0))
    pipeline._make_clips(job, dict(use_ai=False, music=False, count=1, min_len=5, max_len=20))
    return json.loads((folder / "clips.json").read_text())["clips"], exported


def test_every_clip_gets_a_verdict_and_captions_are_unchanged(folders, monkeypatch):
    clips, exported = run(monkeypatch, folders[0], HINDI)
    q = clips[0]["text_quality"]
    assert q["verdict"] == "reliable" and q["evidence"] == "full"
    assert clips[0]["captions"]["words"] and exported[0]["cap_words"]       # still drawn, as before


def test_a_bad_clip_is_recorded_as_bad_and_gets_no_captions(folders, monkeypatch):
    clips, exported = run(monkeypatch, folders[0], HINDI[:10] + ["तो"] * 30)
    assert clips[0]["text_quality"]["verdict"] in ("unreliable", "unusable")
    assert "word_loop" in clips[0]["text_quality"]["hard"]
    assert exported[0]["cap_words"] == []


def test_a_job_made_before_confidence_data_still_works(folders, monkeypatch):
    clips, _ = run(monkeypatch, folders[0], HINDI, with_confidence=False)
    assert clips[0]["text_quality"]["evidence"] == "text_only"


def test_a_failing_check_never_stops_the_job(folders, monkeypatch):
    monkeypatch.setattr(pipeline.quality, "assess_clip", lambda *a, **k: 1 / 0)
    clips, exported = run(monkeypatch, folders[0], HINDI)
    assert clips[0]["text_quality"]["verdict"] == "unchecked" and exported
