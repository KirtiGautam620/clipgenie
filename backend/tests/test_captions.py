from app.captions import MAX_WORDS_PER_GROUP, make_groups


def w(text, start, end):
    return {"word": " " + text, "start": start, "end": end}


def test_groups_are_relative_to_clip_start():
    groups = make_groups([w("hello", 10.0, 10.4), w("world", 10.5, 11.0)], 10.0, 12.0)
    assert groups[0][0]["start"] == 0.0 and groups[0][1]["end"] == 1.0


def test_group_size_limit_and_punctuation_break():
    words = [w(f"w{i}", i * 0.3, i * 0.3 + 0.25) for i in range(9)]
    assert all(len(g) <= MAX_WORDS_PER_GROUP for g in make_groups(words, 0, 5))
    words = [w("Hi.", 0, 0.3), w("there", 0.4, 0.7), w("you", 0.8, 1.0)]
    assert [len(g) for g in make_groups(words, 0, 2)] == [1, 2]   # break after the full stop


def test_long_pause_starts_a_new_group():
    groups = make_groups([w("a", 0, 0.2), w("b", 2.0, 2.2)], 0, 3)
    assert len(groups) == 2


def test_words_outside_the_clip_are_ignored_and_hindi_is_kept():
    words = [w("before", 1, 2), w("नमस्ते", 5, 5.5), w("after", 9, 10)]
    groups = make_groups(words, 4.0, 8.0)
    assert [x["text"] for g in groups for x in g] == ["नमस्ते"]


def test_a_word_with_a_silly_long_duration_does_not_hold_the_screen(tmp_path, monkeypatch):
    """Whisper sometimes gives one word a 13-second duration. Its caption must not last that long."""
    from app import captions
    word_frames = []     # (seconds on screen) for frames that show a word, not blank filler

    def fake_run(cmd, check):
        lines = open(cmd[cmd.index("-i") + 1]).read().splitlines()
        for name, dur in zip(lines[0::2], lines[1::2]):
            if "blank" not in name and dur.startswith("duration"):
                word_frames.append(float(dur.split()[1]))
    monkeypatch.setattr(captions.subprocess, "run", fake_run)
    monkeypatch.setattr(captions, "_render_frame", lambda texts, active, out: out.write_bytes(b""))
    monkeypatch.setattr(captions.shutil, "rmtree", lambda p: None)
    captions.build_caption_track([w("hello", 0.0, 13.0), w("there", 13.1, 13.5)], 0.0, 14.0,
                                 tmp_path, "t")
    assert word_frames and max(word_frames) <= captions.MAX_WORD_SECONDS + 1e-6
    assert any(abs(d - captions.MAX_WORD_SECONDS) < 1e-6 for d in word_frames)   # it was capped
