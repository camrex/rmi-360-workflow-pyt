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
from datetime import datetime
from unittest.mock import MagicMock

# Rich arcpy/arcgis stubs so importing the utils package succeeds without ArcGIS.
for _esri_mod in ("arcpy", "arcgis", "arcgis.gis"):
    sys.modules.setdefault(_esri_mod, MagicMock())

import numpy as np
import pytest

import utils.fix_oid_elevations as foe
from utils.calculate_oid_attributes import ELLIPSOIDAL_Z_FIELD, Z_FRAME_FIELD
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


ACQ = datetime(2026, 1, 19, 12, 0, 0)   # ~2026.05
FRAME_SHIFT = 1.08                       # ITRF2014 -> NAD83(2011) height change (IL)


@pytest.fixture
def logger():
    return MagicMock()


def _cfg_values(overrides=None):
    values = {
        "spatial_ref.geoid_correction.model": "GEOID18",
        "spatial_ref.geoid_correction.source_frame": "ITRF2014",
        "spatial_ref.gcs_horizontal_wkid": 4326,
        "spatial_ref.vcs_vertical_wkid": 5703,
        "camera_offset.z": {"a": 100.0},  # 100 cm -> 1.0 m lever-arm offset
    }
    values.update(overrides or {})
    return lambda k, d=None: values.get(k, d)


@pytest.fixture
def mock_cfg(logger):
    cfg = MagicMock()
    cfg.get_logger.return_value = logger
    progressor = MagicMock()
    progressor.update = lambda i: None
    cfg.get_progressor.return_value.__enter__.return_value = progressor
    cfg.get_progressor.return_value.__exit__.return_value = False
    cfg.validate.return_value = True
    cfg.get.side_effect = _cfg_values()
    return cfg


def _make_field(name):
    f = MagicMock()
    f.name = name
    return f


def _patch_transform(monkeypatch, separation=-25.0, shift=FRAME_SHIFT):
    def fake_frame(lons, lats, zs, frame, epoch):
        zs = np.asarray(zs, dtype=float)
        return zs + shift, np.full(len(zs), shift)

    def fake_geoid(lons, lats, zs, model):
        zs = np.asarray(zs, dtype=float)
        return zs - separation, np.full(len(zs), separation)

    monkeypatch.setattr(foe, "to_nad83_2011", fake_frame)
    monkeypatch.setattr(foe, "ellipsoidal_to_orthometric", fake_geoid)


def _rec(oid, z, ellip=None, frame=None, acq=ACQ, x=-87.9, y=41.8):
    return {"OID@": oid, "SHAPE@X": x, "SHAPE@Y": y, "SHAPE@Z": z,
            ELLIPSOIDAL_Z_FIELD: ellip, Z_FRAME_FIELD: frame, "AcquisitionDate": acq}


def _setup_arcpy(monkeypatch, records, update_rows=None, has_ellip_field=False,
                 has_frame_field=False):
    """SearchCursor yields each record's values for whatever fields are requested."""
    monkeypatch.setattr(foe.arcpy, "Exists", lambda fc: True)
    names = ["Z", "CameraOrientation", "AcquisitionDate"]
    if has_ellip_field:
        names.append(ELLIPSOIDAL_Z_FIELD)
    if has_frame_field:
        names.append(Z_FRAME_FIELD)
    monkeypatch.setattr(foe.arcpy, "ListFields", lambda fc: [_make_field(n) for n in names])
    monkeypatch.setattr(
        foe.arcpy.da, "SearchCursor",
        lambda fc, flds: FakeCursor([tuple(r[f] for f in flds) for r in records]),
    )
    cursor = None
    if update_rows is not None:
        cursor = FakeCursor(update_rows)
        monkeypatch.setattr(foe.arcpy.da, "UpdateCursor", lambda fc, flds: cursor)
    added = []
    monkeypatch.setattr(foe.arcpy.management, "AddField", lambda *a, **kw: added.append(a[1]))
    return added, cursor


def _urow(oid, z, ellip=None, frame=None, heading=45.0):
    # [oid, x, y, SHAPE@Z, Z, CameraOrientation, heading, pitch, roll, Z_Ellipsoidal, Z_Frame]
    return [oid, -87.9, 41.8, z, z, "old", heading, 90.0, 0.0, ellip, frame]


# --- never-converted rows: full conversion ------------------------------------

def test_dry_run_reports_without_writing(monkeypatch, mock_cfg, logger):
    _patch_transform(monkeypatch)
    # stored Z 1000.0 = ellipsoidal 999.0 + 1.0 m offset
    added, _ = _setup_arcpy(monkeypatch, [_rec(1, 1000.0)])
    monkeypatch.setattr(
        foe.arcpy.da, "UpdateCursor",
        lambda fc, flds: pytest.fail("UpdateCursor must not open in dry run"),
    )

    result = foe.fix_oid_elevations(mock_cfg, "oid_fc", dry_run=True)

    assert result.fixed == 1 and result.converted == 1
    assert result.dry_run is True and result.source_frame == "ITRF2014"
    assert added == []  # no schema change in dry run
    assert result.separation_min == pytest.approx(-25.0)
    assert result.frame_shift_min == pytest.approx(FRAME_SHIFT)
    # 999 ellipsoidal + 1.08 frame + 25 geoid + 1 offset
    assert result.samples == [(1, 1000.0, pytest.approx(1026.08))]
    assert logger.warning.called  # DRY RUN notice


def test_apply_full_conversion_writes_z_source_and_frame(monkeypatch, mock_cfg):
    _patch_transform(monkeypatch)
    added, cursor = _setup_arcpy(monkeypatch, [_rec(1, 1000.0)], update_rows=[_urow(1, 1000.0)])

    result = foe.fix_oid_elevations(mock_cfg, "oid_fc", dry_run=False)

    assert result.fixed == 1
    assert added == [ELLIPSOIDAL_Z_FIELD, Z_FRAME_FIELD]
    row = cursor.updated[0]
    assert row[3] == pytest.approx(1026.08)   # SHAPE@Z
    assert row[4] == pytest.approx(1026.08)   # Z attribute
    assert "|1026.080|" in row[5] and row[5].startswith("1|4326|5703|")
    assert row[9] == pytest.approx(999.0)     # pre-offset ellipsoidal source preserved
    assert row[10].startswith("ITRF2014@2026.0")


# --- converted under 1.5.0 without the frame step -----------------------------

def test_legacy_converted_rows_get_frame_shift_only(monkeypatch, mock_cfg):
    _patch_transform(monkeypatch)
    monkeypatch.setattr(
        foe, "ellipsoidal_to_orthometric",
        lambda *a, **kw: pytest.fail("GEOID18 was already applied to these rows"),
    )
    # Converted under 1.5.0: stored 1025 = 999 + 25 (N) + 1 (offset); no Z_Frame.
    _, cursor = _setup_arcpy(
        monkeypatch, [_rec(1, 1025.0, ellip=999.0)],
        update_rows=[_urow(1, 1025.0, ellip=999.0)], has_ellip_field=True,
    )

    result = foe.fix_oid_elevations(mock_cfg, "oid_fc", dry_run=False)

    assert result.frame_corrected == 1 and result.converted == 0
    row = cursor.updated[0]
    assert row[3] == pytest.approx(1025.0 + FRAME_SHIFT)   # built offset kept as-is
    assert row[9] == pytest.approx(999.0)                  # Z_Ellipsoidal untouched
    assert row[10].startswith("ITRF2014@")


def test_legacy_rows_with_nad83_source_are_marked_only(monkeypatch, mock_cfg):
    monkeypatch.setattr(foe, "to_nad83_2011", lambda *a, **kw: pytest.fail("no shift for NAD83"))
    _, cursor = _setup_arcpy(
        monkeypatch, [_rec(1, 1025.0, ellip=999.0, acq=None)],
        update_rows=[_urow(1, 1025.0, ellip=999.0)], has_ellip_field=True,
    )

    result = foe.fix_oid_elevations(mock_cfg, "oid_fc", dry_run=False, source_frame="NAD83_2011")

    assert result.marked_only == 1
    assert cursor.updated[0][3] == pytest.approx(1025.0)   # Z unchanged
    assert cursor.updated[0][10] == "NAD83_2011"


# --- idempotency / refusal cases ----------------------------------------------

def test_rows_with_matching_frame_are_skipped(monkeypatch, mock_cfg, logger):
    _patch_transform(monkeypatch)
    _, cursor = _setup_arcpy(
        monkeypatch,
        [_rec(1, 1026.08, ellip=999.0, frame="ITRF2014@2026.051"),  # done
         _rec(2, 1025.0, ellip=999.0)],                              # 1.5.0, needs dh
        update_rows=[_urow(2, 1025.0, ellip=999.0)],
        has_ellip_field=True, has_frame_field=True,
    )

    result = foe.fix_oid_elevations(mock_cfg, "oid_fc", dry_run=False)

    assert result.already_fixed == 1 and result.fixed == 1
    assert [r[0] for r in cursor.updated] == [2]


def test_all_rows_fixed_is_noop(monkeypatch, mock_cfg):
    monkeypatch.setattr(foe, "to_nad83_2011", lambda *a, **kw: pytest.fail("nothing to fix"))
    _setup_arcpy(
        monkeypatch, [_rec(1, 1026.08, ellip=999.0, frame="ITRF2014@2026.051")],
        has_ellip_field=True, has_frame_field=True,
    )

    result = foe.fix_oid_elevations(mock_cfg, "oid_fc", dry_run=False)

    assert result.fixed == 0 and result.already_fixed == 1


def test_conflicting_frame_refuses_whole_run(monkeypatch, mock_cfg, logger):
    _patch_transform(monkeypatch)
    _setup_arcpy(
        monkeypatch,
        [_rec(1, 1025.0, ellip=999.0, frame="NAD83_2011"), _rec(2, 1000.0)],
        has_ellip_field=True, has_frame_field=True,
    )
    monkeypatch.setattr(foe.arcpy.da, "UpdateCursor", lambda *a: pytest.fail("no writes"))

    assert foe.fix_oid_elevations(mock_cfg, "oid_fc", dry_run=False) is None
    assert "different reference frame" in logger.error.call_args[0][0]


def test_missing_acquisition_date_refuses(monkeypatch, mock_cfg, logger):
    _patch_transform(monkeypatch)
    _setup_arcpy(monkeypatch, [_rec(1, 1000.0), _rec(2, 1000.0, acq=None)])
    monkeypatch.setattr(foe.arcpy.da, "UpdateCursor", lambda *a: pytest.fail("no writes"))

    assert foe.fix_oid_elevations(mock_cfg, "oid_fc", dry_run=False) is None
    assert "AcquisitionDate" in logger.error.call_args[0][0]


def test_missing_source_frame_refuses(monkeypatch, mock_cfg, logger):
    # An older (pre-1.6.0) project config has no source_frame and none was passed.
    mock_cfg.get.side_effect = _cfg_values({"spatial_ref.geoid_correction.source_frame": None})
    _setup_arcpy(monkeypatch, [_rec(1, 1000.0)])
    monkeypatch.setattr(foe.arcpy.da, "SearchCursor", lambda *a: pytest.fail("must not read"))

    assert foe.fix_oid_elevations(mock_cfg, "oid_fc", dry_run=True) is None
    assert logger.error.called


def test_source_frame_parameter_covers_older_config(monkeypatch, mock_cfg):
    mock_cfg.get.side_effect = _cfg_values({"spatial_ref.geoid_correction.source_frame": None})
    _patch_transform(monkeypatch)
    _setup_arcpy(monkeypatch, [_rec(1, 1000.0)])

    result = foe.fix_oid_elevations(mock_cfg, "oid_fc", dry_run=True, source_frame="ITRF2014")

    assert result.source_frame == "ITRF2014" and result.fixed == 1


def test_transform_failure_aborts_without_writes(monkeypatch, mock_cfg, logger):
    def raising(*a, **kw):
        raise GeoidTransformError("no-op frame transformation")

    monkeypatch.setattr(foe, "to_nad83_2011", raising)
    _setup_arcpy(monkeypatch, [_rec(1, 1000.0)])
    monkeypatch.setattr(foe.arcpy.da, "UpdateCursor", lambda *a: pytest.fail("no writes"))

    assert foe.fix_oid_elevations(mock_cfg, "oid_fc", dry_run=False) is None
    assert logger.error.called


def test_import_error_aborts_without_writes(monkeypatch, mock_cfg, logger):
    def raising(*a, **kw):
        raise ImportError("No module named 'pyproj'")

    monkeypatch.setattr(foe, "to_nad83_2011", raising)
    _setup_arcpy(monkeypatch, [_rec(1, 1000.0)])
    monkeypatch.setattr(foe.arcpy.da, "UpdateCursor", lambda *a: pytest.fail("no writes"))

    assert foe.fix_oid_elevations(mock_cfg, "oid_fc", dry_run=False) is None
    assert logger.error.called


def test_missing_oid_aborts(monkeypatch, mock_cfg, logger):
    monkeypatch.setattr(foe.arcpy, "Exists", lambda fc: False)
    assert foe.fix_oid_elevations(mock_cfg, "oid_fc", dry_run=True) is None
    assert logger.error.called


def test_missing_orientation_parts_fixes_z_only(monkeypatch, mock_cfg, logger):
    _patch_transform(monkeypatch)
    _, cursor = _setup_arcpy(monkeypatch, [_rec(1, 1000.0)],
                             update_rows=[_urow(1, 1000.0, heading=None)])

    foe.fix_oid_elevations(mock_cfg, "oid_fc", dry_run=False)

    row = cursor.updated[0]
    assert row[3] == pytest.approx(1026.08)
    assert row[5] == "old"  # orientation untouched when heading missing
    assert logger.warning.called


def test_service_identity_strips_aws_suffix():
    assert foe._service_identity(r"E:\proj\a26150.gdb\a26150") == ("a26150", False)
    assert foe._service_identity(r"E:\proj\a26150.gdb\a26150_aws") == ("a26150", True)


def _preflight_env(monkeypatch, image_paths, bucket="b", region="us-east-1"):
    monkeypatch.setattr(foe, "is_secured_storage_enabled", lambda cfg: False)
    monkeypatch.setattr(foe, "resolve_oid_target_bucket", lambda cfg, secured_mode: bucket)
    monkeypatch.setattr(foe, "resolve_oid_target_region", lambda cfg, secured_mode: region)
    monkeypatch.setattr(foe.arcpy, "Exists", lambda fc: True)
    monkeypatch.setattr(
        foe.arcpy.da, "SearchCursor", lambda fc, flds: FakeCursor([(p,) for p in image_paths])
    )


def test_preflight_passes_for_prepared_aws_copy(monkeypatch, mock_cfg):
    _preflight_env(monkeypatch, ["https://b.s3.us-east-1.amazonaws.com/p/img_1.jpg"])
    assert foe._preflight_republish(mock_cfg, "a_aws", is_aws_copy=True) == []


def test_preflight_flags_local_paths_in_aws_copy(monkeypatch, mock_cfg):
    _preflight_env(monkeypatch, [r"I:\panos\final\img_1.jpg", r"\\srv\share\img_2.jpg"])
    problems = foe._preflight_republish(mock_cfg, "a_aws", is_aws_copy=True)
    assert any("LOCAL" in p for p in problems)
    # A source OID legitimately carries local paths (they are rewritten on copy).
    assert foe._preflight_republish(mock_cfg, "a", is_aws_copy=False) == []


def test_preflight_flags_missing_bucket_and_bad_config(monkeypatch, mock_cfg):
    _preflight_env(monkeypatch, ["img_1.jpg"], bucket=None)
    mock_cfg.validate.side_effect = ValueError("portal.project_folder missing")
    problems = foe._preflight_republish(mock_cfg, "a", is_aws_copy=False)
    assert any("validation" in p for p in problems)
    assert any("bucket/region" in p for p in problems)


def test_republish_preflight_failure_deletes_nothing(monkeypatch, mock_cfg, logger):
    monkeypatch.setattr(foe, "_preflight_republish", lambda cfg, fc, aws: ["boom"])
    monkeypatch.setattr(
        foe, "_delete_existing_service_items",
        lambda *a: pytest.fail("must not delete when preflight fails"),
    )
    monkeypatch.setattr(
        "utils.generate_oid_service.generate_oid_service",
        lambda **kw: pytest.fail("must not publish when preflight fails"),
    )

    foe.republish_oid_service(mock_cfg, r"E:\proj\a26150.gdb\a26150")
    assert logger.error.called


def test_republish_publish_failure_reports_deleted_items(monkeypatch, mock_cfg, logger):
    monkeypatch.setattr(foe, "_preflight_republish", lambda cfg, fc, aws: [])
    monkeypatch.setattr(
        foe, "_delete_existing_service_items",
        lambda gis, name, log: [("a26150", "Feature Service", "abc123", "")],
    )

    def failing(**kw):
        raise RuntimeError("publish blew up")

    monkeypatch.setattr("utils.generate_oid_service.generate_oid_service", failing)

    with pytest.raises(RuntimeError):
        foe.republish_oid_service(mock_cfg, r"E:\proj\a26150.gdb\a26150")
    messages = " ".join(str(c.args[0]) for c in logger.error.call_args_list)
    assert "abc123" in messages and "unavailable" in messages


def test_republish_aws_copy_publishes_directly(monkeypatch, mock_cfg):
    monkeypatch.setattr(foe, "_preflight_republish", lambda cfg, fc, aws: [])
    monkeypatch.setattr(foe, "_delete_existing_service_items", lambda gis, name, log: [("a26150", "x", "1", "")])
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
    monkeypatch.setattr(foe, "_preflight_republish", lambda cfg, fc, aws: [])
    monkeypatch.setattr(foe, "_delete_existing_service_items", lambda gis, name, log: [])
    captured = {}
    monkeypatch.setattr(
        "utils.generate_oid_service.generate_oid_service",
        lambda **kw: captured.update(kw),
    )

    foe.republish_oid_service(mock_cfg, r"E:\proj\a26150.gdb\a26150")

    assert captured["service_name"] == "a26150"
    assert captured["prepare_copy"] is True            # duplicate + rewrite ImagePaths
