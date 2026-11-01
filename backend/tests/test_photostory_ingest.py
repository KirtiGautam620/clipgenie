"""Tests for photo intake. Every image here is tiny and made in memory: nothing big is decoded."""
from io import BytesIO

import pytest
from PIL import Image

from app.photostory import ingest


def jpeg_bytes(size=(40, 20), exif=None, color=(200, 30, 30)):
    out = BytesIO()
    img = Image.new("RGB", size, color)
    if exif is not None:
        img.save(out, "JPEG", exif=exif)
    else:
        img.save(out, "JPEG")
    return out.getvalue()


def test_a_normal_photo_is_saved_as_a_clean_jpeg(tmp_path):
    dest = tmp_path / "photo.jpg"
    report = ingest.normalize_image(jpeg_bytes(), dest)
    with Image.open(dest) as saved:
        assert saved.format == "JPEG" and saved.size == (40, 20)
    assert report == {"width": 40, "height": 20, "original": (40, 20), "rotated": False, "resized": False,
                      "had_location": False, "had_camera_data": False}


def test_a_photo_taken_sideways_is_turned_the_right_way_up(tmp_path):
    exif = Image.Exif()
    exif[0x0112] = 6                                       # "rotate 90 degrees to view"
    report = ingest.normalize_image(jpeg_bytes((40, 20), exif), tmp_path / "p.jpg")
    assert report["rotated"] is True and (report["width"], report["height"]) == (20, 40)
    with Image.open(tmp_path / "p.jpg") as saved:
        assert saved.size == (20, 40) and saved.getexif().get(0x0112) in (None, 1)


def test_hidden_camera_and_location_data_is_not_kept(tmp_path):
    exif = Image.Exif()
    exif[0x010F] = "Acme Camera Co"                        # camera make
    gps = exif.get_ifd(0x8825)
    gps[1], gps[2], gps[3], gps[4] = "N", (26.0, 55.0, 0.0), "E", (75.0, 49.0, 0.0)
    report = ingest.normalize_image(jpeg_bytes((40, 20), exif), tmp_path / "p.jpg")
    assert report["had_location"] is True and report["had_camera_data"] is True
    with Image.open(tmp_path / "p.jpg") as saved:
        assert len(saved.getexif()) == 0 and "exif" not in saved.info


def test_see_through_areas_become_white_not_black(tmp_path):
    out = BytesIO()
    Image.new("RGBA", (10, 10), (255, 0, 0, 0)).save(out, "PNG")        # fully transparent
    ingest.normalize_image(out.getvalue(), tmp_path / "p.jpg")
    with Image.open(tmp_path / "p.jpg") as saved:
        r, g, b = saved.getpixel((5, 5))
    assert min(r, g, b) > 240


def test_very_long_photos_are_shrunk_to_the_side_limit(tmp_path):
    out = BytesIO()
    Image.new("RGB", (ingest.MAX_SIDE + 904, 100), (10, 10, 10)).save(out, "PNG")      # 5000 x 100: tiny in memory
    report = ingest.normalize_image(out.getvalue(), tmp_path / "p.jpg")
    assert report["resized"] is True and max(report["width"], report["height"]) == ingest.MAX_SIDE
    assert report["original"] == (ingest.MAX_SIDE + 904, 100)


def test_a_photo_with_too_many_pixels_is_refused_before_it_is_decoded(tmp_path, monkeypatch):
    monkeypatch.setattr(ingest, "MAX_PIXELS", 1000)
    data = jpeg_bytes((40, 40))                      # made BEFORE watching for decoding
    decoded = []
    real_load = Image.Image.load
    monkeypatch.setattr(Image.Image, "load", lambda self, *a, **k: decoded.append(1) or real_load(self, *a, **k))
    with pytest.raises(ValueError, match="too large"):
        ingest.normalize_image(data, tmp_path / "p.jpg")
    assert not decoded and not (tmp_path / "p.jpg").exists()


@pytest.mark.parametrize("data", [b"not an image at all", b"", b"\x89PNG\r\n\x1a\n broken"])
def test_files_that_are_not_photos_are_refused(tmp_path, data):
    with pytest.raises(ValueError, match="not a photo"):
        ingest.normalize_image(data, tmp_path / "p.jpg")
    assert not (tmp_path / "p.jpg").exists()


def test_other_picture_formats_are_refused_with_the_same_advice(tmp_path):
    out = BytesIO()
    Image.new("P", (8, 8)).save(out, "GIF")
    with pytest.raises(ValueError, match="JPG, PNG or WebP"):
        ingest.normalize_image(out.getvalue(), tmp_path / "p.jpg")


def test_a_photo_can_be_given_as_a_file_path_too(tmp_path):
    src = tmp_path / "in.jpg"
    src.write_bytes(jpeg_bytes())
    assert ingest.normalize_image(src, tmp_path / "out.jpg")["width"] == 40


def test_webp_is_accepted(tmp_path):
    out = BytesIO()
    Image.new("RGB", (16, 16), (0, 128, 0)).save(out, "WEBP")
    assert ingest.normalize_image(out.getvalue(), tmp_path / "p.jpg")["width"] == 16
