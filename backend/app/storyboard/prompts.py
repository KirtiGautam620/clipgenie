"""The prompt for each scene, written for an external video generator.

These are composed from fixed wording plus the user's own words (product, style). They are plain
text: ClipGenie does not know what any particular generator will do with them, and says so.
"""
from app.storyboard.shots import ASPECTS, STYLE_INFO

ASPECT_WORDS = {"9:16": "vertical 9:16", "16:9": "horizontal 16:9"}
KEEP = ("Keep the product exactly as in the reference photo: the same shape, colours, materials, label text "
        "and logo. Do not invent or change any text, logos or packaging details.")
NO_TEXT = "No on-screen text, captions or watermarks."


def _sentence(text: str) -> str:
    text = text.strip().rstrip(".")
    return text[:1].upper() + text[1:] + "." if text else ""


def compose_scene(*, camera: str, detail: str, duration: float, product: str, style: str, aspect: str) -> str:
    """The prompt for one scene. It does not depend on where the scene sits, so reordering, adding or
    deleting scenes never makes a prompt wrong."""
    if aspect not in ASPECTS:
        raise ValueError(f"aspect must be one of: {', '.join(ASPECTS)}")
    subject = product.strip() or "the product in the reference photo"
    lines = [f"Create a {duration:g}-second {ASPECT_WORDS[aspect]} video clip using the attached reference "
             f"photo of {subject}.",
             f"Camera: {camera.strip().rstrip('.')}.", f"Shows: {_sentence(detail)}"]
    phrase = STYLE_INFO[style].phrase
    if phrase:
        lines.append(f"Style: {phrase}.")
    lines += [KEEP, NO_TEXT]
    return "\n".join(lines)


def prompts_text(title: str, aspect: str, scenes: list[dict]) -> str:
    """Every scene's prompt in one block, to copy in one go."""
    head = [f"Storyboard: {title}",
            f"Format: {ASPECT_WORDS[aspect]}. Use the same reference photo for every scene.", ""]
    body = []
    for n, s in enumerate(scenes, 1):
        body += [f"=== Scene {n}: {s['title']} ({s['duration']:g} s) ===", s["prompt"], ""]
    return "\n".join(head + body).rstrip() + "\n"
