# =============================================================================
# 🧮 OID Geoid Conversion Integration Tests (tests/test_calculate_oid_attributes_geoid.py)
# -----------------------------------------------------------------------------
# Purpose:             Tests the ellipsoidal -> NAVD88 wiring inside enrich_oid_attributes
# Project:             RMI 360 Imaging Workflow Python Toolbox
# Version:             1.0.0
# Author:              RMI Valuation, LLC
# Created:             2026-07-17
#
# Notes:
#   - Stubs arcpy (MagicMock) so the production modules import without ArcGIS.
#   - The pyproj transform itself is covered by tests/test_geoid_transform.py;
#     here it is mocked to isolate the OID read/convert/write plumbing.
# =============================================================================

import sys
from unittest.mock import MagicMock

# Rich arcpy/arcgis stubs so importing the utils package succeeds without ArcGIS.
for _esri_mod in ("arcpy", "arcgis", "arcgis.gis"):
    sys.modules.setdefault(_esri_mod, MagicMock())

import numpy as np
import pytest

import utils.calculate_oid_attributes as coa
from utils.shared.geoid_transform import GeoidTransformError


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
    }
    values.update(overrides or {})
    return lambda k, d=None: values.get(k, d)


def _make_field(name):
    f = MagicMock()
    f.name = name
    return f


# ---------------------------------------------------------------------------
# convert_heights_to_navd88
# ---------------------------------------------------------------------------

def test_convert_adds_field_and_converts(monkeypatch, mock_cfg, logger):
    mock_cfg.get.side_effect = _cfg_get()
    monkeypatch.setattr(coa.arcpy, "ListFields", lambda fc: [_make_field("Z")])
    added = []
    monkeypatch.setattr(
        coa.arcpy.management, "AddField", lambda *a, **kw: added.append((a, kw))
    )
    # (oid, x, y, SHAPE@Z, Z_Ellipsoidal)
    rows = [
        (1, -93.6, 42.0, 1000.0, None),
        (2, -93.7, 42.1, 1010.0, None),
    ]
    monkeypatch.setattr(coa.arcpy.da, "SearchCursor", lambda fc, flds: FakeCursor(rows))
    monkeypatch.setattr(
        coa, "ellipsoidal_to_orthometric",
        lambda lons, lats, zs, model: (np.asarray(zs) + 25.0, np.full(len(zs), -25.0)),
    )

    result = coa.convert_heights_to_navd88(mock_cfg, "oid_fc", logger)

    assert added and added[0][0][1] == coa.ELLIPSOIDAL_Z_FIELD
    assert result == {1: (1025.0, 1000.0), 2: (1035.0, 1010.0)}
    assert logger.info.called


def test_convert_is_idempotent_for_already_converted_rows(monkeypatch, mock_cfg, logger):
    mock_cfg.get.side_effect = _cfg_get()
    monkeypatch.setattr(
        coa.arcpy, "ListFields",
        lambda fc: [_make_field("Z"), _make_field(coa.ELLIPSOIDAL_Z_FIELD)],
    )
    monkeypatch.setattr(
        coa.arcpy.management, "AddField",
        lambda *a, **kw: pytest.fail("AddField must not be called when field exists"),
    )
    # Row 1 was converted before: SHAPE@Z already NAVD88 (1025), original preserved.
    # The source for re-conversion must be the preserved 1000, not 1025.
    rows = [
        (1, -93.6, 42.0, 1026.0, 1000.0),
        (2, -93.7, 42.1, 1010.0, None),
    ]
    monkeypatch.setattr(coa.arcpy.da, "SearchCursor", lambda fc, flds: FakeCursor(rows))
    captured = {}

    def fake_transform(lons, lats, zs, model):
        captured["zs"] = list(zs)
        return np.asarray(zs) + 25.0, np.full(len(zs), -25.0)

    monkeypatch.setattr(coa, "ellipsoidal_to_orthometric", fake_transform)

    result = coa.convert_heights_to_navd88(mock_cfg, "oid_fc", logger)

    assert captured["zs"] == [1000.0, 1010.0]
    assert result == {1: (1025.0, 1000.0), 2: (1035.0, 1010.0)}


def test_convert_returns_none_on_transform_error(monkeypatch, mock_cfg, logger):
    mock_cfg.get.side_effect = _cfg_get()
    monkeypatch.setattr(coa.arcpy, "ListFields", lambda fc: [_make_field(coa.ELLIPSOIDAL_Z_FIELD)])
    rows = [(1, -93.6, 42.0, 1000.0, None)]
    monkeypatch.setattr(coa.arcpy.da, "SearchCursor", lambda fc, flds: FakeCursor(rows))

    def raising_transform(lons, lats, zs, model):
        raise GeoidTransformError("grid missing")

    monkeypatch.setattr(coa, "ellipsoidal_to_orthometric", raising_transform)

    assert coa.convert_heights_to_navd88(mock_cfg, "oid_fc", logger) is None
    assert logger.error.called


def test_convert_skips_rows_without_geometry(monkeypatch, mock_cfg, logger):
    mock_cfg.get.side_effect = _cfg_get()
    monkeypatch.setattr(coa.arcpy, "ListFields", lambda fc: [_make_field(coa.ELLIPSOIDAL_Z_FIELD)])
    rows = [
        (1, None, 42.0, 1000.0, None),   # no x
        (2, -93.6, 42.0, None, None),    # no z at all
        (3, -93.6, 42.0, 1000.0, None),  # usable
    ]
    monkeypatch.setattr(coa.arcpy.da, "SearchCursor", lambda fc, flds: FakeCursor(rows))
    monkeypatch.setattr(
        coa, "ellipsoidal_to_orthometric",
        lambda lons, lats, zs, model: (np.asarray(zs) + 25.0, np.full(len(zs), -25.0)),
    )

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
]


def _setup_enrich(monkeypatch, mock_cfg, data_rows, update_cursor):
    monkeypatch.setattr(coa, "load_field_registry", lambda cfg: REGISTRY)
    monkeypatch.setattr(coa, "check_oid_fov_defaults", lambda *a, **kw: None)
    monkeypatch.setattr(coa, "extract_reel_from_path", lambda p: "0001")
    monkeypatch.setattr(coa, "extract_frame_from_filename", lambda p: "000001")
    monkeypatch.setattr(coa, "load_reel_from_info_file", lambda p, logger: (None, None))
    monkeypatch.setattr(coa.arcpy.management, "GetCount", lambda fc: [str(len(data_rows))])

    class FirstImageCursor(FakeCursor):
        pass

    def search_cursor(fc, flds, where_clause=None):
        return FirstImageCursor([["/img/reel_0001/cam/img_000001.jpg"]])

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
        lambda cfg, fc, logger: {7: (1025.0, 1000.0)},
    )
    cursor = FakeCursor([_row(7, -93.6, 42.0, 1000.0)])
    _setup_enrich(monkeypatch, mock_cfg, cursor.rows, cursor)

    coa.enrich_oid_attributes(mock_cfg, "oid_fc")

    assert len(cursor.updated) == 1
    updated = cursor.updated[0]
    # NAVD88 (1025.0) + 1.0 m lever-arm offset
    assert updated[ENRICH_FIELDS.index("Z")] == pytest.approx(1026.0)
    assert updated[ENRICH_FIELDS.index("SHAPE@Z")] == pytest.approx(1026.0)
    # Original ellipsoidal preserved
    assert updated[ENRICH_FIELDS.index(coa.ELLIPSOIDAL_Z_FIELD)] == pytest.approx(1000.0)
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
    cursor = FakeCursor([_row(7, -93.6, 42.0, 1000.0)])
    _setup_enrich(monkeypatch, mock_cfg, cursor.rows, cursor)

    coa.enrich_oid_attributes(mock_cfg, "oid_fc")

    assert len(cursor.updated) == 1
    updated = cursor.updated[0]
    # Legacy behavior: raw (ellipsoidal) Z + offset
    assert updated[ENRICH_FIELDS.index("Z")] == pytest.approx(1001.0)
    assert updated[ENRICH_FIELDS.index(coa.ELLIPSOIDAL_Z_FIELD)] is None
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
    assert _run_validator(monkeypatch, logger, {"enabled": True, "model": "GEOID18"})


def test_validator_accepts_missing_geoid_section(monkeypatch, logger):
    assert _run_validator(monkeypatch, logger, {})


def test_validator_rejects_unsupported_geoid_model(monkeypatch, logger):
    assert not _run_validator(monkeypatch, logger, {"enabled": True, "model": "EGM2008"})
    assert logger.error.called
