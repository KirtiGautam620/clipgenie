import gc
import importlib
import re
import subprocess
from pathlib import Path

from app.config import WHISPER_MODEL

SUPPORTED = {"en", "hi"}
# Whisper often calls Hindi/Hinglish one of its neighbours. We re-run those as Hindi.
HINDI_LIKE = {"ur", "ne", "mr", "sa", "pa", "gu", "bn"}
SENTENCE_END = ".?!।"


class NoSpeechError(Exception):
    """A readable problem to show to the user."""


def extract_audio(video: Path, wav: Path) -> None:
    """Pull the sound out of the video as 16 kHz mono WAV (what Whisper expects)."""
    subprocess.run(
        ["ffmpeg", "-loglevel", "error", "-y", "-i", str(video),
         "-vn", "-ac", "1", "-ar", "16000", str(wav)],
        check=True,
    )


def release_memory() -> None:
    """Free Whisper's model. On an 8 GB Mac this matters: Ollama and FFmpeg need the room."""
    try:
        module = importlib.import_module("mlx_whisper.transcribe")
        module.ModelHolder.model = None
        module.ModelHolder.model_path = None
        gc.collect()
        import mlx.core as mx
        mx.clear_cache()
    except Exception:  # never let clean-up break a job
        pass


def _is_garbage(seg: dict) -> bool:
    """Whisper's own warning signs for made-up text: repeats, or 'no speech' with low confidence."""
    text = seg["text"]
    return (seg.get("compression_ratio", 0) > 2.4
            or (seg.get("no_speech_prob", 0) > 0.6 and seg.get("avg_logprob", 0) < -1.0)
            or bool(re.search(r"(.)\1{7,}", text)))


def resegment(segments: list[dict], gap: float = 0.5, min_len: float = 1.5,
              clause_len: float = 4.0, max_len: float = 12.0) -> list[dict]:
    """Split Whisper's segments into sentence-sized pieces using the word timings.

    Whisper (especially for Hindi) often returns one long segment holding several
    sentences, and uses commas where a full stop belongs. We start a new piece:
      - after a full stop / question mark / "।", or a pause (once the piece is min_len long);
      - after a comma, once the piece is already clause_len long;
      - at max_len, but then at the last comma or biggest pause inside it, never mid-phrase.
    """
    words = [w for s in segments for w in s.get("words", [])]
    if not words:
        return segments
    out, cur = [], []

    def emit(part):
        out.append({"start": part[0]["start"], "end": part[-1]["end"],
                    "text": "".join(w["word"] for w in part).strip(), "words": list(part)})

    def split_point(part):
        """Index after which to cut an over-long piece: last comma, else biggest pause."""
        commas = [i for i, w in enumerate(part[:-1]) if w["word"].strip()[-1:] == ","]
        if commas:
            return commas[-1] + 1
        gaps = [(part[i + 1]["start"] - part[i]["end"], i) for i in range(len(part) - 1)]
        return max(gaps)[1] + 1 if gaps else len(part)

    for w in words:
        if cur:
            length = cur[-1]["end"] - cur[0]["start"]
            pause = w["start"] - cur[-1]["end"]
            last = cur[-1]["word"].strip()[-1:]
            if length >= min_len and (last in SENTENCE_END or pause >= gap
                                      or (last == "," and length >= clause_len)):
                emit(cur)
                cur = []
            elif length >= max_len:
                cut = split_point(cur)
                emit(cur[:cut])
                cur = cur[cut:]
        cur.append(w)
    if cur:
        emit(cur)
    return out


def transcribe(video: Path, work: Path, language: str | None = None) -> dict:
    """Return {"language": "hi", "segments": [{"start", "end", "text", "words"}, ...]}.

    language=None lets Whisper detect the language (English or Hindi only).
    """
    import mlx_whisper  # imported here so the server starts fast

    wav = work / "audio.wav"
    extract_audio(video, wav)

    def run(lang):
        return mlx_whisper.transcribe(str(wav), path_or_hf_repo=WHISPER_MODEL,
                                      language=lang, word_timestamps=True)
    try:
        result = run(language)
        detected = result["language"]
        if language is None and detected in HINDI_LIKE:
            result, detected = run("hi"), "hi"
    finally:
        release_memory()

    good = [s for s in result["segments"] if not _is_garbage(s)]
    if not good or not "".join(s["text"] for s in good).strip():
        raise NoSpeechError("ClipGenie could not find clear speech in this video. It works best "
                            "with videos where someone talks. If there is speech, try choosing "
                            "the language yourself.")
    if language is None and detected not in SUPPORTED:
        raise NoSpeechError(f"The speech sounds like '{detected}', but ClipGenie supports English "
                            "and Hindi. If it is English or Hindi, choose the language yourself.")

    segments = []
    for s in good:
        # Whisper sometimes emits half a character (shown as U+FFFD): remove it, and any
        # word that was nothing else.
        words = [{"start": round(w["start"], 2), "end": round(w["end"], 2),
                  "word": w["word"].replace("�", "")} for w in s.get("words", [])]
        words = [w for w in words if w["word"].strip()]
        segments.append({"start": round(s["start"], 2), "end": round(s["end"], 2),
                         "text": s["text"].replace("�", "").strip(), "words": words})
    return {"language": detected, "segments": resegment(segments)}
