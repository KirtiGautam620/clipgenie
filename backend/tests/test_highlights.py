from app import highlights as h


def seg(start, end, text="A real sentence about something."):
    return {"start": start, "end": end, "text": text, "words": []}


def test_filler_detection_english_and_hindi():
    for filler in ["Hi everyone, welcome back to the channel.", "Okay, that is about it.",
                   "Thanks for watching, see you next week.", "Now let me read a few comments.",
                   "आज के लिए बस इतना ही, धन्यवाद।", "नमस्ते दोस्तों, स्वागत है।"]:
        assert h.FILLER.search(filler), filler
    for real in ["I sat in my car and I cried for an hour.", "Done is better than perfect.",
                 "मैंने अपनी job छोड़ दी थी।", "The okay-ish results surprised me."]:
        assert not h.FILLER.search(real), real


def test_fix_bounds_trims_filler_at_the_edges_only():
    segs = [seg(0, 5, "Welcome back everyone."), seg(5, 20), seg(20, 35, "Thanks for watching!"),
            seg(35, 50)]
    assert h._fix_bounds(segs, 0, 2, 0, 4, 10, 60) == (1, 1)
    # filler in the middle is kept
    segs = [seg(0, 15), seg(15, 20, "Okay, so thanks."), seg(20, 40)]
    assert h._fix_bounds(segs, 0, 2, 0, 3, 10, 60) == (0, 2)


def test_fix_bounds_enforces_length_without_cutting_sentences():
    segs = [seg(i * 10, i * 10 + 9) for i in range(10)]
    first, last = h._fix_bounds(segs, 0, 9, 0, 10, 10, 40)
    assert segs[last]["end"] - segs[first]["start"] <= 40
    assert (first, last) == (0, 3)            # whole sentences only


def test_fix_bounds_grows_short_clips_forward_then_backward():
    segs = [seg(0, 10), seg(10, 20), seg(20, 30, "Okay so anyway."), seg(30, 40)]
    # too short at [1,1]; the next sentence is filler, so it grows backward instead
    assert h._fix_bounds(segs, 1, 1, 0, 4, 18, 60) == (0, 1)


def test_fix_bounds_rejects_impossible_clips():
    segs = [seg(0, 2)]
    assert h._fix_bounds(segs, 0, 0, 0, 1, 30, 60) is None   # far shorter than allowed
    assert h._fix_bounds(segs, 5, 3, 0, 1, 30, 60) is None   # nonsense range


def test_drop_overlaps_keeps_the_earlier_better_clip():
    clips = [{"first": 0, "last": 5}, {"first": 4, "last": 9}, {"first": 10, "last": 12}]
    assert h._drop_overlaps(clips) == [{"first": 0, "last": 5}, {"first": 10, "last": 12}]


def test_ai_unavailable_falls_back_to_basic_picker(monkeypatch):
    def boom(*a, **k):
        raise h.LLMError("down")
    monkeypatch.setattr(h, "ask_json", boom)
    monkeypatch.setattr(h, "unload", lambda: None)     # do not touch the real Ollama
    segs = [seg(i * 10, i * 10 + 9) for i in range(8)]
    clips, note = h.pick_ai_clips(segs, 20, 40, 2)
    assert clips and "AI unavailable" in note
