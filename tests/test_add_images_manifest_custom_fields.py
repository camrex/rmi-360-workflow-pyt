"""Unit tests for manifest-sourced custom field population in add_images_to_oid_fc.

arcpy is available in the ArcGIS Pro test environment; arcpy.ListFields and
arcpy.da.UpdateCursor are monkeypatched so no real geodatabase is required.
"""

import csv
import types

import arcpy
import pytest

from utils import add_images_to_oid_fc as aio


class DummyCfg:
    def __init__(self, custom_fields):
        self._custom_fields = custom_fields
        self.paths = types.SimpleNamespace(logs=None)

    def get(self, key, default=None):
        if key == "oid_schema_template.custom_fields":
            return self._custom_fields
        return default


class DummyUpdateCursor:
    def __init__(self, rows):
        self.rows = [list(r) for r in rows]
        self.updated = []

    def __enter__(self):
        return self

    def __exit__(self, *a):
        return False

    def __iter__(self):
        for r in self.rows:
            yield r

    def updateRow(self, row):
        self.updated.append(list(row))


def _write_manifest(tmp_path):
    p = tmp_path / "RMI_manifest.csv"
    with open(p, "w", newline="", encoding="utf-8") as f:
        w = csv.writer(f)
        w.writerow(["Name", "Path", "track", "mp_pre"])
        w.writerow(["img_a.jpg", "C:/x/img_a.jpg", "2", "SUBA"])
        w.writerow(["img_b.jpg", "C:/x/img_b.jpg", "", "SUBA"])  # empty track
    return str(p)


def _fields(*names):
    return [types.SimpleNamespace(name=n) for n in names]


# -----------------------------------------------------------------------------
def test_load_manifest_attr_map(tmp_path):
    amap = aio.load_manifest_attr_map(_write_manifest(tmp_path), ["track"])
    assert amap["img_a.jpg"] == {"track": "2"}
    assert amap["img_b.jpg"] == {"track": ""}
    # only requested columns are captured
    assert set(amap["img_a.jpg"].keys()) == {"track"}


def test_manifest_custom_field_defs_filters_to_manifest_fields():
    cfg = DummyCfg({
        "custom1": {"name": "RR", "expression": "x"},                    # expression -> ignored
        "custom2": {"name": "Track", "type": "TEXT", "manifest_field": "track", "default": "_main"},
    })
    assert aio._manifest_custom_field_defs(cfg) == [("Track", "track", "_main", "TEXT")]


def test_manifest_custom_field_defs_empty_when_none():
    cfg = DummyCfg({"custom1": {"name": "RR", "expression": "x"}})
    assert aio._manifest_custom_field_defs(cfg) == []


def test_populate_joins_track_and_applies_default(tmp_path, monkeypatch):
    cfg = DummyCfg({
        "custom2": {"name": "Track", "manifest_field": "track", "default": "_main"},
        "custom3": {"name": "Ghost", "manifest_field": "missingcol", "default": None},
    })
    # Ghost is intentionally absent from the OID -> must be skipped, not error.
    monkeypatch.setattr(arcpy, "ListFields", lambda fc: _fields("ImagePath", "Track"))

    rows = [["C:/x/img_a.jpg", None], ["C:/x/img_b.jpg", None], ["C:/x/img_c.jpg", None]]
    cursor = DummyUpdateCursor(rows)
    captured = {}

    # Pre-scan reads ImagePath via SearchCursor; mirror the same paths.
    monkeypatch.setattr(arcpy.da, "SearchCursor",
                        lambda fc, fields: DummyUpdateCursor([(r[0],) for r in rows]))

    def fake_cursor(fc, fields):
        captured["fields"] = fields
        return cursor

    monkeypatch.setattr(arcpy.da, "UpdateCursor", fake_cursor)

    from unittest.mock import MagicMock
    aio.populate_manifest_custom_fields(cfg, "oid", _write_manifest(tmp_path), MagicMock())

    # Ghost dropped (not on OID); only ImagePath + Track read.
    assert captured["fields"] == ["ImagePath", "Track"]
    by_name = {r[0].split("/")[-1]: r[1] for r in cursor.rows}
    assert by_name["img_a.jpg"] == "2"        # joined from manifest
    assert by_name["img_b.jpg"] == "_main"    # empty cell -> default
    assert by_name["img_c.jpg"] == "_main"    # not in manifest -> default
    assert len(cursor.updated) == 3


def test_populate_noop_without_manifest_fields(tmp_path, monkeypatch):
    cfg = DummyCfg({"custom1": {"name": "RR", "expression": "x"}})
    # If it tried to touch arcpy it would fail loudly; assert it returns early.
    monkeypatch.setattr(arcpy, "ListFields", lambda fc: (_ for _ in ()).throw(AssertionError("should not be called")))
    from unittest.mock import MagicMock
    aio.populate_manifest_custom_fields(cfg, "oid", _write_manifest(tmp_path), MagicMock())
