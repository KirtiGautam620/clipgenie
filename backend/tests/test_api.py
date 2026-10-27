import json

import pytest
from fastapi.testclient import TestClient

from app import jobs, rights, ytdl
from app import main
from tests.conftest import make_clips_job, music_info

MP4 = ("clip.mp4", b"not really a video", "video/mp4")


@pytest.fixture
def client(folders, monkeypatch):
    started = []
    monkeypatch.setattr(main, "run_pipeline", lambda *a, **k: started.append(a))
    with TestClient(main.app) as c:
        c.started = started
        yield c


# ------------------------------------------------------------------ starting jobs

def test_upload_needs_a_rights_declaration(client):
    assert client.post("/api/upload", files={"file": MP4}).status_code == 422
    r = client.post("/api/upload", files={"file": MP4}, data={"rights": "whatever"})
    assert r.status_code == 400
    assert not client.started


def test_upload_accepts_declared_rights_and_records_them(client):
    r = client.post("/api/upload", files={"file": MP4}, data={"rights": "permission"})
    assert r.status_code == 200 and client.started
    assert rights.load_source(r.json()["job_id"])["rights"] == "permission"


def test_upload_rejects_non_mp4_and_bad_settings(client):
    bad = ("a.exe", b"x", "application/octet-stream")
    assert client.post("/api/upload", files={"file": bad}, data={"rights": "own"}).status_code == 400
    assert client.post("/api/upload", files={"file": MP4},
                       data={"rights": "own", "min_len": 50, "max_len": 10}).status_code == 400


def test_url_import_refuses_unsure_rights_and_non_youtube_links(client):
    url = "https://www.youtube.com/watch?v=abc"
    assert client.post("/api/import-url", data={"url": url, "rights": "unsure"}).status_code == 400
    for bad in ["http://www.youtube.com/watch?v=a", "https://evil.com/youtube.com",
                "https://youtube.com.evil.com/x", "file:///etc/passwd", "javascript:alert(1)"]:
        r = client.post("/api/import-url", data={"url": bad, "rights": "own"})
        assert r.status_code == 400, bad
    assert not client.started
    ok = client.post("/api/import-url", data={"url": url, "rights": "own"})
    assert ok.status_code == 200 and client.started


def test_check_url_accepts_all_youtube_forms():
    for good in ["https://youtu.be/abc", "https://m.youtube.com/watch?v=a", "https://youtube.com/shorts/a"]:
        assert ytdl.check_url(good) == good


# ------------------------------------------------------------------ safety

def test_job_ids_cannot_reach_other_folders(client):
    for bad in ["..", "abc", "ABCDEF0123", "zzzzzzzzzz", "%2e%2e"]:
        assert client.get(f"/api/jobs/{bad}").status_code == 404, bad
        assert client.get(f"/api/jobs/{bad}/clips").status_code == 404, bad


def test_interrupted_jobs_are_marked_on_startup(folders, monkeypatch):
    work, _ = folders
    stuck = work / "0123456789"
    stuck.mkdir()
    (stuck / "status.json").write_text(json.dumps({"status": "transcribing"}))
    done = work / "9876543210"
    done.mkdir()
    (done / "status.json").write_text(json.dumps({"status": "done"}))
    with TestClient(main.app):
        pass
    assert jobs.get_status("0123456789")["status"] == "error"
    assert jobs.get_status("9876543210")["status"] == "done"


def test_pipeline_reports_a_failed_import(folders, monkeypatch):
    from app import pipeline
    job_id, _ = jobs.create_job()

    def refuse(*a, **k):
        raise ytdl.ImportError_("This video is private.")
    monkeypatch.setattr(pipeline.ytdl, "download", refuse)
    pipeline.run_pipeline(job_id, None, {"rights": "own"}, "https://youtu.be/x")
    status = jobs.get_status(job_id)
    assert status["status"] == "error" and "private" in status["error"]


# ------------------------------------------------------------------ the copyright gate

def test_download_is_blocked_until_the_checklist_is_confirmed(client, folders):
    work, _ = folders
    job, _, _ = make_clips_job(work, music_info=music_info())
    assert client.get(f"/api/jobs/{job}/clips/1/download").status_code == 403
    assert client.get(f"/api/jobs/{job}/clips/1.mp4").status_code == 200       # preview is fine

    clip = client.get(f"/api/jobs/{job}/clips").json()["clips"][0]
    ids = [i["id"] for i in clip["checklist"]]
    assert client.post(f"/api/jobs/{job}/clips/1/checklist", json={"items": ids[:-1]}).status_code == 400
    assert client.get(f"/api/jobs/{job}/clips/1/download").status_code == 403

    assert client.post(f"/api/jobs/{job}/clips/1/checklist", json={"items": ids}).status_code == 200
    r = client.get(f"/api/jobs/{job}/clips/1/download")
    assert r.status_code == 200 and r.content == b"fake video"
    assert "attachment" in r.headers["content-disposition"]


def test_changing_the_music_requires_confirming_again(client, folders, monkeypatch):
    work, folder = folders[0], None
    job, folder, _ = make_clips_job(work, music_info=music_info())
    clip = client.get(f"/api/jobs/{job}/clips").json()["clips"][0]
    client.post(f"/api/jobs/{job}/clips/1/checklist", json={"items": [i["id"] for i in clip["checklist"]]})
    assert client.get(f"/api/jobs/{job}/clips/1/download").status_code == 200

    def fake_set(job_id, clip_id, track_id, volume):       # stands in for the ffmpeg mix
        data = json.loads((folder / "clips.json").read_text())
        data["clips"][0]["version"] += 1
        data["clips"][0]["music"] = None
        (folder / "clips.json").write_text(json.dumps(data))
        return data["clips"][0]
    monkeypatch.setattr(main, "set_clip_music", fake_set)
    r = client.post(f"/api/jobs/{job}/clips/1/music", json={"track_id": None, "volume": 0.5})
    assert r.status_code == 200 and r.json()["confirmed"] is False
    assert client.get(f"/api/jobs/{job}/clips/1/download").status_code == 403


def test_unsure_source_shows_a_warning_and_a_different_checklist(client, folders):
    work, _ = folders
    job, _, _ = make_clips_job(work, rights="unsure")
    clip = client.get(f"/api/jobs/{job}/clips").json()["clips"][0]
    assert clip["warnings"] and clip["checklist"][0]["id"] == "source_unsure"


def test_clip_listing_includes_the_disclaimer_and_report_downloads(client, folders):
    work, _ = folders
    job, _, _ = make_clips_job(work)
    data = client.get(f"/api/jobs/{job}/clips").json()
    assert "NOT automatically copyright-free" in data["disclaimer"]
    r = client.get(f"/api/jobs/{job}/clips/1/report")
    assert r.status_code == 200 and "attachment" in r.headers["content-disposition"]
    assert client.get(f"/api/jobs/{job}/clips/7/report").status_code == 404
