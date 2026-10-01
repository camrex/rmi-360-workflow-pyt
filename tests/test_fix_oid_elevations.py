# =============================================================================
# 🩹 OID Elevation Fix Unit Tests (tests/test_fix_oid_elevations.py)
# -----------------------------------------------------------------------------
# Purpose:             Tests for the ellipsoidal -> NAVD88 repair of existing OIDs
# Project:             RMI 360 Imaging Workflow Python Toolbox
# Version:             1.0.0
# Author:              RMI Valuation, LLC
# Created:             2026-07-17
#
# Notes:
#   - Stubs arcpy/arcgis (MagicMock) so production modules import without ArcGIS.
#   - The pyproj transform is mocked; its correctness is covered by
#     tests/test_geoid_transform.py.
# =============================================================================

import sys
from unittest.mock import MagicMock

# Rich arcpy/arcgis stubs so importing the utils package succeeds without ArcGIS.
for _esri_mod in ("arcpy", "arcgis", "arcgis.gis"):
    sys.modules.setdefault(_esri_mod, MagicMock())

import numpy as np
import pytest

import utils.fix_oid_elevations as foe
from utils.calculate_oid_attributes import ELLIPSOIDAL_Z_FIELD
from utils.shared.geoid_transform import GeoidTransformError


class FakeCursor:
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
    cfg.get.side_effect = lambda k, d=None: {
        "spatial_ref.geoid_correction.model": "GEOID18",
        "spatial_ref.gcs_horizontal_wkid": 4326,
        "spatial_ref.vcs_vertical_wkid": 5703,
        "camera_offset.z": {"a": 100.0},  # 100 cm -> 1.0 m lever-arm offset
    }.get(k, d)
    return cfg


def _make_field(name):
    f = MagicMock()
    f.name = name
    return f


def _patch_transform(monkeypatch, separation=-25.0):
    def fake(lons, lats, zs, model):
        zs = np.asarray(zs, dtype=float)
        return zs - separation, np.full(len(zs), separation)

    monkeypatch.setattr(foe, "ellipsoidal_to_orthometric", fake)


def _setup_arcpy(monkeypatch, search_rows, update_cursor=None, has_ellip_field=False):
    monkeypatch.setattr(foe.arcpy, "Exists", lambda fc: True)
    names = ["Z", "CameraOrientation"]
    if has_ellip_field:
        names.append(ELLIPSOIDAL_Z_FIELD)
    monkeypatch.setattr(foe.arcpy, "ListFields", lambda fc: [_make_field(n) for n in names])
    monkeypatch.setattr(foe.arcpy.da, "SearchCursor", lambda fc, flds: FakeCursor(search_rows))
    if update_cursor is not None:
        monkeypatch.setattr(foe.arcpy.da, "UpdateCursor", lambda fc, flds: update_cursor)
    added = []
    monkeypatch.setattr(foe.arcpy.management, "AddField", lambda *a, **kw: added.append((a, kw)))
    return added


def test_dry_run_reports_without_writing(monkeypatch, mock_cfg, logger):
    _patch_transform(monkeypatch)
    # stored Z 1000.0 = ellipsoidal 999.0 + 1.0 m offset
    added = _setup_arcpy(monkeypatch, [(1, -93.6, 42.0, 1000.0)])
    monkeypatch.setattr(
        foe.arcpy.da, "UpdateCursor",
        lambda fc, flds: pytest.fail("UpdateCursor must not open in dry run"),
    )

    result = foe.fix_oid_elevations(mock_cfg, "oid_fc", dry_run=True)

    assert result.fixed == 1
    assert result.dry_run is True
    assert added == []  # no schema change in dry run
    assert result.separation_min == pytest.approx(-25.0)
    # sample preview: stored 1000.0 -> fixed 1025.0 (N=-25, offset preserved)
    assert result.samples == [(1, 1000.0, pytest.approx(1025.0))]
    assert logger.warning.called  # DRY RUN notice


def test_apply_writes_z_orientation_and_preserves_source(monkeypatch, mock_cfg):
    _patch_transform(monkeypatch, separation=-25.0)
    cursor = FakeCursor([
        # [oid, x, y, SHAPE@Z, Z, CameraOrientation, heading, pitch, roll, Z_Ellipsoidal]
        [1, -93.6, 42.0, 1000.0, 1000.0, "old", 45.0, 90.0, 0.0, None],
    ])
    added = _setup_arcpy(monkeypatch, [(1, -93.6, 42.0, 1000.0)], update_cursor=cursor)

    result = foe.fix_oid_elevations(mock_cfg, "oid_fc", dry_run=False)

    assert result.fixed == 1
    assert added and added[0][0][1] == ELLIPSOIDAL_Z_FIELD
    row = cursor.updated[0]
    assert row[3] == pytest.approx(1025.0)  # SHAPE@Z: 999 + 25 (N) + 1 (offset)
    assert row[4] == pytest.approx(1025.0)  # Z attribute
    assert "|1025.000|" in row[5]           # CameraOrientation rebuilt
    assert row[5].startswith("1|4326|5703|")
    assert row[9] == pytest.approx(999.0)   # pre-offset ellipsoidal source preserved


def test_rows_already_fixed_are_skipped(monkeypatch, mock_cfg, logger):
    _patch_transform(monkeypatch)
    cursor = FakeCursor([
        [2, -93.7, 42.1, 1010.0, 1010.0, "old", 45.0, 90.0, 0.0, None],
    ])
    _setup_arcpy(
        monkeypatch,
        [
            (1, -93.6, 42.0, 1025.0, 999.0),   # Z_Ellipsoidal populated -> fixed already
            (2, -93.7, 42.1, 1010.0, None),    # still ellipsoidal
        ],
        update_cursor=cursor,
        has_ellip_field=True,
    )

    result = foe.fix_oid_elevations(mock_cfg, "oid_fc", dry_run=False)

    assert result.already_fixed == 1
    assert result.fixed == 1
    assert len(cursor.updated) == 1
    assert cursor.updated[0][0] == 2


def test_all_rows_fixed_is_noop(monkeypatch, mock_cfg, logger):
    _patch_transform(monkeypatch)
    _setup_arcpy(
        monkeypatch,
        [(1, -93.6, 42.0, 1025.0, 999.0)],
        has_ellip_field=True,
    )
    monkeypatch.setattr(
        foe, "ellipsoidal_to_orthometric",
        lambda *a, **kw: pytest.fail("transform must not run when nothing to fix"),
    )

    result = foe.fix_oid_elevations(mock_cfg, "oid_fc", dry_run=False)

    assert result.fixed == 0
    assert result.already_fixed == 1


def test_transform_failure_aborts_without_writes(monkeypatch, mock_cfg, logger):
    def raising(*a, **kw):
        raise GeoidTransformError("grid missing")

    monkeypatch.setattr(foe, "ellipsoidal_to_orthometric", raising)
    _setup_arcpy(monkeypatch, [(1, -93.6, 42.0, 1000.0)])
    monkeypatch.setattr(
        foe.arcpy.da, "UpdateCursor",
        lambda fc, flds: pytest.fail("must not write after transform failure"),
    )

    assert foe.fix_oid_elevations(mock_cfg, "oid_fc", dry_run=False) is None
    assert logger.error.called


def test_missing_oid_aborts(monkeypatch, mock_cfg, logger):
    monkeypatch.setattr(foe.arcpy, "Exists", lambda fc: False)
    assert foe.fix_oid_elevations(mock_cfg, "oid_fc", dry_run=True) is None
    assert logger.error.called


def test_service_identity_strips_aws_suffix():
    assert foe._service_identity(r"E:\proj\a26150.gdb\a26150") == ("a26150", False)
    assert foe._service_identity(r"E:\proj\a26150.gdb\a26150_aws") == ("a26150", True)


def test_republish_aws_copy_publishes_directly(monkeypatch, mock_cfg):
    monkeypatch.setattr(foe, "_delete_existing_service_items", lambda gis, name, log: 1)
    captured = {}
    monkeypatch.setattr(
        "utils.generate_oid_service.generate_oid_service",
        lambda **kw: captured.update(kw),
    )

    foe.republish_oid_service(mock_cfg, r"E:\proj\a26150.gdb\a26150_aws")

    assert captured["service_name"] == "a26150"
    assert captured["prepare_copy"] is False           # publish the copy as-is
    assert captured["oid_fc"].endswith("a26150_aws")


def test_republish_source_uses_standard_flow(monkeypatch, mock_cfg):
    monkeypatch.setattr(foe, "_delete_existing_service_items", lambda gis, name, log: 0)
    captured = {}
    monkeypatch.setattr(
        "utils.generate_oid_service.generate_oid_service",
        lambda **kw: captured.update(kw),
    )

    foe.republish_oid_service(mock_cfg, r"E:\proj\a26150.gdb\a26150")

    assert captured["service_name"] == "a26150"
    assert captured["prepare_copy"] is True            # duplicate + rewrite ImagePaths


def test_missing_orientation_parts_fixes_z_only(monkeypatch, mock_cfg, logger):
    _patch_transform(monkeypatch)
    cursor = FakeCursor([
        [1, -93.6, 42.0, 1000.0, 1000.0, "old", None, 90.0, 0.0, None],
    ])
    _setup_arcpy(monkeypatch, [(1, -93.6, 42.0, 1000.0)], update_cursor=cursor)

    foe.fix_oid_elevations(mock_cfg, "oid_fc", dry_run=False)

    row = cursor.updated[0]
    assert row[3] == pytest.approx(1025.0)
    assert row[5] == "old"  # orientation untouched when heading missing
    assert logger.warning.called
