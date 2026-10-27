"""Choose clip time ranges from a transcript (simple rule-based version).

Phase 2 will replace pick_clips() with an AI-based choice. The output format
(a list of {"start", "end", "reason"}) stays the same.
"""


def pick_clips(segments: list[dict], min_len: float = 30, max_len: float = 60,
               count: int = 3) -> list[dict]:
    """Group whole sentences (segments) into windows of min_len..max_len seconds.

    A clip always starts at the beginning of a sentence and ends at the end
    of one, so we never cut a sentence in the middle.
    """
    clips = []
    i = 0
    while i < len(segments) and len(clips) < count:
        start = segments[i]["start"]
        j = i
        # extend sentence by sentence until the clip is long enough
        while j < len(segments) and segments[j]["end"] - start < min_len:
            j += 1
        if j >= len(segments):  # ran out of video
            j = len(segments) - 1
        # if we overshot max_len, step back to the last sentence that fits
        while j > i and segments[j]["end"] - start > max_len:
            j -= 1
        end = segments[j]["end"]
        if end - start >= min(min_len, 5):  # skip tiny leftovers
            clips.append({"start": start, "end": end,
                          "reason": "Basic pick: consecutive full sentences."})
        i = j + 1
    return clips
