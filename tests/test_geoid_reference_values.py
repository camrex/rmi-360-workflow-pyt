# =============================================================================
# 🧭 Geoid Conversion Reference-Value Tests (tests/test_geoid_reference_values.py)
# -----------------------------------------------------------------------------
# Purpose:             Checks the camera-height conversion against values computed
#                      independently by NOAA/NGS tools — not by PROJ
# Project:             RMI 360 Imaging Workflow Python Toolbox
# Version:             1.0.0
# Author:              RMI Valuation, LLC
# Created:             2026-10-01
#
# Why:
#   The other geoid tests largely compare PROJ against PROJ. These pin results
#   from NGS's own implementations, so a different PROJ operation being picked
#   (e.g. after an ArcGIS Pro / PROJ upgrade), a wrong EPSG code, a sign or epoch
#   error, or a skipped step shows up as a numeric mismatch.
#
# Reference values (generated 2026-10-01):
#   - Frame shift dh = h[NAD83(2011)] - h[ITRF]: NGS HTDP 3.6.0 (April 7, 2025),
#     official Windows build from https://geodesy.noaa.gov/TOOLS/Htdp/HTDP-download.zip
#     Main menu 4 (transform positions), input frame 25 = ITRF2014 or
#     26 = ITRF2020, output frame 1 = NAD_83(2011/CORS96/2007), input and output
#     dates equal (decimal year), positions via option 3 (LAT,LON-west,EHT=200 m).
#     HTDP prints heights to 1 mm.
#   - Geoid height N: NGS GEOID18 web service (model 14),
#     https://geodesy.noaa.gov/api/geoid/ght?lat=<lat>&lon=<lon>&model=14
#     (reported to 2-3 decimals).
#   - Expected NAVD88 height for an ITRF ellipsoidal height h:
#     H = h + dh - N.
#
# Notes:
#   - Requires the GEOID18 grid and PROJ's ITRF -> NAD83(2011) operations
#     (both present in ArcGIS Pro's Python); skipped otherwise.
# =============================================================================

import sys
from unittest.mock import MagicMock

for _esri_mod in ("arcpy", "arcgis", "arcgis.gis"):
    sys.modules.setdefault(_esri_mod, MagicMock())

import pytest

from utils.shared.geoid_transform import (
    GeoidTransformError,
    ellipsoidal_to_orthometric,
    get_frame_transformer,
    get_geoid_transformer,
    to_nad83_2011,
)

H_IN = 200.0  # ellipsoidal height used for all HTDP runs (m)

# name, lat, lon (east-positive), NGS GEOID18 N (m)
POINTS = [
    ("Chicago Sub, IL", 41.80, -87.90, -33.350),
    ("Central IL", 40.10, -89.40, -32.503),
    ("Kansas City area", 39.170959, -94.342593, -32.637),
    ("Denver, CO", 39.74, -104.99, -17.113),
    ("Fernandina Beach, FL", 30.65, -81.46, -28.494),
]

# HTDP 3.6.0 output heights for EHT = 200.000 m, keyed by (frame, epoch).
HTDP_NAD83_HEIGHT = {
    ("ITRF2014", 2026.05): [201.079, 201.110, 201.065, 200.860, 201.472],
    ("ITRF2014", 2024.5): [201.080, 201.111, 201.066, 200.862, 201.473],
    ("ITRF2020", 2026.05): [201.080, 201.111, 201.066, 200.861, 201.473],
}

# HTDP rounds to 1 mm; the GEOID18 service reports N to 2-3 decimals.
DH_TOL = 0.002
N_TOL = 0.006
H_TOL = DH_TOL + N_TOL


def _available() -> bool:
    try:
        get_geoid_transformer("GEOID18")
        get_frame_transformer("ITRF2014")
        return True
    except (GeoidTransformError, ImportError):
        return False
    finally:
        get_geoid_transformer.cache_clear()
        get_frame_transformer.cache_clear()


pytestmark = pytest.mark.skipif(
    not _available(), reason="GEOID18 grid or ITRF -> NAD83(2011) operations not available"
)

CASES = [
    pytest.param(frame, epoch, i, id=f"{frame}@{epoch}-{POINTS[i][0]}")
    for (frame, epoch) in HTDP_NAD83_HEIGHT
    for i in range(len(POINTS))
]


@pytest.mark.parametrize("frame, epoch, i", CASES)
def test_frame_shift_matches_ngs_htdp(frame, epoch, i):
    _, lat, lon, _ = POINTS[i]
    expected_dh = HTDP_NAD83_HEIGHT[(frame, epoch)][i] - H_IN
    _, dh = to_nad83_2011([lon], [lat], [H_IN], frame, epoch)
    assert dh[0] == pytest.approx(expected_dh, abs=DH_TOL)


@pytest.mark.parametrize("i", range(len(POINTS)), ids=[p[0] for p in POINTS])
def test_geoid_separation_matches_ngs_service(i):
    _, lat, lon, expected_n = POINTS[i]
    _, n = ellipsoidal_to_orthometric([lon], [lat], [H_IN])
    assert n[0] == pytest.approx(expected_n, abs=N_TOL)


@pytest.mark.parametrize("frame, epoch, i", CASES)
def test_full_conversion_matches_ngs(frame, epoch, i):
    """ITRF ellipsoidal -> NAVD88 through the same two calls the pipeline makes,
    against H = h + dh(HTDP) - N(NGS GEOID18)."""
    _, lat, lon, ngs_n = POINTS[i]
    expected_h = HTDP_NAD83_HEIGHT[(frame, epoch)][i] - ngs_n
    h_nad83, _ = to_nad83_2011([lon], [lat], [H_IN], frame, epoch)
    h_navd88, _ = ellipsoidal_to_orthometric([lon], [lat], h_nad83)
    assert h_navd88[0] == pytest.approx(expected_h, abs=H_TOL)


def test_skipping_the_frame_step_is_detectably_wrong():
    """Guards the original bug: GEOID18 alone (no frame shift) lands ~1.08 m low
    in Illinois — far outside tolerance of the NGS reference."""
    _, lat, lon, ngs_n = POINTS[0]
    expected_h = HTDP_NAD83_HEIGHT[("ITRF2014", 2026.05)][0] - ngs_n
    geoid_only, _ = ellipsoidal_to_orthometric([lon], [lat], [H_IN])
    assert expected_h - geoid_only[0] == pytest.approx(1.079, abs=0.01)
