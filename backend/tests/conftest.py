import json
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from app import jobs, music  # noqa: E402


@pytest.fixture
def folders(tmp_path, monkeypatch):
    """Point the app at empty temporary folders so tests never touch real data."""
    work, tracks = tmp_path / "work", tmp_path / "music"
    work.mkdir()
    tracks.mkdir()
    monkeypatch.setattr(jobs, "WORK_DIR", work)
    monkeypatch.setattr(music, "MUSIC_DIR", tracks)
    monkeypatch.setattr(music, "LIBRARY_FILE", tracks / "library.json")
    return work, tracks


def make_clips_job(work: Path, job_id="abcdef0123", music_info=None, rights="own", version=0):
    """A finished job folder with one clip, without running any AI."""
    folder = work / job_id
    folder.mkdir()
    (folder / "status.json").write_text(json.dumps({"status": "done"}))
    (folder / "provenance.json").write_text(json.dumps(
        {"rights": rights, "url": None, "title": "my.mp4", "uploader": ""}))
    (folder / "clip_1.mp4").write_bytes(b"fake video")
    clip = {"id": 1, "start": 1.0, "end": 31.0, "duration": 30.0, "title": "T",
            "music": music_info, "version": version}
    (folder / "clips.json").write_text(json.dumps({"status": "done", "note": "ok", "clips": [clip]}))
    return job_id, folder, clip


def music_info(license="CC0 / public domain", attribution="", warning=None):
    return {"track_id": "t1", "title": "Song", "volume": 0.6, "license": license,
            "attribution": attribution, "warning": warning}
