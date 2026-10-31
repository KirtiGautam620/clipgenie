"""Tests for the benchmark's resource guard: it must refuse to start, and stop a running model,
when the Mac is short of memory or disk. No real model is run here."""
import json
import subprocess

import pytest

from tools import asr_benchmark as b

SWAP = "vm.swapusage: total = 7168.00M  used = 6050.56M  free = 1117.44M  (encrypted)"
PRESSURE = """The system has 8589934592 (524288 pages with a page size of 16384).
Pages free: 4220
System-wide memory free percentage: 20%"""

HEALTHY = {"pressure_level": 1, "swap_used_mb": 1000.0, "swap_total_mb": 7168.0,
           "free_percent": 40, "free_disk_gb": 30.0}


# ---------------------------------------------------------------- reading the Mac

def test_parsers_read_real_macos_output():
    assert b.parse_swap(SWAP) == (6050.56, 7168.0)
    assert b.parse_swap("garbage") is None
    assert b.parse_free_percent(PRESSURE) == 20 and b.parse_free_percent("") is None


def test_read_resources_on_this_machine_returns_every_field():
    now = b.read_resources()
    assert set(now) == set(HEALTHY) and now["free_disk_gb"] > 0
    assert now["pressure_level"] in (None, 1, 2, 4)


# ---------------------------------------------------------------- deciding

def test_all_clear_on_a_healthy_mac():
    assert b.assess(HEALTHY, starting=True) is None
    assert b.assess(HEALTHY, starting=False, baseline_swap_mb=900) is None


def test_starting_needs_green_but_a_running_job_only_stops_on_red():
    yellow, red = {**HEALTHY, "pressure_level": b.YELLOW}, {**HEALTHY, "pressure_level": b.RED}
    assert "yellow" in b.assess(yellow, starting=True)
    assert b.assess(yellow, starting=False) is None          # yellow: let the running model finish
    assert "red" in b.assess(red, starting=False) and "red" in b.assess(red, starting=True)


def test_low_free_memory_blocks_starting_and_stops_a_run():
    low = {**HEALTHY, "free_percent": 5}
    assert "free" in b.assess(low, starting=True) and "free" in b.assess(low, starting=False)


def test_swap_nearly_full_blocks_starting_but_is_not_blamed_on_a_run_that_did_not_grow_it():
    full = {**HEALTHY, "swap_used_mb": 6500.0}               # 91% of 7168
    assert "swap" in b.assess(full, starting=True)
    assert b.assess(full, starting=False, baseline_swap_mb=6400) is None


def test_swap_growth_during_a_run_stops_it():
    grown = {**HEALTHY, "swap_used_mb": 4200.0}
    assert "grew" in b.assess(grown, starting=False, baseline_swap_mb=1000)
    assert b.assess(grown, starting=False, baseline_swap_mb=3500) is None   # grew only 700 MB
    assert b.assess(grown, starting=False) is None                          # no baseline to compare


def test_low_disk_blocks_starting_and_stops_a_run():
    tight = {**HEALTHY, "free_disk_gb": 2.5}
    assert "disk" in b.assess(tight, starting=True) and "disk" in b.assess(tight, starting=False)


def test_unreadable_values_never_block():
    assert b.assess({k: None for k in HEALTHY}, starting=True) is None


def test_worst_of_reports_the_extremes():
    seen = b.worst_of([HEALTHY, {**HEALTHY, "pressure_level": 2, "swap_used_mb": 3000.0,
                                 "free_percent": 15, "free_disk_gb": 29.5}, {k: None for k in HEALTHY}])
    assert seen == {"pressure_level_max": 2, "swap_used_mb_max": 3000.0, "free_percent_min": 15,
                    "free_disk_gb_min": 29.5, "samples": 3}


# ---------------------------------------------------------------- watching a child process

def test_a_child_is_stopped_when_memory_runs_short(monkeypatch):
    monkeypatch.setattr(b, "read_resources", lambda *a, **k: HEALTHY)
    monkeypatch.setattr(b, "assess", lambda *a, **k: "memory pressure is red (level 4)")
    with pytest.raises(b.Overloaded, match="red"):
        b._run_guarded(["sleep", "30"], poll=0.1)


def test_the_child_is_not_left_running_after_a_stop(monkeypatch):
    started = []
    real_popen = subprocess.Popen

    def spy(*a, **k):
        started.append(real_popen(*a, **k))
        return started[-1]
    monkeypatch.setattr(b.subprocess, "Popen", spy)
    monkeypatch.setattr(b, "read_resources", lambda *a, **k: HEALTHY)
    monkeypatch.setattr(b, "assess", lambda *a, **k: "stop")
    with pytest.raises(b.Overloaded):
        b._run_guarded(["sleep", "30"], poll=0.1)
    assert started[0].poll() is not None                    # terminated, not abandoned


def test_a_healthy_child_finishes_normally_and_reports_what_it_saw(monkeypatch):
    monkeypatch.setattr(b, "read_resources", lambda *a, **k: HEALTHY)
    done, seen = b._run_guarded(["echo", "hi"], poll=0.1)
    assert done.returncode == 0 and "hi" in done.stdout
    assert seen["pressure_level_max"] == 1 and seen["samples"] >= 2


# ---------------------------------------------------------------- the whole benchmark loop

def _fake_child(monkeypatch, calls, fail_on=None):
    from pathlib import Path

    def fake_run_guarded(cmd, poll=3.0):
        model, name, result = cmd[-4].split("/")[-1], cmd[-3], cmd[-1]
        calls.append((model, name))
        if (model, name) == fail_on:
            raise b.Overloaded("memory pressure is red (level 4)")
        Path(result).write_text(json.dumps(
            {"wall": 5.0, "segments": [{"start": 0, "end": 1, "text": "नमस्ते दोस्तों"}]}))
        return (subprocess.CompletedProcess(cmd, 0, "", "  900000000  maximum resident set size"),
                b.worst_of([HEALTHY]))
    monkeypatch.setattr(b, "_run_guarded", fake_run_guarded)
    monkeypatch.setattr(b, "_slice_audio", lambda wav, start, dur, out: out.write_bytes(b""))


def test_only_the_requested_pairs_run_one_after_another(monkeypatch, tmp_path):
    calls = []
    _fake_child(monkeypatch, calls)
    monkeypatch.setattr(b, "check_resources", lambda *a, **k: None)
    rows = b.benchmark(tmp_path / "a.wav", 100, 120,
                       [("mlx-community/whisper-small-mlx", "default"),
                        ("mlx-community/whisper-large-v3-turbo-q4", "tuned")], "hi", None, tmp_path / "out")
    assert calls == [("whisper-small-mlx", "default"), ("whisper-large-v3-turbo-q4", "tuned")]
    assert len(rows) == 2 and rows[0]["resources"]["pressure_level_max"] == 1
    assert (tmp_path / "out" / "results.json").exists()
    assert (tmp_path / "out" / "whisper-small-mlx__default.txt").exists()


def test_it_refuses_to_start_when_the_mac_is_short_of_resources(monkeypatch, tmp_path):
    calls = []
    _fake_child(monkeypatch, calls)
    monkeypatch.setattr(b, "check_resources", lambda *a, **k: "swap is 90% full (limit 85%)")
    with pytest.raises(b.Overloaded, match="not starting"):
        b.benchmark(tmp_path / "a.wav", 0, 60, [("m/x", "default")], "hi", None, tmp_path / "out")
    assert calls == []                                      # nothing was ever launched


def test_a_stop_midway_keeps_the_finished_results(monkeypatch, tmp_path):
    calls = []
    _fake_child(monkeypatch, calls, fail_on=("whisper-large-v3-turbo-q4", "tuned"))
    monkeypatch.setattr(b, "check_resources", lambda *a, **k: None)
    with pytest.raises(b.Overloaded, match="stopped"):
        b.benchmark(tmp_path / "a.wav", 0, 60, [("m/whisper-small-mlx", "default"),
                                                ("m/whisper-large-v3-turbo-q4", "tuned")],
                    "hi", None, tmp_path / "out")
    saved = json.loads((tmp_path / "out" / "results.json").read_text())
    assert [r["model"] for r in saved] == ["whisper-small-mlx"]          # the first run survived


def test_the_command_line_takes_exact_pairs_and_rejects_typos(monkeypatch):
    monkeypatch.setattr(b.sys, "argv", ["x", "a.wav", "--out", "o", "--run", "m/x:nope"])
    with pytest.raises(SystemExit):
        b.main()
