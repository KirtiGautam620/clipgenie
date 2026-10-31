"""Run the transcript quality check on clips that already exist, so we can see how often it fires
BEFORE anything depends on it. A developer tool; it prints verdicts and reasons, never transcripts.

    cd backend
    .venv/bin/python tools/quality_report.py                 # every job in data/work
    .venv/bin/python tools/quality_report.py 126f73661f      # chosen jobs
    .venv/bin/python tools/quality_report.py --benchmark ../data/benchmarks/asr/slice1_*   # benchmark outputs
"""
import argparse
import json
import re
import sys
from collections import Counter
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from app import cuts, quality  # noqa: E402

WORK = Path(__file__).resolve().parents[2] / "data" / "work"


def job_rows(job: Path) -> list[dict]:
    transcript_file, clips_file = job / "transcript.json", job / "clips.json"
    if not transcript_file.exists() or not clips_file.exists():
        return []
    transcript = json.loads(transcript_file.read_text())
    clips = json.loads(clips_file.read_text()).get("clips", [])
    words = [w for s in transcript["segments"] for w in s["words"]]
    wav = job / "audio.wav"
    envelope = cuts.load_envelope(wav) if wav.exists() else None
    rows = []
    for c in clips:
        start, end = (c.get("cut") or {}).get("cut_start", c["start"]), (c.get("cut") or {}).get("cut_end", c["end"])
        verdict = quality.assess_clip(
            quality.words_between(words, start, end), start, end, language=transcript.get("language", "hi"),
            asr=transcript.get("asr"), dropped=transcript.get("dropped"),
            lines=quality.lines_between(transcript["segments"], start, end), envelope=envelope)
        rows.append({"job": job.name, "clip": c["id"], "seconds": round(end - start), "language": transcript.get("language"),
                     **verdict})
    return rows


def benchmark_rows(folder: Path) -> list[dict]:
    """Benchmark outputs hold only text lines ('[28s] words'), so only text signals can run."""
    rows = []
    for f in sorted(folder.glob("*.txt")):
        lines = [(int(m.group(1)), m.group(2)) for l in f.read_text().splitlines()
                 if (m := re.match(r"\[(\d+)s\]\s*(.*)", l))]
        if not lines:
            continue
        words, texts = [], []
        for i, (t0, text) in enumerate(lines):
            t1 = lines[i + 1][0] if i + 1 < len(lines) else t0 + 3
            toks = text.split()
            step = max(0.05, (t1 - t0) / max(1, len(toks)))
            words += [{"word": " " + tok, "start": t0 + k * step, "end": t0 + k * step + step * 0.8}
                      for k, tok in enumerate(toks)]
            texts.append(text)
        end = lines[-1][0] + 3
        rows.append({"job": f.stem, "clip": "-", "seconds": round(end), "language": "hi",
                     **quality.assess_clip(words, 0, end, language="hi", lines=texts)})
    return rows


def show(rows: list[dict]) -> None:
    print(f"{'job / run':46s} {'clip':>4s} {'sec':>4s}  {'verdict':10s} {'evidence':9s} {'trusted':>7s}  hard | soft")
    for r in rows:
        trusted = f"{r['trusted_fraction']:.0%}" if r.get("trusted_fraction") is not None else "-"
        print(f"{r['job']:46s} {str(r['clip']):>4s} {r['seconds']:>4d}  {r['verdict']:10s} {r['evidence']:9s} "
              f"{trusted:>7s}  {','.join(r['hard']) or '-'} | {','.join(r['soft']) or '-'}")
    print()
    by_verdict = Counter(r["verdict"] for r in rows)
    by_evidence = Counter(r["evidence"] for r in rows)
    print("verdicts:", dict(by_verdict), " evidence:", dict(by_evidence), " clips:", len(rows))


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawTextHelpFormatter)
    ap.add_argument("jobs", nargs="*", help="job ids (default: all)")
    ap.add_argument("--benchmark", type=Path, nargs="+", help="benchmark output folders (text signals only)")
    ap.add_argument("--json", type=Path, help="also save the rows here")
    args = ap.parse_args()
    rows: list[dict] = []
    if args.benchmark:
        for folder in args.benchmark:
            rows += benchmark_rows(folder)
    else:
        folders = [WORK / j for j in args.jobs] if args.jobs else sorted(p for p in WORK.iterdir() if p.is_dir())
        for job in folders:
            rows += job_rows(job)
    show(rows)
    if args.json:
        args.json.write_text(json.dumps(rows, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
