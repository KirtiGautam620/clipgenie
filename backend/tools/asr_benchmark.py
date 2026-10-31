"""Compare Whisper models and settings on the same audio. A developer tool, not part of the app.

    cd backend
    .venv/bin/python tools/asr_benchmark.py WAV --start 60 --dur 120 \\
        --run mlx-community/whisper-small-mlx:default \\
        --run mlx-community/whisper-large-v3-turbo-q4:tuned [--reference fixed.txt] --out results/

Every run happens in its own process, so the measured memory is that model's own.
Reports: time (as a multiple of the audio length), peak memory, repeat loops, segments Whisper
itself flags as garbage, the worst memory pressure / swap / free disk seen during each run, and
(with --reference) the character error rate. It refuses to start, and stops a running model, when
the Mac is short of memory or disk.
"""
import argparse
import json
import re
import subprocess
import sys
import tempfile
import time
import unicodedata
from pathlib import Path

HINDI_PROMPT = "यह हिंदी में एक सामान्य बातचीत है।"

# Named bundles of decoding settings. "default" = what ClipGenie did before this benchmark.
OPTION_SETS = {
    "default": {},
    "noctx": {"condition_on_previous_text": False},
    "tuned": {"condition_on_previous_text": False, "hallucination_silence_threshold": 2.0},
    "tuned_prompt": {"condition_on_previous_text": False, "hallucination_silence_threshold": 2.0,
                     "initial_prompt": HINDI_PROMPT},
}


# ---------------------------------------------------------------- the measurements

def normalize(text: str) -> str:
    """Letters only, one space between words: so punctuation and spacing never count as errors."""
    text = unicodedata.normalize("NFC", text).lower()
    # Drop punctuation and symbols but keep letters AND combining marks: Devanagari vowel signs
    # and the virama are marks, and Python's \w would wrongly treat them as punctuation.
    text = "".join(" " if unicodedata.category(c)[0] in "PSZC" else c for c in text)
    return re.sub(r"\s+", " ", text).strip()


def edit_distance(a: str, b: str) -> int:
    prev = list(range(len(b) + 1))
    for i, ca in enumerate(a, 1):
        cur = [i]
        for j, cb in enumerate(b, 1):
            cur.append(min(prev[j] + 1, cur[j - 1] + 1, prev[j - 1] + (ca != cb)))
        prev = cur
    return prev[-1]


def cer(reference: str, hypothesis: str) -> float:
    """Character error rate: edits needed to turn the hypothesis into the reference, per
    reference character (spaces ignored). 0.0 = perfect; above 1.0 is possible."""
    ref, hyp = normalize(reference).replace(" ", ""), normalize(hypothesis).replace(" ", "")
    if not ref:
        return 0.0 if not hyp else 1.0
    return edit_distance(ref, hyp) / len(ref)


def repeat_loops(texts: list[str]) -> dict:
    """Whisper's classic failure: saying the same thing again and again. Two kinds:
    - repeated_lines / longest_run: a line identical to the line just before (2+ words);
    - word_run: the longest run of one word repeated inside the text ("तो तो तो तो ...")."""
    norm = [normalize(t) for t in texts]
    repeats = run = longest = 0
    for i in range(1, len(norm)):
        if len(norm[i].split()) >= 2 and norm[i] == norm[i - 1]:
            repeats += 1
            run += 1
            longest = max(longest, run)
        else:
            run = 0
    words = " ".join(norm).split()
    word_run = best = 0
    for i, w in enumerate(words):
        word_run = word_run + 1 if i and w == words[i - 1] else 1
        best = max(best, word_run)
    return {"repeated_lines": repeats, "longest_run": longest + (1 if longest else 0),
            "word_run": best if best >= 4 else 0}     # 2-3 repeats are normal speech ("बहुत बहुत")


def summarize(segments: list[dict], seconds: float, wall: float, rss_mb: float | None,
              reference: str | None = None) -> dict:
    texts = [s["text"].strip() for s in segments]
    flagged = sum(1 for s in segments if s.get("compression_ratio", 0) > 2.4 or
                  (s.get("no_speech_prob", 0) > 0.6 and s.get("avg_logprob", 0) < -1.0))
    out = {"segments": len(segments), "words": sum(len(t.split()) for t in texts),
           "seconds_audio": round(seconds, 1), "seconds_wall": round(wall, 1),
           "times_real_time": round(wall / seconds, 2), "peak_memory_mb": rss_mb,
           "flagged_garbage": flagged, **repeat_loops(texts)}
    if reference is not None:
        out["cer"] = round(cer(reference, " ".join(texts)), 3)
    return out


# ---------------------------------------------------------------- keeping the Mac healthy
# Four separate signals, because each one alone can mislead:
#  - pressure level: macOS's own verdict, the same green/yellow/red as Activity Monitor
#  - free memory %:  what the system says it can still hand out (includes reclaimable memory)
#  - swap:           how full it is, and how much it GREW since the run began (the swap file's size
#                    changes by itself, so "% full" alone is unreliable)
#  - free disk:      so a run can never fill the disk

MAX_SWAP_FRACTION = 0.85    # do not start above this share of swap in use
MAX_SWAP_GROWTH_MB = 1024   # stop a run if swap grows by this much while it works
MIN_FREE_PERCENT = 12       # do not start (or stop) when free memory falls this low
MIN_FREE_DISK_GB = 6        # do not start (or stop) when the disk has less than this free
GREEN, YELLOW, RED = 1, 2, 4    # kern.memorystatus_vm_pressure_level


class Overloaded(RuntimeError):
    """The Mac is short of resources: stop instead of making it worse."""


def parse_swap(text: str) -> tuple[float, float] | None:
    """(used MB, total MB) from `sysctl vm.swapusage` ('total = 7168.00M  used = 6050.56M')."""
    total, used = (re.search(rf"{k} = ([\d.]+)M", text) for k in ("total", "used"))
    return (float(used.group(1)), float(total.group(1))) if total and used else None


def parse_free_percent(text: str) -> int | None:
    m = re.search(r"free percentage: (\d+)%", text)
    return int(m.group(1)) if m else None


def read_resources(disk_path: str = "/") -> dict:
    """What the Mac looks like right now. A value is None if it could not be read."""
    import shutil

    def run(*cmd):
        try:
            return subprocess.run(cmd, capture_output=True, text=True, timeout=10).stdout
        except (OSError, subprocess.TimeoutExpired):
            return ""
    level = run("sysctl", "-n", "kern.memorystatus_vm_pressure_level").strip()
    swap = parse_swap(run("sysctl", "vm.swapusage"))
    return {"pressure_level": int(level) if level.isdigit() else None,
            "swap_used_mb": swap[0] if swap else None, "swap_total_mb": swap[1] if swap else None,
            "free_percent": parse_free_percent(run("memory_pressure")),
            "free_disk_gb": round(shutil.disk_usage(disk_path).free / 1e9, 1)}


def assess(now: dict, starting: bool, baseline_swap_mb: float | None = None) -> str | None:
    """None if all is well; otherwise a sentence saying why we must not start / must stop.
    Starting is stricter (green only) than carrying on (only red stops a run already going)."""
    level = now.get("pressure_level")
    if level is not None and level >= (YELLOW if starting else RED):
        return f"memory pressure is {'red' if level >= RED else 'yellow'} (level {level})"
    free = now.get("free_percent")
    if free is not None and free < MIN_FREE_PERCENT:
        return f"only {free}% of memory is free (limit {MIN_FREE_PERCENT}%)"
    used, total = now.get("swap_used_mb"), now.get("swap_total_mb")
    if starting and used is not None and total and used / total > MAX_SWAP_FRACTION:
        return f"swap is {used / total:.0%} full (limit {MAX_SWAP_FRACTION:.0%})"
    if not starting and used is not None and baseline_swap_mb is not None \
            and used - baseline_swap_mb > MAX_SWAP_GROWTH_MB:
        return f"swap grew by {used - baseline_swap_mb:.0f} MB during the run (limit {MAX_SWAP_GROWTH_MB})"
    disk = now.get("free_disk_gb")
    if disk is not None and disk < MIN_FREE_DISK_GB:
        return f"only {disk} GB of disk is free (limit {MIN_FREE_DISK_GB} GB)"
    return None


def check_resources(starting: bool = True, baseline_swap_mb: float | None = None) -> str | None:
    return assess(read_resources(), starting, baseline_swap_mb)


def worst_of(samples: list[dict]) -> dict:
    """The worst values seen across a run's samples, for the report."""
    def pick(key, fn):
        values = [s[key] for s in samples if s.get(key) is not None]
        return fn(values) if values else None
    return {"pressure_level_max": pick("pressure_level", max), "swap_used_mb_max": pick("swap_used_mb", max),
            "free_percent_min": pick("free_percent", min), "free_disk_gb_min": pick("free_disk_gb", min),
            "samples": len(samples)}


def _run_guarded(cmd: list[str], poll: float = 3.0) -> tuple[subprocess.CompletedProcess, dict]:
    """Run a child process and watch the Mac while it works. If resources run short, stop the child
    (politely, then firmly) and raise Overloaded. Returns (result, worst values seen)."""
    start = read_resources()
    samples = [start]
    proc = subprocess.Popen(cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True)
    try:
        while True:
            try:
                out, err = proc.communicate(timeout=poll)
                samples.append(read_resources())
                return subprocess.CompletedProcess(cmd, proc.returncode, out, err), worst_of(samples)
            except subprocess.TimeoutExpired:
                now = read_resources()
                samples.append(now)
                problem = assess(now, starting=False, baseline_swap_mb=start.get("swap_used_mb"))
                if problem:
                    raise Overloaded(problem)
    finally:
        if proc.poll() is None:          # also on Ctrl+C or any error: never leave the child behind
            proc.terminate()
            try:
                proc.communicate(timeout=10)
            except subprocess.TimeoutExpired:
                proc.kill()
                proc.communicate()


# ---------------------------------------------------------------- running one model

def _slice_audio(wav: Path, start: float, dur: float, out: Path) -> None:
    subprocess.run(["ffmpeg", "-loglevel", "error", "-y", "-ss", str(start), "-t", str(dur),
                    "-i", str(wav), "-ac", "1", "-ar", "16000", str(out)], check=True)


def run_one(wav: Path, model: str, opts_name: str, language: str, out: Path) -> None:
    """Child process: transcribe once and write the result as JSON."""
    import mlx_whisper
    t0 = time.time()
    result = mlx_whisper.transcribe(str(wav), path_or_hf_repo=model, language=language,
                                    word_timestamps=True, **OPTION_SETS[opts_name])
    wall = time.time() - t0
    out.write_text(json.dumps({"wall": wall, "segments": [
        {k: s.get(k) for k in ("start", "end", "text", "compression_ratio", "no_speech_prob",
                               "avg_logprob")} for s in result["segments"]]}, ensure_ascii=False))


def _peak_memory_mb(time_log: str) -> float | None:
    m = re.search(r"(\d+)\s+maximum resident set size", time_log)   # macOS: bytes
    return round(int(m.group(1)) / 1024 / 1024) if m else None


def benchmark(wav: Path, start: float, dur: float, runs: list[tuple[str, str]],
              language: str, reference: str | None, out_dir: Path) -> list[dict]:
    """runs = exact (model, settings name) pairs, executed one after another."""
    out_dir.mkdir(parents=True, exist_ok=True)
    rows = []
    with tempfile.TemporaryDirectory() as tmp:    # the slice is deleted when this block ends
        piece = Path(tmp) / "slice.wav"
        _slice_audio(wav, start, dur, piece)
        for model, name in runs:
            problem = check_resources(starting=True)    # one run at a time, only if the Mac has room
            if problem:
                (out_dir / "results.json").write_text(json.dumps(rows, ensure_ascii=False, indent=2))
                raise Overloaded(f"not starting {model.split('/')[-1]} / {name}: {problem}")
            result = Path(tmp) / "result.json"
            result.unlink(missing_ok=True)
            try:
                proc, seen = _run_guarded(
                    ["/usr/bin/time", "-l", sys.executable, __file__, "--child", str(piece), model,
                     name, language, str(result)])
            except Overloaded as e:
                (out_dir / "results.json").write_text(json.dumps(rows, ensure_ascii=False, indent=2))
                raise Overloaded(f"stopped {model.split('/')[-1]} / {name}: {e}") from e
            if proc.returncode or not result.exists():
                rows.append({"model": model, "opts": name, "error": proc.stderr[-300:], "resources": seen})
                continue
            data = json.loads(result.read_text())
            row = {"model": model.split("/")[-1], "opts": name,
                   **summarize(data["segments"], dur, data["wall"], _peak_memory_mb(proc.stderr), reference),
                   "resources": seen}
            rows.append(row)
            (out_dir / f"{row['model']}__{name}.txt").write_text(
                "\n".join(f"[{s['start']:.0f}s] {s['text'].strip()}" for s in data["segments"]))
    (out_dir / "results.json").write_text(json.dumps(rows, ensure_ascii=False, indent=2))
    return rows


def main() -> None:
    if len(sys.argv) > 1 and sys.argv[1] == "--child":   # internal: one run in its own process
        _, _, wav, model, name, language, out = sys.argv
        run_one(Path(wav), model, name, language, Path(out))
        return
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawTextHelpFormatter)
    ap.add_argument("wav", type=Path)
    ap.add_argument("--start", type=float, default=0)
    ap.add_argument("--dur", type=float, default=120)
    ap.add_argument("--run", action="append", required=True, metavar="MODEL:SETTINGS",
                    help="one exact configuration, e.g. mlx-community/whisper-small-mlx:default "
                         f"(settings: {', '.join(OPTION_SETS)}). Repeat for more; they run one at a time.")
    ap.add_argument("--language", default="hi")
    ap.add_argument("--reference", type=Path, help="text file with the correct transcript of the slice")
    ap.add_argument("--out", type=Path, required=True)
    args = ap.parse_args()
    reference = args.reference.read_text() if args.reference else None
    runs = []
    for item in args.run:
        model, _, name = item.rpartition(":")
        if not model or name not in OPTION_SETS:
            ap.error(f"--run must look like MODEL:SETTINGS with settings one of {list(OPTION_SETS)}: {item}")
        runs.append((model, name))
    try:
        rows = benchmark(args.wav, args.start, args.dur, runs, args.language, reference, args.out)
    except Overloaded as e:
        sys.exit(f"Stopped to protect your Mac: {e}. Results so far are in {args.out}/results.json")
    cols = ["model", "opts", "times_real_time", "peak_memory_mb", "repeated_lines", "word_run",
            "flagged_garbage", "words"] + (["cer"] if reference else [])
    print(" | ".join(cols))
    for r in rows:
        print(" | ".join(str(r.get(c, r.get("error", ""))) for c in cols))


if __name__ == "__main__":
    main()
