"""The download: a zip with the plan, every scene's prompt, and reference frames cropped from the photo."""
import json
import zipfile
from io import BytesIO
from pathlib import Path

from PIL import Image

from app.storyboard import frames, model, prompts

FRAME_LONG_SIDE = 1280


def _markdown(sb: model.Storyboard, geo: dict) -> str:
    lines = [
        f"# {sb.title}", "",
        "Made with CocoGenie AI Storyboard. This is a **shot plan built from templates and your prompt**, with "
        "reference frames cropped from your own photo. It is not an AI-generated video, and the reference frames "
        "show framing only, not new camera angles.", "",
        f"- Photo: `photo.jpg` ({sb.photo['width']} x {sb.photo['height']})",
        f"- Format: {prompts.ASPECT_WORDS[sb.aspect]}", f"- Style: {sb.style}",
        f"- Product: {sb.product or '(not described)'}", f"- Your prompt: {sb.prompt or '(none)'}", "",
        "## How to use this", "",
        "1. Open the video generator you want to use (for example Google Flow). Check that tool's own limits, "
        "pricing and terms: CocoGenie cannot promise what any tool will make from these prompts.",
        "2. Upload `photo.jpg` as the reference image for every scene.",
        "3. Paste each scene's prompt (also all together in `prompts.txt`). The frames in `reference/` show the "
        "framing planned for each scene and can be used as extra guidance if the tool accepts them.", "",
        "## Scenes", ""]
    for n, s in enumerate(sb.scenes, 1):
        g = geo[s.id]["sharpness"]
        lines += [f"### Scene {n}: {s.title}", "",
                  f"- Length: {s.duration:g} s, arrives with: {s.transition}",
                  f"- Camera: {s.camera}", f"- Shows: {s.detail}",
                  f"- Reference frames: `reference/scene_{n:02d}_start.jpg`, `reference/scene_{n:02d}_end.jpg` "
                  f"(photo detail: {g['label']})", "", "Prompt:", "", "```text", s.prompt, "```", ""]
    return "\n".join(lines)


def build(sb: model.Storyboard, photo_file: Path) -> bytes:
    """The package as zip bytes. The caller checks rights and consent first."""
    geo = {s.id: frames.geometry(sb.photo["width"], sb.photo["height"], sb.aspect, s) for s in sb.scenes}
    data = model.to_dict(sb)
    scenes = data["scenes"]
    out = BytesIO()
    with zipfile.ZipFile(out, "w", zipfile.ZIP_DEFLATED) as z, Image.open(photo_file) as photo:
        photo.load()
        z.write(photo_file, "photo.jpg")
        z.writestr("storyboard.md", _markdown(sb, geo))
        z.writestr("prompts.txt", prompts.prompts_text(sb.title, sb.aspect, scenes))
        z.writestr("storyboard.json", json.dumps({**data, "geometry": geo}, ensure_ascii=False, indent=2))
        for n, (s, scene) in enumerate(zip(sb.scenes, scenes), 1):
            g = geo[s.id]
            for which in ("start", "end"):
                z.writestr(f"reference/scene_{n:02d}_{which}.jpg",
                           frames.render(photo, tuple(g[which]), sb.aspect, FRAME_LONG_SIDE, 90))
    return out.getvalue()
