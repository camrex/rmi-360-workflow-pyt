# =============================================================================
# 🧮 OID Geoid Conversion Integration Tests (tests/test_calculate_oid_attributes_geoid.py)
# -----------------------------------------------------------------------------
# Purpose:             Tests the ellipsoidal -> NAVD88 wiring inside enrich_oid_attributes
# Project:             RMI 360 Imaging Workflow Python Toolbox
# Version:             1.1.0
# Author:              RMI Valuation, LLC
# Created:             2026-07-17
# Last Updated:        2026-10-01
#
# Notes:
#   - Stubs arcpy (MagicMock) so the production modules import without ArcGIS.
#   - The pyproj transforms themselves are covered by tests/test_geoid_transform.py;
#     here they are mocked to isolate the OID read/convert/write plumbing.
# =============================================================================

import sys
from datetime import datetime
from unittest.mock import MagicMock

# Rich arcpy/arcgis stubs so importing the utils package succeeds without ArcGIS.
for _esri_mod in ("arcpy", "arcgis", "arcgis.gis"):
    sys.modules.setdefault(_esri_mod, MagicMock())

import numpy as np
import pytest

import utils.calculate_oid_attributes as coa
from utils.shared.geoid_transform import GeoidTransformError

ACQ = datetime(2026, 1, 19, 12, 0, 0)   # ~2026.05
FRAME_SHIFT = 1.08                       # ITRF2014 -> NAD83(2011) height change (IL)


class FakeCursor:
    """Context-manager cursor over preloaded rows (Search or Update)."""

    def __init__(self, rows):
        self.rows = rows
        self.updated = []

    def __enter__(self):
        return self

    def __exit__(self, *exc):
        return False

    def __iter__(self):
        return iter(self.rows)

    def updateRow(self, row):
        self.updated.append(list(row))


@pytest.fixture
def logger():
    return MagicMock()


@pytest.fixture
def mock_cfg(logger):
    cfg = MagicMock()
    cfg.get_logger.return_value = logger
    progressor = MagicMock()
    progressor.update = lambda i: None
    cfg.get_progressor.return_value.__enter__.return_value = progressor
    cfg.get_progressor.return_value.__exit__.return_value = False
    cfg.validate.return_value = True
    return cfg


def _cfg_get(overrides=None):
    values = {
        "oid_schema_template.esri_default": {},
        "oid_schema_template": {"mosaic_fields": {}},
        "camera_offset.z": {"a": 100.0},           # 100 cm -> 1.0 m offset
        "camera_offset.camera_height": {"a": 250.0},
        "spatial_ref.gcs_horizontal_wkid": 4326,
        "spatial_ref.vcs_vertical_wkid": 5703,
        "spatial_ref.geoid_correction.enabled": True,
        "spatial_ref.geoid_correction.model": "GEOID18",
        "spatial_ref.geoid_correction.source_frame": "ITRF2014",
    }
    values.update(overrides or {})
    return lambda k, d=None: values.get(k, d)


def _make_field(name):
    f = MagicMock()
    f.name = name
    return f


def _fields(*names):
    return lambda fc: [_make_field(n) for n in names]


def _patch_transforms(monkeypatch, captured=None):
    """Frame step adds FRAME_SHIFT; geoid step adds 25 m (N = -25)."""
    def fake_frame(lons, lats, zs, frame, epoch):
        if captured is not None:
            captured.update(frame=frame, frame_in=list(zs), epoch=epoch)
        zs = np.asarray(zs, dtype=float)
        return zs + FRAME_SHIFT, np.full(len(zs), FRAME_SHIFT)

    def fake_geoid(lons, lats, zs, model):
        if captured is not None:
            captured["geoid_in"] = list(zs)
        zs = np.asarray(zs, dtype=float)
        return zs + 25.0, np.full(len(zs), -25.0)

    monkeypatch.setattr(coa, "to_nad83_2011", fake_frame)
    monkeypatch.setattr(coa, "ellipsoidal_to_orthometric", fake_geoid)


# ---------------------------------------------------------------------------
# resolve_source_frame / frame_tag
# ---------------------------------------------------------------------------

def test_resolve_source_frame_prefers_override(mock_cfg):
    mock_cfg.get.side_effect = _cfg_get()
    assert coa.resolve_source_frame(mock_cfg) == "ITRF2014"
    assert coa.resolve_source_frame(mock_cfg, "nad83_2011") == "NAD83_2011"


def test_resolve_source_frame_never_guesses(mock_cfg):
    mock_cfg.get.side_effect = _cfg_get({"spatial_ref.geoid_correction.source_frame": None})
    with pytest.raises(GeoidTransformError, match="source_frame is not set"):
        coa.resolve_source_frame(mock_cfg)
    with pytest.raises(GeoidTransformError, match="Unsupported source_frame"):
        coa.resolve_source_frame(mock_cfg, "GDA2020")


def test_frame_tag():
    assert coa.frame_tag("ITRF2014", 2026.0512) == "ITRF2014@2026.051"
    assert coa.frame_tag("NAD83_2011", 2026.05) == "NAD83_2011"


# ---------------------------------------------------------------------------
# convert_heights_to_navd88
# ---------------------------------------------------------------------------

def test_convert_applies_frame_shift_before_geoid(monkeypatch, mock_cfg, logger):
    mock_cfg.get.side_effect = _cfg_get()
    monkeypatch.setattr(coa.arcpy, "ListFields", _fields("Z", "AcquisitionDate"))
    added = []
    monkeypatch.setattr(coa.arcpy.management, "AddField", lambda *a, **kw: added.append(a[1]))
    # (oid, x, y, SHAPE@Z, Z_Ellipsoidal, AcquisitionDate)
    rows = [(1, -87.9, 41.8, 1000.0, None, ACQ), (2, -87.9, 41.8, 1010.0, None, ACQ)]
    monkeypatch.setattr(coa.arcpy.da, "SearchCursor", lambda fc, flds: FakeCursor(rows))
    captured = {}
    _patch_transforms(monkeypatch, captured)

    result = coa.convert_heights_to_navd88(mock_cfg, "oid_fc", logger)

    assert added == [coa.ELLIPSOIDAL_Z_FIELD, coa.Z_FRAME_FIELD]
    assert captured["frame"] == "ITRF2014"
    assert captured["frame_in"] == [1000.0, 1010.0]
    assert captured["geoid_in"] == pytest.approx([1000.0 + FRAME_SHIFT, 1010.0 + FRAME_SHIFT])
    assert list(captured["epoch"]) == pytest.approx([2026.05] * 2, abs=0.01)
    z, src, tag = result[1]
    assert z == pytest.approx(1000.0 + FRAME_SHIFT + 25.0)
    assert src == 1000.0                                  # original, unshifted
    assert tag.startswith("ITRF2014@2026.0")


def test_convert_is_idempotent_for_already_converted_rows(monkeypatch, mock_cfg, logger):
    mock_cfg.get.side_effect = _cfg_get()
    monkeypatch.setattr(
        coa.arcpy, "ListFields",
        _fields("Z", "AcquisitionDate", coa.ELLIPSOIDAL_Z_FIELD, coa.Z_FRAME_FIELD),
    )
    monkeypatch.setattr(
        coa.arcpy.management, "AddField",
        lambda *a, **kw: pytest.fail("AddField must not be called when fields exist"),
    )
    # Row 1 was converted before: the source for re-conversion must be the
    # preserved 1000, not the stored NAVD88 value.
    rows = [(1, -87.9, 41.8, 1026.0, 1000.0, ACQ), (2, -87.9, 41.8, 1010.0, None, ACQ)]
    monkeypatch.setattr(coa.arcpy.da, "SearchCursor", lambda fc, flds: FakeCursor(rows))
    captured = {}
    _patch_transforms(monkeypatch, captured)

    result = coa.convert_heights_to_navd88(mock_cfg, "oid_fc", logger)

    assert captured["frame_in"] == [1000.0, 1010.0]
    assert result[1][0] == pytest.approx(1000.0 + FRAME_SHIFT + 25.0)


def test_convert_nad83_source_needs_no_date(monkeypatch, mock_cfg, logger):
    mock_cfg.get.side_effect = _cfg_get({"spatial_ref.geoid_correction.source_frame": "NAD83_2011"})
    monkeypatch.setattr(coa.arcpy, "ListFields", _fields(coa.ELLIPSOIDAL_Z_FIELD, coa.Z_FRAME_FIELD))
    seen = {}

    def search(fc, flds):
        seen["fields"] = flds
        return FakeCursor([(1, -87.9, 41.8, 1000.0, None)])

    monkeypatch.setattr(coa.arcpy.da, "SearchCursor", search)
    monkeypatch.setattr(
        coa, "ellipsoidal_to_orthometric",
        lambda lons, lats, zs, model: (np.asarray(zs) + 25.0, np.full(len(zs), -25.0)),
    )  # real to_nad83_2011: NAD83_2011 returns heights unchanged without PROJ

    result = coa.convert_heights_to_navd88(mock_cfg, "oid_fc", logger)

    assert "AcquisitionDate" not in seen["fields"]
    assert result == {1: (1025.0, 1000.0, "NAD83_2011")}


def test_convert_refuses_without_source_frame(monkeypatch, mock_cfg, logger):
    mock_cfg.get.side_effect = _cfg_get({"spatial_ref.geoid_correction.source_frame": None})
    monkeypatch.setattr(
        coa.arcpy.da, "SearchCursor", lambda *a, **kw: pytest.fail("must not read rows"),
    )
    assert coa.convert_heights_to_navd88(mock_cfg, "oid_fc", logger) is None
    assert logger.error.called


def test_convert_refuses_rows_without_acquisition_date(monkeypatch, mock_cfg, logger):
    mock_cfg.get.side_effect = _cfg_get()
    monkeypatch.setattr(
        coa.arcpy, "ListFields",
        _fields("AcquisitionDate", coa.ELLIPSOIDAL_Z_FIELD, coa.Z_FRAME_FIELD),
    )
    rows = [(1, -87.9, 41.8, 1000.0, None, ACQ), (2, -87.9, 41.8, 1000.0, None, None)]
    monkeypatch.setattr(coa.arcpy.da, "SearchCursor", lambda fc, flds: FakeCursor(rows))
    _patch_transforms(monkeypatch)

    assert coa.convert_heights_to_navd88(mock_cfg, "oid_fc", logger) is None
    assert "AcquisitionDate" in logger.error.call_args[0][0]


def test_convert_refuses_without_acquisition_field(monkeypatch, mock_cfg, logger):
    mock_cfg.get.side_effect = _cfg_get()
    monkeypatch.setattr(coa.arcpy, "ListFields", _fields(coa.ELLIPSOIDAL_Z_FIELD))
    monkeypatch.setattr(
        coa.arcpy.management, "AddField", lambda *a, **kw: pytest.fail("nothing may change"),
    )
    assert coa.convert_heights_to_navd88(mock_cfg, "oid_fc", logger) is None


def test_convert_returns_none_on_transform_error(monkeypatch, mock_cfg, logger):
    mock_cfg.get.side_effect = _cfg_get()
    monkeypatch.setattr(
        coa.arcpy, "ListFields",
        _fields("AcquisitionDate", coa.ELLIPSOIDAL_Z_FIELD, coa.Z_FRAME_FIELD),
    )
    rows = [(1, -87.9, 41.8, 1000.0, None, ACQ)]
    monkeypatch.setattr(coa.arcpy.da, "SearchCursor", lambda fc, flds: FakeCursor(rows))

    def raising_frame(*a, **kw):
        raise GeoidTransformError("no-op frame transformation")

    monkeypatch.setattr(coa, "to_nad83_2011", raising_frame)

    assert coa.convert_heights_to_navd88(mock_cfg, "oid_fc", logger) is None
    assert logger.error.called


def test_convert_skips_rows_without_geometry(monkeypatch, mock_cfg, logger):
    mock_cfg.get.side_effect = _cfg_get()
    monkeypatch.setattr(
        coa.arcpy, "ListFields",
        _fields("AcquisitionDate", coa.ELLIPSOIDAL_Z_FIELD, coa.Z_FRAME_FIELD),
    )
    rows = [
        (1, None, 42.0, 1000.0, None, ACQ),    # no x
        (2, -93.6, 42.0, None, None, ACQ),     # no z at all
        (3, -93.6, 42.0, 1000.0, None, ACQ),   # usable
    ]
    monkeypatch.setattr(coa.arcpy.da, "SearchCursor", lambda fc, flds: FakeCursor(rows))
    _patch_transforms(monkeypatch)

    result = coa.convert_heights_to_navd88(mock_cfg, "oid_fc", logger)
    assert set(result) == {3}


# ---------------------------------------------------------------------------
# enrich_oid_attributes wiring
# ---------------------------------------------------------------------------

REGISTRY = {
    "CameraPitch": {"name": "CameraPitch", "oid_default": 90, "category": "standard"},
    "CameraRoll": {"name": "CameraRoll", "oid_default": 0, "category": "standard"},
    "NearDistance": {"name": "NearDistance", "oid_default": 2, "category": "standard"},
    "FarDistance": {"name": "FarDistance", "oid_default": 50, "category": "standard"},
    "CameraHeight": {"name": "CameraHeight", "oid_default": 2.5, "category": "standard"},
    "SRS": {"name": "SRS", "category": "standard"},
    "X": {"name": "X", "category": "standard"},
    "Y": {"name": "Y", "category": "standard"},
    "Z": {"name": "Z", "category": "standard"},
    "CameraOrientation": {"name": "CameraOrientation", "category": "standard"},
    "CameraHeading": {"name": "CameraHeading", "category": "standard"},
    "ImagePath": {"name": "ImagePath", "category": "standard"},
}

ENRICH_FIELDS = [
    "OID@", "SHAPE@X", "SHAPE@Y", "SHAPE@Z", "CameraPitch", "CameraRoll",
    "NearDistance", "FarDistance", "CameraHeight", "SRS", "X", "Y", "Z",
    "CameraOrientation", "CameraHeading", "ImagePath", coa.ELLIPSOIDAL_Z_FIELD,
    coa.Z_FRAME_FIELD,
]


def _setup_enrich(monkeypatch, mock_cfg, data_rows, update_cursor):
    monkeypatch.setattr(coa, "load_field_registry", lambda cfg: REGISTRY)
    monkeypatch.setattr(coa, "check_oid_fov_defaults", lambda *a, **kw: None)
    monkeypatch.setattr(coa, "extract_reel_from_path", lambda p: "0001")
    monkeypatch.setattr(coa, "extract_frame_from_filename", lambda p: "000001")
    monkeypatch.setattr(coa, "load_reel_from_info_file", lambda p, logger: (None, None))
    monkeypatch.setattr(coa.arcpy.management, "GetCount", lambda fc: [str(len(data_rows))])

    def search_cursor(fc, flds, where_clause=None):
        return FakeCursor([["/img/reel_0001/cam/img_000001.jpg"]])

    monkeypatch.setattr(coa.arcpy.da, "SearchCursor", search_cursor)
    monkeypatch.setattr(coa.arcpy.da, "UpdateCursor", lambda fc, flds: update_cursor)


def _row(oid, x, y, z):
    row = [None] * len(ENRICH_FIELDS)
    row[ENRICH_FIELDS.index("OID@")] = oid
    row[ENRICH_FIELDS.index("SHAPE@X")] = x
    row[ENRICH_FIELDS.index("SHAPE@Y")] = y
    row[ENRICH_FIELDS.index("SHAPE@Z")] = z
    row[ENRICH_FIELDS.index("CameraHeading")] = 45.0
    row[ENRICH_FIELDS.index("ImagePath")] = "/img/reel_0001/cam/img_000001.jpg"
    return row


def test_enrich_applies_conversion_before_offset(monkeypatch, mock_cfg):
    mock_cfg.get.side_effect = _cfg_get()
    monkeypatch.setattr(
        coa, "convert_heights_to_navd88",
        lambda cfg, fc, logger: {7: (1025.0, 1000.0, "ITRF2014@2026.051")},
    )
    cursor = FakeCursor([_row(7, -93.6, 42.0, 1000.0)])
    _setup_enrich(monkeypatch, mock_cfg, cursor.rows, cursor)

    coa.enrich_oid_attributes(mock_cfg, "oid_fc")

    assert len(cursor.updated) == 1
    updated = cursor.updated[0]
    # NAVD88 (1025.0) + 1.0 m lever-arm offset
    assert updated[ENRICH_FIELDS.index("Z")] == pytest.approx(1026.0)
    assert updated[ENRICH_FIELDS.index("SHAPE@Z")] == pytest.approx(1026.0)
    # Original ellipsoidal preserved; frame/epoch recorded
    assert updated[ENRICH_FIELDS.index(coa.ELLIPSOIDAL_Z_FIELD)] == pytest.approx(1000.0)
    assert updated[ENRICH_FIELDS.index(coa.Z_FRAME_FIELD)] == "ITRF2014@2026.051"
    # Orientation string embeds the converted+offset Z, not the ellipsoidal one
    assert "|1026.000|" in updated[ENRICH_FIELDS.index("CameraOrientation")]


def test_enrich_aborts_when_conversion_fails(monkeypatch, mock_cfg, logger):
    mock_cfg.get.side_effect = _cfg_get()
    monkeypatch.setattr(coa, "convert_heights_to_navd88", lambda cfg, fc, logger: None)
    cursor = FakeCursor([_row(7, -93.6, 42.0, 1000.0)])
    _setup_enrich(monkeypatch, mock_cfg, cursor.rows, cursor)

    coa.enrich_oid_attributes(mock_cfg, "oid_fc")

    # Hard stop: no rows written with unconverted heights
    assert cursor.updated == []


def test_enrich_disabled_keeps_ellipsoidal_and_warns(monkeypatch, mock_cfg, logger):
    mock_cfg.get.side_effect = _cfg_get({"spatial_ref.geoid_correction.enabled": False})
    monkeypatch.setattr(
        coa, "convert_heights_to_navd88",
        lambda cfg, fc, logger: pytest.fail("conversion must not run when disabled"),
    )
    fields = [f for f in ENRICH_FIELDS if f not in (coa.ELLIPSOIDAL_Z_FIELD, coa.Z_FRAME_FIELD)]
    row = [None] * len(fields)
    row[fields.index("OID@")] = 7
    row[fields.index("SHAPE@X")], row[fields.index("SHAPE@Y")] = -93.6, 42.0
    row[fields.index("SHAPE@Z")] = 1000.0
    row[fields.index("CameraHeading")] = 45.0
    row[fields.index("ImagePath")] = "/img/reel_0001/cam/img_000001.jpg"
    cursor = FakeCursor([row])
    _setup_enrich(monkeypatch, mock_cfg, cursor.rows, cursor)

    coa.enrich_oid_attributes(mock_cfg, "oid_fc")

    assert len(cursor.updated) == 1
    # Legacy behavior: raw (ellipsoidal) Z + offset
    assert cursor.updated[0][fields.index("Z")] == pytest.approx(1001.0)
    assert logger.warning.called


def test_enrich_skips_row_missing_from_conversion(monkeypatch, mock_cfg, logger):
    mock_cfg.get.side_effect = _cfg_get()
    monkeypatch.setattr(coa, "convert_heights_to_navd88", lambda cfg, fc, logger: {})
    cursor = FakeCursor([_row(7, -93.6, 42.0, 1000.0)])
    _setup_enrich(monkeypatch, mock_cfg, cursor.rows, cursor)

    coa.enrich_oid_attributes(mock_cfg, "oid_fc")

    assert cursor.updated == []
    assert logger.warning.called


# ---------------------------------------------------------------------------
# Validator: spatial_ref.geoid_correction
# ---------------------------------------------------------------------------

def _validator_cfg(logger, geoid_section):
    from utils.validators import calculate_oid_attributes_validator as validator_mod

    registry = {
        key: dict(REGISTRY[key]) for key in REGISTRY
    }
    registry["CameraOrientation"]["orientation_format"] = "type1_short"

    cfg = MagicMock()
    cfg.get_logger.return_value = logger
    cfg.get.side_effect = lambda k, d=None: {
        "oid_schema_template": {
            "esri_default": {},
            "mosaic_fields": {
                "mosaic_reel": {"name": "mosaic_reel"},
                "mosaic_frame": {"name": "mosaic_frame"},
            },
            "linear_ref_fields": {
                "route_identifier": {"name": "route_identifier"},
                "route_measure": {"name": "route_measure"},
            },
        },
        "camera_offset": {"z": {"a": 10}, "camera_height": {"a": 150}},
        "spatial_ref.geoid_correction": geoid_section,
    }.get(k, d)
    return cfg, validator_mod, registry


def _run_validator(monkeypatch, logger, geoid_section):
    cfg, validator_mod, registry = _validator_cfg(logger, geoid_section)
    monkeypatch.setattr(validator_mod, "load_field_registry", lambda c: registry)
    monkeypatch.setattr(validator_mod, "validate_field_block", lambda *a, **kw: True)
    monkeypatch.setattr(validator_mod, "validate_expression_block", lambda *a, **kw: True)
    monkeypatch.setattr(validator_mod, "validate_config_section", lambda *a, **kw: True)
    return validator_mod.validate(cfg)


def test_validator_accepts_geoid_section(monkeypatch, logger):
    assert _run_validator(
        monkeypatch, logger, {"enabled": True, "model": "GEOID18", "source_frame": "ITRF2014"}
    )


def test_validator_accepts_missing_geoid_section(monkeypatch, logger):
    assert _run_validator(monkeypatch, logger, {})


def test_validator_accepts_older_section_without_source_frame(monkeypatch, logger):
    # Maintenance tools load older configs and take the frame as a parameter.
    assert _run_validator(monkeypatch, logger, {"enabled": True, "model": "GEOID18"})


def test_validator_rejects_unknown_source_frame(monkeypatch, logger):
    assert not _run_validator(
        monkeypatch, logger, {"enabled": True, "model": "GEOID18", "source_frame": "GDA2020"}
    )
    assert logger.error.called


def test_validator_rejects_unsupported_geoid_model(monkeypatch, logger):
    assert not _run_validator(monkeypatch, logger, {"enabled": True, "model": "EGM2008"})
    assert logger.error.called
