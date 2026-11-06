"""The edit plan: what Auto Edit decided for every clip, written down BEFORE anything is rendered.

    pick      the moment the AI chose (start/end/title/reason/mood/score)
    cut       the padded cut points (cuts.refine)
    segments  the parts of that cut that are kept (long pauses removed), or None
    text      what text it may show (captions, or withheld when the speech is not trusted)
    hook      an AI-written hook line, only ever a DRAFT the user must approve

The plan is data: it is validated, saved as plan.json next to the clips (so it is always possible
to see what was decided and why), and only then executed (rendered). AI proposes; Python checks.
Later, AI + Manual and Custom Style use this same plan and just give the user a say before it runs.
"""
import json
from datetime import datetime, timezone
from pathlib import Path

from app import captionstyles, cuts, hinglish, textmode
from app.captions import words_in_clip
from app.highlights import LLMError, suggest_hook
from app.llm import unload

PLAN_VERSION = 1


def plan_clip(n: int, pick: dict, ctx: dict) -> dict:
    """Decide everything about clip `n` that does not need rendering.
    ctx: words, silences, envelope, media_end, style, remove_pauses, assess(cut) -> text_quality."""
    cut = cuts.refine(ctx["words"], ctx["silences"], pick["start"], pick["end"], ctx["media_end"], ctx["envelope"])
    text_quality = ctx["assess"](cut)
    text = textmode.initial_state(text_quality)
    cap_words = (hinglish.convert_words(words_in_clip(ctx["words"], cut["cut_start"], cut["cut_end"]),
                                        ctx["style"].script)
                 if text["mode"] == "captions" else [])
    params = ctx.get("pause_params", {}) if ctx["remove_pauses"] else None
    kept = (cuts.pause_segments(ctx["silences"], ctx["words"], cut["cut_start"], cut["cut_end"], **params)
            if params is not None else None)
    return {"id": n, "pick": pick, "cut": cut, "text_quality": text_quality, "text": text,
            "cap_words": cap_words, "segments": kept if kept and len(kept) > 1 else None, "hook": None}


def clip_text(segments: list[dict], cut: dict) -> str:
    """The clip's own sentences, for the model to read."""
    lo, hi = cut["cut_start"] - 0.5, cut["cut_end"] + 0.5
    return " ".join(seg["text"].strip() for seg in segments if seg["start"] >= lo and seg["end"] <= hi)


def suggest_hooks(planned: list[dict], segments: list[dict]) -> str:
    """Give every clip with trustworthy speech a hook DRAFT. Returns "ok", or why it stopped.
    Clips whose speech cannot be trusted never get one: the model would be writing about words
    nobody can vouch for. If the model cannot be reached, nothing is retried for the other clips."""
    try:
        for item in planned:
            if item["text"]["mode"] != "captions":
                continue
            hook = suggest_hook(clip_text(segments, item["cut"]))
            if hook:
                item["hook"] = {"text": hook, "status": "draft", "source": "ai"}
    except LLMError as e:
        return f"hooks skipped ({e})"
    finally:
        unload()          # free the model's memory before any video is rendered
    return "ok"


HOOK_SECONDS = 3      # a hook card stays on screen this long (unless the style says otherwise)


def attach_hook(entry_text: dict, hook: dict | None, seconds: int = HOOK_SECONDS,
                preset: str = captionstyles.DEFAULT_HEADLINE_PRESET) -> None:
    """Put a hook DRAFT on a clip's text block. It is not drawn on the video: the user previews and
    approves it first (see set_clip_hook), exactly like a headline they typed themselves."""
    if not hook:
        return
    style = captionstyles.resolve_headline(preset, {"seconds": seconds})
    entry_text["hook"] = {"text": hook["text"], "style": style.as_dict(), "approved": False, "source": "ai"}


# ---------------------------------------------------------------- checking and saving the plan

def validate(plan: dict) -> None:
    """Check a plan before it is rendered. Raises ValueError with a readable reason."""
    if plan.get("version") != PLAN_VERSION:
        raise ValueError(f"Unknown plan version {plan.get('version')!r}.")
    if not isinstance(plan.get("clips"), list):
        raise ValueError("A plan needs a list of clips.")
    seen = set()
    for c in plan["clips"]:
        n = c.get("id")
        if n in seen:
            raise ValueError(f"Clip {n} appears twice in the plan.")
        seen.add(n)
        cut = c.get("cut") or {}
        if not 0 <= cut.get("cut_start", -1) < cut.get("cut_end", -2):
            raise ValueError(f"Clip {n} has an unusable cut.")
        segs = c.get("segments")
        if segs:
            for a, b in segs:
                if not cut["cut_start"] - 1e-6 <= a < b <= cut["cut_end"] + 1e-6:
                    raise ValueError(f"Clip {n} keeps a part outside its cut.")
            for (a, b), (c2, d) in zip(segs, segs[1:]):
                if not b < c2:
                    raise ValueError(f"Clip {n} has overlapping kept parts.")
        hook = c.get("hook")
        if hook and (hook.get("status") != "draft" or not hook.get("text")):
            raise ValueError(f"Clip {n}: a hook must be a draft until the user approves it.")


def build(job_id: str, planned: list[dict], options: dict, note: str, hook_note: str) -> dict:
    """The whole plan as a document (no caption words and no AI text for untrusted clips)."""
    clips = []
    for c in planned:
        trusted = c["text"]["mode"] == "captions"
        pick = c["pick"]
        removed = 0.0
        if c["segments"]:
            removed = (c["cut"]["cut_end"] - c["cut"]["cut_start"]) - sum(b - a for a, b in c["segments"])
        clips.append({
            "id": c["id"],
            "pick": {"start": pick["start"], "end": pick["end"], "score": pick.get("score"),
                     **({"title": pick.get("title"), "reason": pick.get("reason"), "mood": pick.get("mood")}
                        if trusted else {})},
            "cut": c["cut"], "segments": c["segments"], "removed_seconds": round(removed, 2),
            "text_mode": c["text"]["mode"], "verdict": c["text_quality"].get("verdict"),
            "caption_words": len(c["cap_words"]), "hook": c["hook"]})
    plan = {"version": PLAN_VERSION, "job_id": job_id, "created_at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
            "options": {k: options[k] for k in ("min_len", "max_len", "count", "use_ai", "framing", "music",
                                                "caption_preset", "caption_script", "remove_pauses", "suggest_hook",
                                                "edit_mode", "style_id")
                        if k in options},
            "notes": [n for n in (note, hook_note) if n and n != "ok"], "clips": clips}
    validate(plan)
    return plan


def save(folder: Path, plan: dict) -> None:
    path = Path(folder) / "plan.json"
    tmp = path.with_name(path.name + ".tmp")
    tmp.write_text(json.dumps(plan, ensure_ascii=False, indent=1))
    tmp.replace(path)
