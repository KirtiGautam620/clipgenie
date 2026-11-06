"""Keeps a video job from overloading the Mac: checks free disk space and memory before a job starts.

Levels:
  ok    - nothing to say
  warn  - a job will work but may be slow or tight on space (shown to the user, job still starts)
  block - a job would likely fail or fill the disk (the job is refused with a clear message)
Only read-only system checks are used (disk usage, swap, memory_pressure). Nothing is changed on the Mac.
"""
import re
import shutil
import subprocess

from . import config

BLOCK_FREE_GB = 5      # below this, refuse new jobs: a video needs room for its source, clips and temp files
WARN_FREE_GB = 15      # below this, warn that long videos may not fit
WARN_SWAP_MB = 4096    # swap in use above this means the Mac is short of memory
WARN_MEM_FREE_PCT = 20 # free memory below this percent means the Mac is short of memory


class Overloaded(RuntimeError):
    """Raised when the Mac cannot safely take a new job right now."""


def _run(cmd: list[str]) -> str:
    try:
        return subprocess.run(cmd, capture_output=True, text=True, timeout=3).stdout
    except Exception:
        return ""  # a missing tool must never break the app; the check is simply skipped


def _swap_mb() -> tuple[float | None, float | None]:
    out = _run(["sysctl", "-n", "vm.swapusage"])            # e.g. "total = 6144.00M  used = 4670.44M ..."
    used = re.search(r"used = ([\d.]+)M", out)
    total = re.search(r"total = ([\d.]+)M", out)
    return (float(used.group(1)) if used else None, float(total.group(1)) if total else None)


def _memory_free_pct() -> int | None:
    m = re.search(r"free percentage: (\d+)%", _run(["memory_pressure"]))
    return int(m.group(1)) if m else None


def status() -> dict:
    free_gb = shutil.disk_usage(config.WORK_DIR).free / 1024 ** 3
    swap_used, swap_total = _swap_mb()
    mem_free = _memory_free_pct()

    level, messages = "ok", []

    def raise_to(new: str) -> None:
        nonlocal level
        order = {"ok": 0, "warn": 1, "block": 2}
        if order[new] > order[level]:
            level = new

    if free_gb < BLOCK_FREE_GB:
        raise_to("block")
        messages.append(f"Only {free_gb:.1f} GB is free on your Mac. CocoGenie needs about "
                        f"{BLOCK_FREE_GB} GB to make a video. Free up some space, then try again.")
    elif free_gb < WARN_FREE_GB:
        raise_to("warn")
        messages.append(f"{free_gb:.0f} GB is free on your Mac. Long videos may not fit, so free up some space.")

    if swap_used is not None and (swap_used > WARN_SWAP_MB or (swap_total and swap_used / swap_total > 0.75)):
        raise_to("warn")
        messages.append("Your Mac is short of memory, so videos may be slow. Closing other apps "
                        "(such as browser tabs) can help.")
    if mem_free is not None and mem_free < WARN_MEM_FREE_PCT:
        raise_to("warn")
        messages.append("Your Mac's memory is almost full. Videos may be slow until some apps are closed.")

    return {
        "level": level,
        "disk_free_gb": round(free_gb, 1),
        "swap_used_mb": round(swap_used) if swap_used is not None else None,
        "swap_total_mb": round(swap_total) if swap_total is not None else None,
        "memory_free_pct": mem_free,
        "messages": messages,
    }


def ensure_room() -> None:
    """Refuse a new job only when the Mac is out of room. Warnings never stop a job."""
    s = status()
    if s["level"] == "block":
        raise Overloaded(s["messages"][0])
