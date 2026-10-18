# =============================================================================
# 🌐 Geoid Transform Unit Tests (tests/test_geoid_transform.py)
# -----------------------------------------------------------------------------
# Purpose:             Unit tests for the ellipsoidal -> NAVD88 height conversion
# Project:             RMI 360 Imaging Workflow Python Toolbox
# Version:             1.0.0
# Author:              RMI Valuation, LLC
# Created:             2026-07-17
#
# Notes:
#   - Pure-logic tests use a mocked transformer; the real-grid tests are skipped
#     automatically when the GEOID18 grid is not installed in the local PROJ
#     data dir (they run in the ArcGIS Pro environment, which bundles it).
# =============================================================================

import sys
from unittest.mock import MagicMock

# Rich arcpy/arcgis stubs so importing the utils package succeeds without ArcGIS.
for _esri_mod in ("arcpy", "arcgis", "arcgis.gis"):
    sys.modules.setdefault(_esri_mod, MagicMock())

import numpy as np
import pytest

from datetime import date, datetime

from utils.shared.geoid_transform import (
    GeoidTransformError,
    decimal_year,
    ellipsoidal_to_orthometric,
    get_frame_transformer,
    get_geoid_transformer,
    to_nad83_2011,
)


@pytest.fixture(autouse=True)
def clear_transformer_cache():
    get_geoid_transformer.cache_clear()
    get_frame_transformer.cache_clear()
    yield
    get_geoid_transformer.cache_clear()
    get_frame_transformer.cache_clear()


def _grid_available() -> bool:
    try:
        get_geoid_transformer("GEOID18")
        return True
    except GeoidTransformError:
        return False
    finally:
        get_geoid_transformer.cache_clear()


class FakeTransformer:
    """Applies a fixed geoid separation N: H = h - N, and shifts lon/lat to prove
    the caller must discard the transformed horizontal."""

    definition = "proj=pipeline ... grids=us_noaa_g2018u0.tif ..."

    def __init__(self, separation=-25.0):
        self.separation = separation

    def transform(self, lon, lat, h):
        lon = np.asarray(lon, dtype=float)
        lat = np.asarray(lat, dtype=float)
        h = np.asarray(h, dtype=float)
        return lon + 0.001, lat + 0.001, h - self.separation


def _patch_transformer(monkeypatch, transformer):
    monkeypatch.setattr(
        "utils.shared.geoid_transform.get_geoid_transformer",
        lambda model="GEOID18": transformer,
    )


def test_unsupported_model_raises():
    with pytest.raises(GeoidTransformError, match="Unsupported geoid model"):
        get_geoid_transformer("GEOID99")


def test_missing_grid_raises_loudly(monkeypatch):
    class EmptyGroup:
        def __init__(self, *a, **kw):
            self.transformers = []

    monkeypatch.setattr("pyproj.transformer.TransformerGroup", EmptyGroup)
    with pytest.raises(GeoidTransformError, match="not available to PROJ"):
        get_geoid_transformer("GEOID18")


def test_conversion_returns_only_z_and_separation(monkeypatch):
    _patch_transformer(monkeypatch, FakeTransformer(separation=-25.0))
    h, n = ellipsoidal_to_orthometric([-93.6], [42.0], [1000.0])
    # NAVD88 height must be HIGHER than the ellipsoidal input (N negative in CONUS)
    assert h[0] == pytest.approx(1025.0)
    assert n[0] == pytest.approx(-25.0)


def test_conversion_vectorized(monkeypatch):
    _patch_transformer(monkeypatch, FakeTransformer(separation=-30.0))
    h, n = ellipsoidal_to_orthometric(
        [-93.6, -104.9, -77.0], [42.0, 39.7, 38.9], [100.0, 200.0, 300.0]
    )
    assert list(h) == pytest.approx([130.0, 230.0, 330.0])
    assert list(n) == pytest.approx([-30.0, -30.0, -30.0])


def test_out_of_coverage_raises(monkeypatch):
    class OutOfGridTransformer(FakeTransformer):
        def transform(self, lon, lat, h):
            return lon, lat, np.full_like(np.asarray(h, dtype=float), np.inf)

    _patch_transformer(monkeypatch, OutOfGridTransformer())
    with pytest.raises(GeoidTransformError, match="outside GEOID18 coverage"):
        ellipsoidal_to_orthometric([2.35], [48.85], [300.0])  # Paris


def test_noop_transform_rejected(monkeypatch):
    # A silent PROJ fallback returns near-unchanged heights (N ~ 0): must fail.
    _patch_transformer(monkeypatch, FakeTransformer(separation=0.0))
    with pytest.raises(GeoidTransformError, match="implausible geoid separation"):
        ellipsoidal_to_orthometric([-93.6], [42.0], [1000.0])


def test_positive_separation_rejected(monkeypatch):
    # Converted height going DOWN is impossible for CONUS GEOID18: must fail.
    _patch_transformer(monkeypatch, FakeTransformer(separation=10.0))
    with pytest.raises(GeoidTransformError, match="implausible geoid separation"):
        ellipsoidal_to_orthometric([-93.6], [42.0], [1000.0])


def test_excessive_separation_rejected(monkeypatch):
    _patch_transformer(monkeypatch, FakeTransformer(separation=-60.0))
    with pytest.raises(GeoidTransformError, match="implausible geoid separation"):
        ellipsoidal_to_orthometric([-93.6], [42.0], [1000.0])


# ---------------------------------------------------------------------------
# Real-grid tests (require the GEOID18 grid; run in the ArcGIS Pro Python env)
# ---------------------------------------------------------------------------

requires_grid = pytest.mark.skipif(
    not _grid_available(), reason="GEOID18 grid not installed in PROJ data dir"
)


@requires_grid
def test_transformer_pinned_to_geoid18_grid():
    tf = get_geoid_transformer("GEOID18")
    assert "us_noaa_g2018u0" in tf.definition


@requires_grid
@pytest.mark.parametrize(
    "lon, lat, expected_n",
    [
        # GEOID18 separations sampled from the NGS us_noaa_g2018u0 grid.
        (-93.63, 42.03, -29.3587),   # Ames, IA
        (-104.99, 39.74, -17.1129),  # Denver, CO
        (-77.03, 38.90, -32.0739),   # Washington, DC
        (-122.33, 47.60, -23.6723),  # Seattle, WA
    ],
)
def test_known_point_separations(lon, lat, expected_n):
    h_ellipsoid = 100.0
    h, n = ellipsoidal_to_orthometric([lon], [lat], [h_ellipsoid])
    # H = h - N within a few centimeters
    assert h[0] == pytest.approx(h_ellipsoid - expected_n, abs=0.03)
    assert n[0] == pytest.approx(expected_n, abs=0.03)
    # Magnitude sanity: NAVD88 must be 8-33 m HIGHER than ellipsoidal in CONUS
    assert 8.0 < (h[0] - h_ellipsoid) < 40.0


@requires_grid
def test_real_out_of_coverage_raises():
    with pytest.raises(GeoidTransformError, match="outside GEOID18 coverage"):
        ellipsoidal_to_orthometric([2.35], [48.85], [300.0])  # Paris, France


# ---------------------------------------------------------------------------
# Reference frame step: source frame -> NAD83(2011) (pure logic, mocked PROJ)
# ---------------------------------------------------------------------------

class FakeFrameTransformer:
    """4D transform applying a fixed height change; records the epochs passed."""

    definition = "proj=pipeline ... proj=helmert ... t_epoch=2010 ..."

    def __init__(self, shift=1.08):
        self.shift = shift
        self.epochs = None

    def transform(self, lon, lat, h, t):
        self.epochs = np.asarray(t, dtype=float)
        h = np.asarray(h, dtype=float)
        return lon, lat, h + self.shift, t


def _patch_frame(monkeypatch, transformer):
    monkeypatch.setattr(
        "utils.shared.geoid_transform.get_frame_transformer", lambda frame: transformer
    )


def test_nad83_source_is_unchanged_without_proj(monkeypatch):
    monkeypatch.setattr(
        "pyproj.transformer.TransformerGroup",
        lambda *a, **kw: pytest.fail("NAD83_2011 needs no PROJ operation"),
    )
    h, shift = to_nad83_2011([-87.9], [41.8], [200.0], "NAD83_2011", 2026.05)
    assert h[0] == 200.0 and shift[0] == 0.0


def test_unknown_frame_raises():
    with pytest.raises(GeoidTransformError, match="Unsupported source_frame"):
        get_frame_transformer("GDA2020")


def test_frame_transformer_refuses_operation_without_helmert(monkeypatch):
    class PlaceholderOnly:
        def __init__(self, *a, **kw):
            placeholder = MagicMock()
            placeholder.definition = "proj=noop"   # e.g. a null/ballpark operation
            self.transformers = [placeholder]

    monkeypatch.setattr("pyproj.transformer.TransformerGroup", PlaceholderOnly)
    with pytest.raises(GeoidTransformError, match="No time-dependent"):
        get_frame_transformer("ITRF2014")


def test_frame_shift_applied_with_per_point_epochs(monkeypatch):
    tf = FakeFrameTransformer(shift=1.08)
    _patch_frame(monkeypatch, tf)
    h, shift = to_nad83_2011([-87.9, -89.4], [41.8, 40.1], [200.0, 210.0], "ITRF2014",
                             [2025.5, 2026.05])
    assert list(h) == pytest.approx([201.08, 211.08])
    assert list(shift) == pytest.approx([1.08, 1.08])
    assert list(tf.epochs) == pytest.approx([2025.5, 2026.05])


def test_scalar_epoch_broadcasts(monkeypatch):
    tf = FakeFrameTransformer()
    _patch_frame(monkeypatch, tf)
    to_nad83_2011([-87.9, -89.4], [41.8, 40.1], [200.0, 210.0], "ITRF2014", 2026.05)
    assert list(tf.epochs) == pytest.approx([2026.05, 2026.05])


@pytest.mark.parametrize("bad_shift", [0.0, 0.05, -0.02, 3.5, -4.0, np.nan, np.inf])
def test_implausible_frame_shift_rejected(monkeypatch, bad_shift):
    # Near zero = a no-op operation slipped through; > 3 m or non-finite = broken.
    _patch_frame(monkeypatch, FakeFrameTransformer(shift=bad_shift))
    with pytest.raises(GeoidTransformError, match="implausible ITRF2014 -> NAD83"):
        to_nad83_2011([-87.9], [41.8], [200.0], "ITRF2014", 2026.05)


def test_decimal_year():
    assert decimal_year(datetime(2026, 1, 1)) == pytest.approx(2026.0)
    assert decimal_year(datetime(2026, 7, 2, 12)) == pytest.approx(2026.5, abs=0.002)
    assert decimal_year(date(2024, 12, 31)) == pytest.approx(2024.997, abs=0.001)
    with pytest.raises(TypeError):
        decimal_year("2026-01-01")


# ---------------------------------------------------------------------------
# Real PROJ frame tests (pyproj ships the Helmert operations; no grid needed)
# ---------------------------------------------------------------------------

def _frame_ops_available() -> bool:
    try:
        get_frame_transformer("ITRF2014")
        return True
    except (GeoidTransformError, ImportError):
        return False
    finally:
        get_frame_transformer.cache_clear()


requires_frame_ops = pytest.mark.skipif(
    not _frame_ops_available(), reason="ITRF -> NAD83(2011) operation not available in PROJ"
)


@requires_frame_ops
def test_frame_transformer_pinned_to_time_dependent_helmert():
    tf = get_frame_transformer("ITRF2014")
    assert "helmert" in tf.definition and "t_epoch" in tf.definition


@requires_frame_ops
@pytest.mark.parametrize(
    "lon, lat, expected_dh",
    [
        (-87.90, 41.80, 1.079),      # Chicago Sub, IL
        (-94.3426, 39.1710, 1.065),  # Kansas City area
        (-81.46, 30.65, 1.472),      # Fernandina Beach, FL (gw-360-oid reference)
    ],
)
def test_real_itrf2014_shift_at_capture_locations(lon, lat, expected_dh):
    _, shift = to_nad83_2011([lon], [lat], [200.0], "ITRF2014", 2026.05)
    assert shift[0] == pytest.approx(expected_dh, abs=0.01)


@requires_frame_ops
def test_wgs84_is_treated_as_itrf2020_not_the_noop_placeholder():
    # PROJ's own WGS 84 -> NAD83(2011) operation is a zero-shift placeholder; the
    # WGS84 source frame must still produce the real ~1.08 m shift in Illinois.
    from pyproj.transformer import TransformerGroup

    placeholder = TransformerGroup(4979, 6319, always_xy=True).transformers[0]
    _, _, h_placeholder = placeholder.transform(-87.9, 41.8, 200.0)
    assert abs(h_placeholder - 200.0) < 0.01          # the trap really exists

    _, shift_wgs = to_nad83_2011([-87.9], [41.8], [200.0], "WGS84", 2026.05)
    _, shift_20 = to_nad83_2011([-87.9], [41.8], [200.0], "ITRF2020", 2026.05)
    assert shift_wgs[0] == pytest.approx(shift_20[0])
    assert shift_wgs[0] == pytest.approx(1.08, abs=0.01)


@requires_frame_ops
def test_itrf2014_and_itrf2020_agree_to_millimetres():
    _, s14 = to_nad83_2011([-87.9], [41.8], [200.0], "ITRF2014", 2026.05)
    _, s20 = to_nad83_2011([-87.9], [41.8], [200.0], "ITRF2020", 2026.05)
    assert abs(s14[0] - s20[0]) < 0.005


@requires_grid
@requires_frame_ops
def test_end_to_end_kc_sample():
    # ITRF2014 ellipsoidal -> NAD83(2011) -> NAVD88 is ~1.065 m higher than the
    # GEOID18-only result at the Kansas City sample point.
    lon, lat, h = -94.342593, 39.170959, 160.0
    geoid_only, _ = ellipsoidal_to_orthometric([lon], [lat], [h])
    h_nad, _ = to_nad83_2011([lon], [lat], [h], "ITRF2014", 2026.05)
    full, _ = ellipsoidal_to_orthometric([lon], [lat], h_nad)
    assert full[0] - geoid_only[0] == pytest.approx(1.065, abs=0.01)
    assert full[0] == pytest.approx(193.70, abs=0.02)
