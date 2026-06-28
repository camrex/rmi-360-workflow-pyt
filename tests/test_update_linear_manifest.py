"""Tests for manifest-driven linear-ref relocation in update_linear_and_custom.

Covers the small pure helpers (event filter, spec lookup, intended-route map).
The full get_located_points path needs a real geodatabase + LR and is exercised
in the ArcGIS Pro environment; _event_allowed is the rule it delegates to.
"""

import csv

import arcpy

from utils import update_linear_and_custom as ulc


class Cfg:
    def __init__(self, vals=None):
        self.vals = vals or {}

    def get(self, key, default=None):
        return self.vals.get(key, default)


# ---------------------------------------------------------------------------
def test_event_allowed_legacy_when_no_map():
    # No intended map -> every event allowed (nearest-event behavior preserved).
    assert ulc._event_allowed("SUBB", "OID_1", None) is True


def test_event_allowed_filters_to_intended_route():
    intended = {"OID_1": "SUBA"}
    assert ulc._event_allowed("SUBA", "OID_1", intended) is True    # intended route
    assert ulc._event_allowed("SUBB", "OID_1", intended) is False   # wrong subdivision
    # Point with no intended entry -> unconstrained.
    assert ulc._event_allowed("SUBZ", "OID_9", intended) is True


def test_event_allowed_stringifies_route_ids():
    assert ulc._event_allowed(12, "OID_1", {"OID_1": "12"}) is True


def test_linear_field_manifest_spec():
    cfg = Cfg({"oid_schema_template.linear_ref_fields": {
        "route_identifier": {"name": "MP_Pre", "type": "TEXT", "manifest_field": "mp_pre"},
        "route_measure": {"name": "MP_Num", "type": "DOUBLE"},  # no manifest_field
    }})
    assert ulc._linear_field_manifest_spec(cfg, "route_identifier") == ("MP_Pre", "mp_pre", None, "TEXT")
    assert ulc._linear_field_manifest_spec(cfg, "route_measure") is None
    assert ulc._linear_field_manifest_spec(cfg, "missing") is None


def test_build_intended_route_map(tmp_path, monkeypatch):
    p = tmp_path / "m.csv"
    with open(p, "w", newline="", encoding="utf-8") as f:
        w = csv.writer(f)
        w.writerow(["Name", "mp_pre"])
        w.writerow(["img_a.jpg", "SUBA"])
        w.writerow(["img_b.jpg", "SUBB"])

    class SC:
        def __init__(self, rows):
            self.rows = rows

        def __enter__(self):
            return self

        def __exit__(self, *a):
            return False

        def __iter__(self):
            return iter(self.rows)

    monkeypatch.setattr(arcpy.da, "SearchCursor",
                        lambda fc, fields: SC([(1, "C:/x/img_a.jpg"), (2, "C:/x/img_b.jpg"), (3, "C:/x/img_c.jpg")]))

    from unittest.mock import MagicMock
    m = ulc._build_intended_route_map(Cfg(), "oid", str(p), "mp_pre", MagicMock())
    assert m == {"OID_1": "SUBA", "OID_2": "SUBB"}  # img_c absent (not in manifest)
