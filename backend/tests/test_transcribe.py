import pytest

from app import transcribe as tr


def w(text, start, end):
    return {"word": " " + text, "start": start, "end": end}


def test_resegment_splits_long_hindi_segment_at_pauses_and_full_stops():
    words = [w("नमस्ते", 0.0, 0.6), w("दोस्तों", 0.7, 1.3), w("स्वागत", 1.4, 1.9), w("है।", 2.0, 2.4),
             w("आज", 3.2, 3.6), w("मैं", 3.7, 4.0), w("बताऊँगा", 4.1, 4.8),
             w("एक", 5.6, 5.9), w("कहानी", 6.0, 6.6)]
    out = tr.resegment([{"start": 0, "end": 6.6, "text": "x", "words": words}])
    assert [s["text"] for s in out] == ["नमस्ते दोस्तों स्वागत है।", "आज मैं बताऊँगा", "एक कहानी"]
    assert out[1]["start"] == 3.2 and out[1]["end"] == 4.8


def test_resegment_uses_commas_when_there_are_no_pauses_or_full_stops():
    # continuous speech, Whisper wrote commas: cut after a comma once a clause is long enough
    words = [w(f"w{i}" + ("," if i % 6 == 5 else ""), i * 0.7, i * 0.7 + 0.7) for i in range(24)]
    out = tr.resegment([{"words": words}])
    assert len(out) >= 3
    assert all(s["text"].endswith(",") or s is out[-1] for s in out)        # cut at commas only


def test_resegment_cuts_overlong_text_at_the_last_comma_not_mid_phrase():
    words = [w("a", 0, 3), w("b,", 3, 6), w("c", 6, 9), w("d", 9, 12), w("e", 12, 14), w("f", 14, 16)]
    out = tr.resegment([{"words": words}], clause_len=99)      # only the hard cap applies
    assert out[0]["text"] == "a b,"                            # not "a b, c d"


def test_resegment_never_makes_tiny_or_huge_pieces():
    short = [w("a", 0, 0.3), w("b", 1.2, 1.5), w("c", 2.5, 2.8)]       # pauses, but each piece < 1.5s
    assert len(tr.resegment([{"words": short}])) <= 2
    endless = [w(f"w{i}", i * 0.4, i * 0.4 + 0.35) for i in range(80)]   # 32 s with no pause
    assert all(s["end"] - s["start"] <= 15 for s in tr.resegment([{"words": endless}]))


def test_resegment_keeps_segments_without_word_timings():
    segs = [{"start": 0, "end": 3, "text": "hello", "words": []}]
    assert tr.resegment(segs) == segs


def test_garbage_segments_are_recognised():
    assert tr._is_garbage({"text": "ស្្្្្្្្្្្្្្្្្្្្", "avg_logprob": -0.3})
    assert tr._is_garbage({"text": "thanks", "compression_ratio": 3.1})
    assert tr._is_garbage({"text": "hmm", "no_speech_prob": 0.9, "avg_logprob": -1.5})
    assert not tr._is_garbage({"text": "Done is better than perfect.", "avg_logprob": -0.2,
                               "no_speech_prob": 0.01, "compression_ratio": 1.4})


def fake_whisper(monkeypatch, languages, segments):
    """Make mlx_whisper return `segments`, with `languages` detected on successive calls."""
    import sys
    import types
    calls = []
    langs = iter(languages)

    def transcribe(path, path_or_hf_repo, language, word_timestamps):
        calls.append(language)
        return {"language": language or next(langs), "segments": segments}
    monkeypatch.setitem(sys.modules, "mlx_whisper", types.SimpleNamespace(transcribe=transcribe))
    monkeypatch.setattr(tr, "extract_audio", lambda *a: None)
    monkeypatch.setattr(tr, "release_memory", lambda: None)
    return calls


GOOD = [{"start": 0, "end": 3, "text": "Hello there", "avg_logprob": -0.2,
         "words": [w("Hello", 0, 1), w("there", 1.1, 2)]}]


def test_hindi_neighbours_are_rerun_as_hindi(tmp_path, monkeypatch):
    calls = fake_whisper(monkeypatch, ["ur"], GOOD)
    assert tr.transcribe(tmp_path / "v.mp4", tmp_path)["language"] == "hi"
    assert calls == [None, "hi"]


def test_unsupported_language_is_refused_with_advice(tmp_path, monkeypatch):
    fake_whisper(monkeypatch, ["nn"], GOOD)
    with pytest.raises(tr.NoSpeechError, match="choose the language"):
        tr.transcribe(tmp_path / "v.mp4", tmp_path)


def test_chosen_language_is_trusted(tmp_path, monkeypatch):
    fake_whisper(monkeypatch, [], GOOD)
    assert tr.transcribe(tmp_path / "v.mp4", tmp_path, "en")["language"] == "en"


def test_a_video_without_speech_is_refused(tmp_path, monkeypatch):
    junk = [{"start": 0, "end": 5, "text": "ʰᴀᴀᴀᴀᴀᴀᴀᴀᴀᴀᴀᴀᴀ", "avg_logprob": -2, "words": []}]
    fake_whisper(monkeypatch, ["en"], junk)
    with pytest.raises(tr.NoSpeechError, match="clear speech"):
        tr.transcribe(tmp_path / "v.mp4", tmp_path)


def test_broken_characters_are_removed_from_captions(tmp_path, monkeypatch):
    seg = [{"start": 0, "end": 3, "text": "कि तु � बरबाद", "avg_logprob": -0.2,
            "words": [w("कि", 0, 0.5), w("तु", 0.6, 1.0), w("�", 1.1, 1.3), w("बरबाद", 1.4, 2.0)]}]
    fake_whisper(monkeypatch, [], seg)
    out = tr.transcribe(tmp_path / "v.mp4", tmp_path, "hi")
    assert "�" not in out["segments"][0]["text"]
    assert [x["word"].strip() for x in out["segments"][0]["words"]] == ["कि", "तु", "बरबाद"]
