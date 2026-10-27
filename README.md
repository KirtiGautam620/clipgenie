# clipgenie
A free, locally running AI video clipping agent for Hindi and English videos, with captions, background music, and Shorts export.

Drop in a long video (an MP4 you upload, or a YouTube link to a video you own) and ClipGenie finds the
most engaging moments, cuts them into vertical 9:16 clips with animated captions, adds background music
that fits the mood, and lets you preview and download them. Everything runs on your own Mac: no paid
APIs, no cloud, no accounts.

## How it works

```
video -> Whisper (speech to text, internal only) -> local AI (Ollama) picks complete, engaging moments
      -> FFmpeg cuts, crops to 9:16, burns in captions -> music is mixed in with ducking -> you download
```

The transcript is only used internally to understand the video. It is not shown or edited in the app.

## Requirements (Apple Silicon Mac)

| Tool | Why | Install |
|---|---|---|
| Python 3.12 + [uv](https://docs.astral.sh/uv/) | backend | `brew install uv` |
| Node.js 20+ | web page | `brew install node` |
| FFmpeg | video and audio editing | `brew install ffmpeg` |
| [Ollama](https://ollama.com) | local AI (optional but recommended) | download the app, then `ollama pull qwen2.5:3b` |

## Run it

```bash
./run.sh
```

Then open http://localhost:5173. The first run sets everything up and downloads the Whisper model
(about 1 GB). Press Ctrl+C to stop.

## Using it

1. Choose a video file, or paste a YouTube link (only for videos you own or have permission to use).
2. Say who owns the video. This is required.
3. Press **Create my clips**.
4. Preview the clips. Change the music or its volume under each clip if you like.
5. Press **Download…**, complete the copyright checklist, and download.

## Music

Only music from the **Music library** is ever used. Five simple starter tracks (generated from
scratch, public domain) are created for you. To use better music, add tracks you made, bought, or
that are free to use, and choose the correct licence for each one. Tracks with an unknown licence are
flagged with a warning.

## Copyright

Please read [docs/COPYRIGHT.md](docs/COPYRIGHT.md). In short: short clips are not automatically
copyright-free, and ClipGenie cannot check ownership or promise that YouTube's Content ID will not
flag a clip.

## Project layout

```
backend/    FastAPI server (app/), starter-music generator (tools/), tests (tests/)
frontend/   React web page (Vite)
data/       your videos, clips and music (never committed to git)
docs/       copyright notes
run.sh      starts everything
```

## Tests

```bash
cd backend
uv pip install --python .venv/bin/python -r requirements-dev.txt
.venv/bin/python -m pytest
```

## Known limits

- The small local AI (3B model, chosen for 8 GB of RAM) finds fewer and less polished highlights than
  a large cloud model. Expect fewer clips than you ask for from short videos.
- Hinglish transcription is imperfect, so captions may contain mistakes.
- Vertical framing is a centre crop (or a blurred-background fit). It does not follow faces yet.
- Only one video is processed at a time.
