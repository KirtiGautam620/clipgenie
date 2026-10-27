"""Copyright-safe workflow: who owns the source, what music licence applies, and the
checklist that must be completed before a clip can be downloaded.

ClipGenie records what YOU declare. It cannot check ownership, and it cannot promise that
a platform's copyright system (like YouTube's Content ID) will not flag a clip.
"""
import json
from datetime import datetime, timezone

from app import jobs

SOURCE_RIGHTS = {
    "own": "I made this video / I own it",
    "permission": "I have the owner's permission to edit and publish it",
    "licensed": "It is public domain or has a licence that allows reuse (for example CC BY)",
    "unsure": "I am not sure",
}
# Choices that allow importing from a link. "unsure" never does.
DOWNLOAD_OK = ("own", "permission", "licensed")

DISCLAIMER = (
    "Short clips are NOT automatically copyright-free. Cutting a video, adding captions or "
    "music, or changing its shape does not remove the original owner's rights. ClipGenie "
    "cannot check ownership and cannot promise that YouTube's Content ID or any other system "
    "will not flag a clip."
)


def save_source(job_id: str, rights: str, url: str | None = None, title: str = "",
                uploader: str = "") -> None:
    data = {"rights": rights, "url": url, "title": title, "uploader": uploader,
            "declared_at": _now()}
    (jobs.job_dir(job_id) / "provenance.json").write_text(json.dumps(data, ensure_ascii=False))


def load_source(job_id: str) -> dict:
    path = jobs.job_dir(job_id) / "provenance.json"
    if path.exists():
        return json.loads(path.read_text())
    return {"rights": "unsure", "url": None, "title": "", "uploader": ""}  # old jobs


def _now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


# ---------------------------------------------------------------- warnings and credits

def warnings(source: dict, clip: dict) -> list[str]:
    out = []
    if source["rights"] == "unsure":
        out.append("You are not sure you have the rights to this video. Do not publish clips "
                   "from it until you have confirmed them.")
    m = clip.get("music")
    if m:
        if m["warning"]:
            out.append(f"Music: {m['warning']}")
        if m["license"].startswith("Royalty-free"):
            out.append("Music: keep your licence or receipt for this track in case a platform asks.")
        if m["license"].startswith("CC BY") and m["attribution"]:
            out.append("Music: this licence requires credit. Paste the credits text below "
                       "into your video description.")
    return out


def credits_text(source: dict, clip: dict) -> str:
    lines = []
    m = clip.get("music")
    if m and m["attribution"]:
        lines.append(f"Music: {m['title']} — {m['attribution']} ({m['license']})")
    elif m and m["license"].startswith("CC0"):
        lines.append(f"Music: {m['title']} ({m['license']}, no credit required)")
    if source.get("url") and source["rights"] != "own":
        who = f" by {source['uploader']}" if source.get("uploader") else ""
        lines.append(f"Original video: {source.get('title') or source['url']}{who} — {source['url']}")
    return "\n".join(lines)


# ---------------------------------------------------------------- the checklist

def required_items(source: dict, clip: dict) -> list[dict]:
    items = []
    if source["rights"] == "unsure":
        items.append({"id": "source_unsure", "text":
                      "I understand I said I am NOT sure about my rights to this video, and I "
                      "will not publish this clip until I have confirmed them."})
    else:
        items.append({"id": "source_rights", "text":
                      "I own this video, or I have permission (or a licence) to edit and publish it."})
    items.append({"id": "third_party", "text":
                  "I checked that the clip contains no other people's music, footage, images or "
                  "logos that I do not have the right to use."})
    if clip.get("music"):
        items.append({"id": "music_licence", "text":
                      "I checked that the music licence shown allows my use, and I will add the "
                      "credits text to my video description where required."})
    items.append({"id": "no_guarantee", "text":
                  "I understand short clips are not automatically copyright-free and that "
                  "ClipGenie cannot promise a platform's copyright checks will not flag them."})
    items.append({"id": "reviewed", "text": "I watched the final clip and I am happy to publish it."})
    return items


def _checklist_path(job_id: str):
    return jobs.job_dir(job_id) / "checklist.json"


def _load_checklist(job_id: str) -> dict:
    path = _checklist_path(job_id)
    return json.loads(path.read_text()) if path.exists() else {}


def confirm(job_id: str, clip: dict, ticked: list[str]) -> list[str]:
    """Save a confirmation. Returns the ids still missing (empty list = confirmed)."""
    source = load_source(job_id)
    need = [i["id"] for i in required_items(source, clip)]
    missing = [i for i in need if i not in ticked]
    if missing:
        return missing
    data = _load_checklist(job_id)
    data[str(clip["id"])] = {"version": clip.get("version", 0), "items": need,
                             "confirmed_at": _now()}
    jobs.write_atomic(_checklist_path(job_id), json.dumps(data))
    return []


def is_confirmed(job_id: str, clip: dict) -> bool:
    """True only if confirmed for THIS version of the clip (changing the music resets it)."""
    entry = _load_checklist(job_id).get(str(clip["id"]))
    return bool(entry) and entry["version"] == clip.get("version", 0)


# ---------------------------------------------------------------- what the page sees

def enrich(job_id: str, clip: dict) -> dict:
    source = load_source(job_id)
    return {**clip,
            "warnings": warnings(source, clip),
            "credits": credits_text(source, clip),
            "checklist": required_items(source, clip),
            "confirmed": is_confirmed(job_id, clip)}


def report(job_id: str, clip: dict) -> dict:
    """A record of the rights information for one clip, to keep with your files."""
    source = load_source(job_id)
    entry = _load_checklist(job_id).get(str(clip["id"]))
    return {
        "generated_at": _now(),
        "disclaimer": DISCLAIMER,
        "source": {**source, "rights_label": SOURCE_RIGHTS.get(source["rights"])},
        "clip": {"id": clip["id"], "title": clip.get("title"), "start": clip["start"],
                 "end": clip["end"], "duration": clip["duration"]},
        "music": clip.get("music"),
        "warnings": warnings(source, clip),
        "credits_text": credits_text(source, clip),
        "checklist_confirmed": entry if entry and entry["version"] == clip.get("version", 0) else None,
    }
