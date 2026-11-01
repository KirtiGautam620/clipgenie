"""Tests for storing storyboards and for the Storyboard API. Photos are tiny and made in memory."""
import json
import zipfile
from io import BytesIO

import pytest
from fastapi.testclient import TestClient
from PIL import Image

from app import main
from app.storyboard import model, store

EXAMPLE = "Create a cinematic UGC video of this product with different camera angles, close-ups, and smooth transitions."


@pytest.fixture
def client(folders, tmp_path, monkeypatch):
    monkeypatch.setattr(store, "ROOT", tmp_path / "storyboards")
    with TestClient(main.app) as c:
        yield c


def photo_bytes(size=(600, 400), fmt="JPEG"):
    img = Image.new("RGB", size)
    for x in range(size[0]):
        for y in range(0, size[1], 20):
            img.paste((int(255 * x / size[0]), 90, int(255 * (1 - x / size[0]))), (x, y, x + 1, y + 20))
    out = BytesIO()
    img.save(out, fmt)
    return out.getvalue()


def make(client, **fields):
    data = {"prompt": EXAMPLE, "product": "a steel water bottle", "rights": "own", "people": "none", **fields}
    return client.post("/api/storyboards", files={"photo": ("bottle.jpg", photo_bytes(), "image/jpeg")}, data=data)


# ================================================================== creating

def test_a_photo_and_a_prompt_make_a_saved_storyboard(client, tmp_path):
    r = make(client)
    assert r.status_code == 200
    sb = r.json()
    assert len(sb["scenes"]) == 6 and sb["style"] == "cinematic" and sb["aspect"] == "9:16"
    assert sb["photo"] == {"file": "photo.jpg", "width": 600, "height": 400}
    assert set(sb["geometry"]) == {s["id"] for s in sb["scenes"]} and sb["blockers"] == []
    assert sb["plan"]["understood"]["shots"] == ["In hand", "Close-up"] and sb["plan"]["notes"]
    where = tmp_path / "storyboards" / sb["id"]
    assert (where / "photo.jpg").exists() and (where / "project.json").exists()
    assert client.get("/api/storyboards").json()["storyboards"][0]["id"] == sb["id"]


def test_the_saved_photo_is_a_clean_jpeg(client, tmp_path):
    sb = make(client).json()
    with Image.open(tmp_path / "storyboards" / sb["id"] / "photo.jpg") as saved:
        assert saved.format == "JPEG" and len(saved.getexif()) == 0
    served = client.get(f"/api/storyboards/{sb['id']}/photo.jpg")
    assert served.status_code == 200 and served.headers["content-type"] == "image/jpeg"


def test_rights_start_unconfirmed_and_that_blocks_export(client):
    sb = make(client, rights="unsure").json()
    assert sb["rights"] == "unsure" and any("right to use" in b for b in sb["blockers"])


def test_options_for_the_form_come_from_the_server(client):
    o = client.get("/api/storyboard-options").json()
    assert [s["id"] for s in o["styles"]] == ["none", "cinematic", "ugc", "luxury", "minimal"]
    assert len(o["shots"]) >= 12 and o["aspects"] == ["9:16", "16:9"] and o["limits"]["scenes"] == [2, 8]
    assert {r["id"] for r in o["rights"]} == {"own", "permission", "licensed", "public_domain", "unsure"}


@pytest.mark.parametrize("fields,status", [
    ({"style": "neon"}, 400), ({"aspect": "4:3"}, 400), ({"count": "many"}, 400), ({"rights": "stolen"}, 400),
    ({"people": "maybe"}, 400), ({"prompt": "x" * 1001}, 400)])
def test_bad_form_values_are_refused_and_leave_nothing_behind(client, tmp_path, fields, status):
    assert make(client, **fields).status_code == status
    root = tmp_path / "storyboards"
    assert not root.exists() or not list(root.iterdir())


def test_a_file_that_is_not_a_photo_is_refused(client, tmp_path):
    r = client.post("/api/storyboards", files={"photo": ("x.jpg", b"not a photo", "image/jpeg")}, data={"prompt": "x"})
    assert r.status_code == 400 and "not a photo" in r.json()["detail"]
    assert not list((tmp_path / "storyboards").iterdir())


def test_an_oversized_upload_is_refused(client, monkeypatch):
    monkeypatch.setattr(store, "MAX_UPLOAD", 1000)
    r = client.post("/api/storyboards", files={"photo": ("x.jpg", photo_bytes(), "image/jpeg")}, data={"prompt": "x"})
    assert r.status_code == 413


def test_the_scene_count_and_style_from_the_form_win_over_the_prompt(client):
    sb = make(client, count="3", style="luxury").json()
    assert len(sb["scenes"]) == 3 and sb["style"] == "luxury"


def test_widescreen_storyboards_use_the_wide_shape(client):
    sb = make(client, aspect="16:9").json()
    assert sb["aspect"] == "16:9" and "horizontal 16:9" in sb["scenes"][0]["prompt"]


# ================================================================== editing

def test_edits_are_saved_with_fresh_geometry(client):
    sb = make(client).json()
    sb["scenes"][0].update(title="Hero bottle", duration=6, zoom=2.0, focus=[0.2, 0.7])
    sb["scenes"] = sb["scenes"][::-1]                                   # reorder
    r = client.put(f"/api/storyboards/{sb['id']}", json=sb)
    assert r.status_code == 200
    saved = r.json()
    assert saved["scenes"][-1]["title"] == "Hero bottle" and saved["scenes"][-1]["zoom"] == 2.0
    assert saved["geometry"][saved["scenes"][-1]["id"]]["start"] != saved["geometry"][saved["scenes"][0]["id"]]["start"]
    assert client.get(f"/api/storyboards/{sb['id']}").json()["scenes"][-1]["title"] == "Hero bottle"


def test_scenes_can_be_added_removed_and_duplicated(client):
    sb = make(client).json()
    sb["scenes"].append({**sb["scenes"][0], "id": "extra", "title": "My own shot", "shot": "custom"})
    del sb["scenes"][1]
    saved = client.put(f"/api/storyboards/{sb['id']}", json=sb).json()
    assert len(saved["scenes"]) == 6 and saved["scenes"][-1]["shot"] == "custom"


def test_a_bad_edit_is_refused_and_changes_nothing(client, tmp_path):
    sb = make(client).json()
    file = tmp_path / "storyboards" / sb["id"] / "project.json"
    before = file.read_text()
    sb["scenes"][0]["zoom"] = 9
    r = client.put(f"/api/storyboards/{sb['id']}", json=sb)
    assert r.status_code == 400 and "Scene 1" in r.json()["detail"] and file.read_text() == before
    sb["scenes"] = []
    assert client.put(f"/api/storyboards/{sb['id']}", json=sb).status_code == 400


def test_the_page_cannot_change_the_photo_facts_or_the_planners_notes(client):
    sb = make(client).json()
    notes = sb["plan"]["notes"]
    sb["photo"], sb["plan"], sb["id"] = {"file": "photo.jpg", "width": 1, "height": 1}, {"notes": ["forged"]}, "ffffffffffff"
    saved = client.put(f"/api/storyboards/{make(client).json()['id']}", json=sb).json()
    assert saved["photo"]["width"] == 600 and saved["plan"]["notes"] == notes and saved["id"] != "ffffffffffff"


def test_a_new_prompt_makes_a_new_plan_but_keeps_the_photo_title_and_rights(client):
    sb = make(client, title="My bottle", rights="permission").json()
    r = client.post(f"/api/storyboards/{sb['id']}/plan", json={"prompt": "a macro and an orbit", "product": "x",
                                                               "style": "luxury", "count": 3})
    assert r.status_code == 200
    new = r.json()
    assert [s["shot"] for s in new["scenes"]][:2] == ["macro", "orbit"] and len(new["scenes"]) == 3
    assert new["title"] == "My bottle" and new["rights"] == "permission" and new["photo"] == sb["photo"]
    assert client.post(f"/api/storyboards/{sb['id']}/plan", json={"prompt": "x", "style": "neon"}).status_code == 400


def test_a_scene_prompt_can_be_rebuilt_from_its_fields(client):
    sb = make(client, product="a steel water bottle").json()
    r = client.post(f"/api/storyboards/{sb['id']}/compose-prompt", json={
        "camera": "a slow orbit", "detail": "all sides of the bottle", "duration": 4})
    text = r.json()["prompt"]
    assert r.status_code == 200 and "a steel water bottle" in text and "Camera: a slow orbit." in text
    bad = client.post(f"/api/storyboards/{sb['id']}/compose-prompt", json={"camera": "x", "detail": "y", "duration": 99})
    assert bad.status_code == 400


# ================================================================== preview frames

def frame_url(sb, **q):
    base = {"zoom": 1, "motion": "hold", "intensity": 0.5, "fx": 0.5, "fy": 0.5, "which": "start", "w": 160}
    base.update(q)
    return f"/api/storyboards/{sb['id']}/frame.jpg?" + "&".join(f"{k}={v}" for k, v in base.items())


def test_frames_are_real_crops_of_the_photo_at_the_right_size(client):
    sb = make(client).json()
    r = client.get(frame_url(sb))
    assert r.status_code == 200 and r.headers["content-type"] == "image/jpeg" and r.headers["cache-control"] == "no-store"
    assert Image.open(BytesIO(r.content)).size == (90, 160)
    wide = make(client, aspect="16:9").json()
    assert Image.open(BytesIO(client.get(frame_url(wide)).content)).size == (160, 90)


def test_the_start_and_end_frames_of_a_move_differ_and_follow_the_focus(client):
    sb = make(client).json()
    move = dict(motion="pan_right", zoom=2, intensity=1)
    assert client.get(frame_url(sb, which="start", **move)).content != client.get(frame_url(sb, which="end", **move)).content
    left, right = client.get(frame_url(sb, fx=0.0, zoom=2)).content, client.get(frame_url(sb, fx=1.0, zoom=2)).content
    a, b = Image.open(BytesIO(left)), Image.open(BytesIO(right))
    assert a.getpixel((45, 80))[0] < b.getpixel((45, 80))[0]


@pytest.mark.parametrize("q", [{"zoom": 9}, {"zoom": 0.2}, {"fx": 2}, {"motion": "spin"}, {"which": "middle"},
                               {"w": 10}, {"w": 5000}, {"w": "big"}, {"intensity": 3}, {"zoom": "x"}])
def test_bad_frame_requests_are_refused(client, q):
    assert client.get(frame_url(make(client).json(), **q)).status_code == 400


def test_geometry_for_live_editing(client):
    sb = make(client).json()
    g = client.get(f"/api/storyboards/{sb['id']}/geometry?zoom=2&motion=push_in&intensity=1&fx=0.3&fy=0.5").json()
    assert set(g) == {"start", "end", "sharpness"} and g["end"][2] - g["end"][0] < g["start"][2] - g["start"][0]
    assert g["sharpness"]["label"] in ("sharp", "ok", "soft")


# ================================================================== the download

def read_zip(content):
    return zipfile.ZipFile(BytesIO(content))


def test_the_package_has_the_plan_the_prompts_the_photo_and_real_reference_frames(client):
    sb = make(client).json()
    r = client.get(f"/api/storyboards/{sb['id']}/package.zip")
    assert r.status_code == 200 and r.headers["content-type"] == "application/zip"
    z = read_zip(r.content)
    names = set(z.namelist())
    assert {"photo.jpg", "storyboard.md", "prompts.txt", "storyboard.json"} <= names
    assert sum(n.startswith("reference/") for n in names) == 12                          # 6 scenes x start and end
    md = z.read("storyboard.md").decode()
    assert "not an AI-generated video" in md and "Scene 6" in md and "photo detail:" in md
    for n in ("reference/scene_01_start.jpg", "reference/scene_06_end.jpg"):
        assert Image.open(BytesIO(z.read(n))).size == (720, 1280)
    data = json.loads(z.read("storyboard.json"))
    assert len(data["scenes"]) == 6 and set(data["geometry"]) == {s["id"] for s in data["scenes"]}
    assert all(s["prompt"] in z.read("prompts.txt").decode() for s in data["scenes"])


def test_the_package_follows_the_edits_that_were_saved(client):
    sb = make(client).json()
    sb["scenes"][0]["prompt"] = "MY OWN WORDS FOR SCENE ONE"
    client.put(f"/api/storyboards/{sb['id']}", json=sb)
    z = read_zip(client.get(f"/api/storyboards/{sb['id']}/package.zip").content)
    assert "MY OWN WORDS FOR SCENE ONE" in z.read("prompts.txt").decode()


def test_prompts_text_is_plain_text(client):
    sb = make(client).json()
    r = client.get(f"/api/storyboards/{sb['id']}/prompts.txt")
    assert r.status_code == 200 and r.headers["content-type"].startswith("text/plain") and r.text.count("=== Scene") == 6


@pytest.mark.parametrize("fields,words", [({"rights": "unsure"}, "right to use"), ({"people": "no_consent"}, "agreed")])
def test_nothing_is_handed_out_until_rights_and_consent_are_settled(client, fields, words):
    sb = make(client, **fields).json()
    for path in ("package.zip", "prompts.txt"):
        r = client.get(f"/api/storyboards/{sb['id']}/{path}")
        assert r.status_code == 409 and words in r.json()["detail"]
    sb.update(rights="own", people="none")
    client.put(f"/api/storyboards/{sb['id']}", json=sb)
    assert client.get(f"/api/storyboards/{sb['id']}/package.zip").status_code == 200


# ================================================================== deleting, bad ids, and the Shorts side

def test_a_storyboard_can_be_deleted_with_its_photo(client, tmp_path):
    sb = make(client).json()
    assert client.delete(f"/api/storyboards/{sb['id']}").json() == {"deleted": sb["id"]}
    assert not (tmp_path / "storyboards" / sb["id"]).exists()
    assert client.get(f"/api/storyboards/{sb['id']}").status_code == 404
    assert client.delete(f"/api/storyboards/{sb['id']}").status_code == 404


@pytest.mark.parametrize("sid", ["../x", "..%2F..%2Fetc", "ABCDEF012345", "short", "0123456789abc", "%2e%2e"])
def test_ids_that_could_reach_other_folders_are_refused(client, sid):
    for method, path in (("get", ""), ("delete", ""), ("get", "/photo.jpg"), ("get", "/package.zip")):
        assert getattr(client, method)(f"/api/storyboards/{sid}{path}").status_code in (404, 405)


def test_an_unknown_storyboard_is_a_404_everywhere(client):
    sid = "0123456789ab"
    assert client.get(f"/api/storyboards/{sid}").status_code == 404
    assert client.get(f"/api/storyboards/{sid}/frame.jpg").status_code == 404
    assert client.put(f"/api/storyboards/{sid}", json={}).status_code == 404
    assert client.post(f"/api/storyboards/{sid}/plan", json={}).status_code == 404


def test_a_damaged_storyboard_does_not_hide_the_others(client, tmp_path):
    good = make(client).json()
    broken = tmp_path / "storyboards" / "aaaaaaaaaaaa"
    broken.mkdir()
    (broken / "project.json").write_text("{not json")
    assert [s["id"] for s in client.get("/api/storyboards").json()["storyboards"]] == [good["id"]]


def test_the_shorts_routes_still_work_next_to_the_new_ones(client):
    assert client.get("/api/health").status_code == 200
    assert client.get("/api/music").status_code == 200
    assert client.get("/api/caption-presets").status_code == 200
    assert client.get("/api/jobs/0123456789").status_code == 404
