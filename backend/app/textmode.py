"""What text a clip shows: word-level captions, a headline, or nothing, and who decided.

Every new clip has a `text` block in clips.json:

    {"mode": "captions" | "pending" | "headline" | "none",
     "verdict": "reliable" | "unreliable" | "unusable" | "unchecked",
     "reasons": [...],                     # plain-language, never transcript text
     "headline": {"text", "style", "approved", "source"} | None}

    captions  the words were judged trustworthy: captions are drawn (as before)
    pending   the words could NOT be trusted: no text is drawn and the clip cannot be downloaded
              until the user chooses a headline or "no text"
    headline  the user previewed and approved a headline
    none      the user chose to export without text

Clips made before this existed have no block: they are treated as "captions" (already burned in).
The raw transcript stays in transcript.json for processing; nothing that came from an untrusted
transcript (words, the AI's title and reason) is shown while a clip is not trusted.
"""
from copy import deepcopy

DECISION_NEEDED = ("The speech in this clip could not be turned into trustworthy captions. Choose a "
                   "headline or export without text first.")
CAPTIONS_UNAVAILABLE = ("Captions are not available for this clip because its speech could not be "
                        "trusted. Use a headline, or export without text.")
UNTRUSTED = ("unreliable", "unusable")


def legacy_state() -> dict:
    return {"mode": "captions", "verdict": "legacy", "reasons": [], "headline": None}


def text_state(clip: dict) -> dict:
    return clip.get("text") or legacy_state()


def is_untrusted(clip: dict) -> bool:
    return text_state(clip).get("verdict") in UNTRUSTED


def needs_decision(clip: dict) -> bool:
    return text_state(clip).get("mode") == "pending"


def initial_state(text_quality: dict) -> dict:
    """The starting text block for a new clip, from its quality verdict."""
    verdict = text_quality.get("verdict", "unchecked")
    mode = "pending" if verdict in UNTRUSTED else "captions"
    return {"mode": mode, "verdict": verdict, "reasons": list(text_quality.get("reasons", [])),
            "headline": None}


def withhold(entry: dict) -> None:
    """Take the transcript-derived fields out of sight for a clip whose speech is not trusted.
    The AI's title, reason and mood were written from the same transcript, so they could misstate
    what the speaker said. They are kept under `withheld` (never sent to the page)."""
    entry["withheld"] = {k: entry.get(k) for k in ("title", "reason", "mood") if k in entry}
    entry["title"] = f"Clip {entry['id']}"
    entry["reason"] = ""
    entry["mood"] = "other"


def public(clip: dict) -> dict:
    """The clip as the page may see it: no withheld text, and no words of an untrusted clip."""
    out = deepcopy(clip)
    out.pop("withheld", None)
    state = text_state(clip)
    out["text"] = {**state, "needs_decision": state.get("mode") == "pending"}
    if is_untrusted(clip):
        out.pop("captions", None)
    return out
