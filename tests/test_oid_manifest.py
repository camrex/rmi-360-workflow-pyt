"""Unit tests for utils/shared/oid_manifest.py — EXIF to oriented-imagery-table CSV, and the
S3 header fetch (fake client; no AWS)."""

import csv
import datetime as dt
import io
import shutil
import subprocess
import sys
from unittest.mock import MagicMock

for _esri_mod in ("arcpy", "arcgis", "arcgis.gis"):
    sys.modules.setdefault(_esri_mod, MagicMock())

import pytest

from utils.shared import oid_manifest as om

FINAL = "RMI26150_UP_G0.109_20260625T155157Z_RL0002_FR000587.jpg"


def exif_rec(name=FINAL, **over):
    e = {"SourceFile": f"I:/x/{name}", "GPS:GPSLatitude": 41.8843625909875, "GPS:GPSLatitudeRef": "N",
         "GPS:GPSLongitude": 87.6399867219722, "GPS:GPSLongitudeRef": "W", "GPS:GPSAltitude": 154.8473934,
         "GPS:GPSAltitudeRef": 0, "GPS:GPSImgDirection": 181.595186,
         "ExifIFD:DateTimeOriginal": "2026:06:25 15:51:57"}
    e.update(over)
    return e


def test_parse_reel_frame():
    assert om.parse_reel_frame(FINAL) == ("0002", 587)
    assert om.parse_reel_frame("pano_reel_0023_20260619-160716_26-150_000037.jpg") == ("0023", 37)
    assert om.parse_reel_frame("random.jpg") is None


def test_record_from_exif_signs_and_fields():
    rec, why = om.record_from_exif(exif_rec())
    assert why == "" and rec.lon == pytest.approx(-87.6399867219722) and rec.lat > 0
    assert rec.z == pytest.approx(154.8473934) and rec.heading == pytest.approx(181.595186)
    assert rec.acquired == dt.datetime(2026, 6, 25, 15, 51, 57) and (rec.reel, rec.frame) == ("0002", 587)
    rec, _ = om.record_from_exif(exif_rec(**{"GPS:GPSAltitudeRef": 1, "GPS:GPSLatitudeRef": "S"}))
    assert rec.z < 0 and rec.lat < 0


@pytest.mark.parametrize("drop,reason", [("GPS:GPSLatitude", "no GPS"), ("ExifIFD:DateTimeOriginal", "no DateTime"),
                                         ("GPS:GPSImgDirection", "no GPSImgDirection")])
def test_record_from_exif_reports_missing(drop, reason):
    e = exif_rec()
    del e[drop]
    rec, why = om.record_from_exif(e)
    assert rec is None and why.startswith(reason)


def test_manifest_rows_round_like_esri_and_apply_corrections():
    recs, skipped = om.records_from_exif([
        exif_rec(), exif_rec(name=FINAL.replace("FR000587", "FR000588")),
        exif_rec(name=FINAL.replace("FR000587", "FR000589")), exif_rec(name="nope.jpg")])
    assert skipped == {"nope.jpg": "name has no reel/frame"}
    frames = [r.to_frame() for r in recs]
    frames[1].heading, frames[1].heading_source = 1.595186, "flip"
    frames[2].excluded = True
    rows = om.manifest_rows(recs, frames, image_path=lambda n: f"https://bucket/RMI26150/{n}")
    assert [r["Name"][-10:] for r in rows] == ["000587.jpg", "000588.jpg"]     # excluded frame left out
    r0, r1 = rows
    assert r0["Z"] == 154.847 and r0["CameraHeading"] == 181.595 and r0["HeadingSource"] == "exif"
    assert r1["CameraHeading"] == 1.595 and r1["HeadingSource"] == "flip"
    assert r0["ImagePath"] == f"https://bucket/RMI26150/{FINAL}" and r0["SRS"] == "4326"
    assert r0["AcquisitionDate"] == "2026-06-25 15:51:57"


def test_duplicate_names_keep_the_first_and_report_the_rest():
    recs, skipped = om.records_from_exif([exif_rec(), {**exif_rec(), "SourceFile": f"I:/y/{FINAL}"}])
    assert len(recs) == 1 and recs[0].source == f"I:/x/{FINAL}"
    assert skipped == {f"I:/y/{FINAL}": f"duplicate name (also I:/x/{FINAL})"}


def test_write_manifest_columns(tmp_path):
    recs, _ = om.records_from_exif([exif_rec()])
    p = om.write_manifest(om.manifest_rows(recs, [], image_path=str), tmp_path / "m" / "manifest.csv")
    header = next(csv.reader(open(p, encoding="utf-8")))
    assert tuple(header) == om.MANIFEST_COLUMNS


class FakeS3:
    """get_object honouring Range; objects are bytes. Counts calls per key."""

    def __init__(self, objects, fail=()):
        self.objects, self.fail, self.calls = objects, set(fail), {}

    def get_object(self, Bucket, Key, Range):
        self.calls[Key] = self.calls.get(Key, 0) + 1
        if Key in self.fail:
            raise RuntimeError("AccessDenied")
        end = int(Range.split("-")[1])
        return {"Body": io.BytesIO(self.objects[Key][:end + 1])}

    def get_paginator(self, name):
        objs = self.objects

        class P:
            def paginate(self, Bucket, Prefix):
                yield {"Contents": [{"Key": k} for k in objs if k.startswith(Prefix)] + [{"Key": Prefix + "x.txt"}]}
        return P()


def jpeg_with_header(meta_len):
    return b"\xff\xd8" + b"M" * meta_len + om.JPEG_SOS + b"I" * 200_000


def test_fetch_headers_small_widen_error_and_resume(tmp_path):
    objs = {"RMI1/a.jpg": jpeg_with_header(6_000), "RMI1/b.jpg": jpeg_with_header(100_000),
            "RMI1/c.jpg": jpeg_with_header(10)}
    s3 = FakeS3(objs, fail={"RMI1/c.jpg"})
    paths, errors = om.fetch_headers(s3, "bucket", sorted(objs), tmp_path)
    assert [p.name for p in paths] == ["a.jpg", "b.jpg"]
    assert errors == {"RMI1/c.jpg": "RuntimeError: AccessDenied"}
    assert len((tmp_path / "RMI1" / "a.jpg").read_bytes()) == om.HEADER_BYTES     # one 32 KB read
    assert s3.calls["RMI1/b.jpg"] == 2 and om.JPEG_SOS in (tmp_path / "RMI1" / "b.jpg").read_bytes()  # widened
    om.fetch_headers(s3, "bucket", ["RMI1/a.jpg"], tmp_path)                    # resume: no new call
    assert s3.calls["RMI1/a.jpg"] == 1


def test_same_file_name_under_two_keys_gets_two_cache_files(tmp_path):
    objs = {"RMI1/a/x.jpg": jpeg_with_header(10) + b"A", "RMI1/b/x.jpg": jpeg_with_header(10) + b"B"}
    paths, errors = om.fetch_headers(FakeS3(objs), "bucket", sorted(objs), tmp_path)
    assert errors == {} and len(set(paths)) == 2
    assert paths == [tmp_path / "RMI1" / "a" / "x.jpg", tmp_path / "RMI1" / "b" / "x.jpg"]
    assert om.header_cache_path(tmp_path, "RMI1/../../evil.jpg") == tmp_path / "RMI1" / "evil.jpg"


def test_list_image_keys_filters_jpegs():
    s3 = FakeS3({"RMI1/a.jpg": b"", "RMI1/b.JPEG": b"", "RMI2/c.jpg": b""})
    assert om.list_image_keys(s3, "bucket", "RMI1") == ["RMI1/a.jpg", "RMI1/b.JPEG"]


@pytest.mark.skipif(shutil.which("exiftool") is None, reason="exiftool not installed")
def test_read_exif_end_to_end(tmp_path):
    pil = pytest.importorskip("PIL.Image")
    img = tmp_path / FINAL
    pil.new("RGB", (64, 32)).save(img, "JPEG")
    subprocess.run(["exiftool", "-overwrite_original", "-GPSLatitude=41.88", "-GPSLatitudeRef=N",
                    "-GPSLongitude=87.64", "-GPSLongitudeRef=W", "-GPSAltitude=154.8474", "-GPSAltitudeRef=0",
                    "-GPSImgDirection=181.595186", "-DateTimeOriginal=2026:06:25 15:51:57", str(img)],
                   check=True, capture_output=True)
    recs, skipped = om.records_from_exif(om.read_exif([img]))
    assert skipped == {} and len(recs) == 1
    r = recs[0]
    assert (r.lon, r.lat) == (pytest.approx(-87.64), pytest.approx(41.88))
    assert r.z == pytest.approx(154.8474, abs=1e-3) and r.heading == pytest.approx(181.595186, abs=1e-4)
