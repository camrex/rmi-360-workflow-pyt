"""Unit tests for utils/corridor/units.py — WKID-aware threshold math, linear-unit
parsing, and the arcpy-free anchor-reset thinning core. No arcpy required."""

import math

import pytest

from utils.corridor.units import (
    anchor_reset_keep,
    linear_unit_to_meters,
    meters_per_unit,
    threshold_to_data_units,
)

US_SURVEY_FOOT = 0.3048006096012192


def test_meters_per_unit_override_wins():
    assert meters_per_unit(wkid=6455, override=1.0) == 1.0


def test_meters_per_unit_6455_us_survey_feet():
    # 6455 = NAD83(2011) IL SP East, US survey feet
    assert meters_per_unit(wkid=6455) == pytest.approx(US_SURVEY_FOOT, rel=1e-9)


def test_threshold_5m_to_us_survey_feet_is_16_4042():
    # The hard-won rule: 5 m at WKID 6455 = 16.4042 ft (NOT 16.404).
    val = threshold_to_data_units(5.0, wkid=6455)
    assert val == pytest.approx(16.4042, abs=1e-3)


def test_threshold_with_explicit_mpu():
    val = threshold_to_data_units(5.0, meters_per_unit_override=US_SURVEY_FOOT)
    assert val == pytest.approx(16.4042, abs=1e-3)


def test_threshold_meters_crs_identity():
    # WKID 26914 (UTM 14N) is meters: 5 m -> 5 units.
    assert threshold_to_data_units(5.0, wkid=26914) == pytest.approx(5.0)


def test_linear_unit_to_meters_variants():
    assert linear_unit_to_meters("5 Meters") == pytest.approx(5.0)
    assert linear_unit_to_meters("16.4042 Feet") == pytest.approx(16.4042 * 0.3048)
    assert linear_unit_to_meters("1.5 Meters") == pytest.approx(1.5)
    # bare number treated as meters
    assert linear_unit_to_meters("5") == pytest.approx(5.0)


def test_linear_unit_unknown_raises():
    with pytest.raises(ValueError):
        linear_unit_to_meters("5 Furlongs")


def test_anchor_reset_keep_basic_spacing():
    # Points 0,1,2,...10 units apart on a line; threshold 5 -> keep every >=5.
    pts = [(float(i), 0.0) for i in range(0, 11)]  # 0..10
    keep = anchor_reset_keep(pts, eff_threshold=5.0)
    # anchor=0 kept; 1-4 dropped (<5); 5 kept (>=5); 6-9 dropped; 10 kept.
    assert keep[0] == 1
    assert keep[5] == 1
    assert keep[10] == 1
    assert sum(keep) == 3
    assert keep[1:5] == [0, 0, 0, 0]


def test_anchor_reset_resets_from_kept_anchor():
    # Cluster then a clear point: anchor distance measured from last KEPT point.
    pts = [(0, 0), (3, 0), (4, 0), (9, 0), (12, 0)]
    keep = anchor_reset_keep(pts, eff_threshold=5.0)
    # 0 keep; 3 drop(<5); 4 drop(<5); 9 keep(>=5 from 0); 12 drop(<5 from 9)
    assert keep == [1, 0, 0, 1, 0]


def test_anchor_reset_empty():
    assert anchor_reset_keep([], 5.0) == []
