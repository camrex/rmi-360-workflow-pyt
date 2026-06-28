"""Unit tests for utils/shared/manifest_fields.py.

arcpy.ListFields / arcpy.da.UpdateCursor are monkeypatched; no geodatabase needed.
"""

import csv
import types

import arcpy
import pytest

from utils.shared import manifest_fields as mf


def _write_manifest(tmp_path, header, rows):
    p = tmp_path / "manifest.csv"
    with open(p, "w", newline="", encoding="utf-8") as f:
        w = csv.writer(f)
        w.writerow(header)
        w.writerows(rows)
    return str(p)


def _fields(*names):
    return [types.SimpleNamespace(name=n) for n in names]


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


class DummySearchCursor:
    def __init__(self, rows):
        self.rows = [tuple(r) for r in rows]

    def __enter__(self):
        return self

    def __exit__(self, *a):
        return False

    def __iter__(self):
        return iter(self.rows)


class _RaisingLogger:
    """Mimics the real logger: error(..., error_type=E) raises E; others are no-ops."""

    def error(self, msg, *a, error_type=None, **k):
        if error_type:
            raise error_type(msg)

    def __getattr__(self, _name):
        return lambda *a, **k: None


class Cfg:
    def __init__(self, vals=None):
        self.vals = vals or {}

    def get(self, key, default=None):
        return self.vals.get(key, default)


# ---------------------------------------------------------------------------
def test_load_manifest_attr_map_keys_by_name(tmp_path):
    p = _write_manifest(tmp_path, ["Name", "Path", "mp_pre", "mp_meas"],
                        [["a.jpg", "C:/x/a.jpg", "SUBA", "12.5"]])
    amap = mf.load_manifest_attr_map(p, ["mp_pre", "mp_meas"])
    assert amap["a.jpg"] == {"mp_pre": "SUBA", "mp_meas": "12.5"}


def test_resolve_manifest_path():
    assert mf.resolve_manifest_path(Cfg(), explicit="X.csv") == "X.csv"
    assert mf.resolve_manifest_path(Cfg({"thinning_mode": "post"})) is None
    assert mf.resolve_manifest_path(
        Cfg({"thinning_mode": "pre", "corridor_thinning.manifest.path": "M.csv"})) == "M.csv"


def test_linear_override_corrects_wrong_subdivision(tmp_path, monkeypatch):
    """The headline case: LR snapped img_a to the nearest WRONG subdivision; the
    manifest (intended mp_pre/mp_meas) must override it. img_b's empty measure must
    not clobber the existing LR value, and a non-manifest row stays untouched."""
    p = _write_manifest(tmp_path, ["Name", "mp_pre", "mp_meas"],
                        [["img_a.jpg", "SUBA", "12.5"], ["img_b.jpg", "SUBB", ""]])
    monkeypatch.setattr(arcpy, "ListFields", lambda fc: _fields("ImagePath", "MP_Pre", "MP_Num"))

    rows = [
        ["C:/x/img_a.jpg", "SUBX", 99.9],  # LR nearest-but-wrong
        ["C:/x/img_b.jpg", "SUBB", 4.0],
        ["C:/x/img_c.jpg", "SUBC", 7.0],   # not in manifest
    ]
    # Pre-scan reads ImagePath via SearchCursor; mirror the same image paths.
    monkeypatch.setattr(arcpy.da, "SearchCursor",
                        lambda fc, fields: DummySearchCursor([(r[0],) for r in rows]))
    cursor = DummyUpdateCursor(rows)
    captured = {}
    monkeypatch.setattr(arcpy.da, "UpdateCursor",
                        lambda fc, fields: captured.setdefault("fields", fields) or cursor)

    from unittest.mock import MagicMock
    specs = [("MP_Pre", "mp_pre", None, "TEXT"), ("MP_Num", "mp_meas", None, "DOUBLE")]
    updated = mf.populate_oid_fields_from_manifest(Cfg(), "oid", specs, p, MagicMock())

    by = {r[0].split("/")[-1]: (r[1], r[2]) for r in cursor.rows}
    assert by["img_a.jpg"] == ("SUBA", 12.5)          # corrected, and coerced to float
    assert isinstance(by["img_a.jpg"][1], float)
    assert by["img_b.jpg"] == ("SUBB", 4.0)           # empty mp_meas -> LR value kept
    assert by["img_c.jpg"] == ("SUBC", 7.0)           # untouched
    assert updated == 1


def test_noop_without_manifest_or_specs(tmp_path):
    from unittest.mock import MagicMock
    specs = [("MP_Pre", "mp_pre", None, "TEXT")]
    assert mf.populate_oid_fields_from_manifest(Cfg(), "oid", specs, None, MagicMock()) == 0
    p = _write_manifest(tmp_path, ["Name", "mp_pre"], [["a.jpg", "SUBA"]])
    assert mf.populate_oid_fields_from_manifest(Cfg(), "oid", [], p, MagicMock()) == 0


def test_zero_match_fails_fast(tmp_path, monkeypatch):
    """If no OID name matches the manifest (e.g. rename already ran), fail fast."""
    p = _write_manifest(tmp_path, ["Name", "mp_pre"], [["original_a.jpg", "SUBA"]])
    monkeypatch.setattr(arcpy, "ListFields", lambda fc: _fields("ImagePath", "MP_Pre"))
    # OID holds already-renamed paths -> no basename matches the manifest.
    monkeypatch.setattr(arcpy.da, "SearchCursor",
                        lambda fc, fields: DummySearchCursor([("C:/x/RENAMED_x.jpg",), ("C:/x/RENAMED_y.jpg",)]))
    # UpdateCursor must never be reached (we fail before writing).
    monkeypatch.setattr(arcpy.da, "UpdateCursor",
                        lambda *a, **k: (_ for _ in ()).throw(AssertionError("wrote before failing")))

    logger = _RaisingLogger()
    specs = [("MP_Pre", "mp_pre", None, "TEXT")]
    with pytest.raises(RuntimeError, match="BEFORE Rename Images"):
        mf.populate_oid_fields_from_manifest(Cfg(), "oid", specs, str(p), logger)


def test_missing_oid_field_skipped(tmp_path, monkeypatch):
    p = _write_manifest(tmp_path, ["Name", "mp_pre"], [["a.jpg", "SUBA"]])
    monkeypatch.setattr(arcpy, "ListFields", lambda fc: _fields("ImagePath"))  # MP_Pre absent
    from unittest.mock import MagicMock
    specs = [("MP_Pre", "mp_pre", None, "TEXT")]
    # No active fields -> returns 0 without opening a cursor.
    monkeypatch.setattr(arcpy.da, "UpdateCursor",
                        lambda *a, **k: (_ for _ in ()).throw(AssertionError("cursor opened")))
    assert mf.populate_oid_fields_from_manifest(Cfg(), "oid", specs, p, MagicMock()) == 0
