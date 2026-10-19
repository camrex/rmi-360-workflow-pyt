"""Reel/frame parsing from image paths: original capture names and renamed finals.

A rebuild from finals (manifest mode) only has final names, e.g.
RMI26150_UP_G0.109_20260625T155157Z_RL0002_FR000587.jpg.
"""

import sys
from unittest.mock import MagicMock

for _esri_mod in ("arcpy", "arcgis", "arcgis.gis"):
    sys.modules.setdefault(_esri_mod, MagicMock())

import pytest

import utils.calculate_oid_attributes as coa

FINAL = r"Z:\x\RMI26150_UP_G0.109_20260625T155157Z_RL0002_FR000587.jpg"
ORIGINAL = r"Z:\proj\panos\original\reel_0002\pano_reel_0002_20260625-150102_26-150_000587.jpg"


@pytest.mark.parametrize("path", [FINAL, ORIGINAL, FINAL.replace(".jpg", ".JPG"), FINAL.replace(".jpg", ".jpeg")])
def test_frame_from_original_and_final_names(path):
    assert coa.extract_frame_from_filename(path) == "000587"


def test_reel_from_final_name():
    assert coa.extract_reel_from_path(FINAL) == "0002"


@pytest.mark.parametrize("name", ["x_FR00587.jpg", "x_FRAME000587.jpg", "x_000587.png", "x000587.jpg"])
def test_frame_not_matched(name):
    assert coa.extract_frame_from_filename(name) is None
