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

from utils.shared.geoid_transform import (
    GeoidTransformError,
    ellipsoidal_to_orthometric,
    get_geoid_transformer,
)


@pytest.fixture(autouse=True)
def clear_transformer_cache():
    get_geoid_transformer.cache_clear()
    yield
    get_geoid_transformer.cache_clear()


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
