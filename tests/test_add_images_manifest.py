"""Tests for manifest-driven Add Images helpers (pre-thin convergence point).
Matches by filename (robust because storage folders != subdivisions). Stubs arcpy
so the production module imports without ArcGIS."""

import sys
import types
from pathlib import Path

# Lightweight arcpy stub so importing the production module succeeds in CI.
arcpy_stub = types.ModuleType("arcpy")
arcpy_stub.Exists = lambda *_a, **_kw: False
arcpy_stub.oi = types.ModuleType("arcpy.oi")
arcpy_stub.oi.AddImagesToOrientedImageryDataset = lambda **_kw: None
sys.modules.setdefault("arcpy", arcpy_stub)
sys.modules.setdefault("arcpy.oi", arcpy_stub.oi)

from utils.add_images_to_oid_fc import _filter_files_by_manifest, load_manifest_keys  # noqa: E402


def _write_manifest(tmp_path, rows, header="Path,Name,mp_pre,track,sub_order"):
    p = tmp_path / "manifest.csv"
    lines = [header] + rows
    p.write_text("\n".join(lines), encoding="utf-8")
    return p


def test_load_manifest_keys_names_and_paths(tmp_path):
    manifest = _write_manifest(
        tmp_path,
        [
            "C:/imgs/chicago/pano_reel_0001_20260101-080000_p_000001.jpg,pano_reel_0001_20260101-080000_p_000001.jpg,H,,1",
            "C:/imgs/geneva/pano_reel_0001_20260101-080000_p_000005.jpg,pano_reel_0001_20260101-080000_p_000005.jpg,H,,2",
        ],
    )
    names, paths = load_manifest_keys(str(manifest))
    assert "pano_reel_0001_20260101-080000_p_000001.jpg" in names
    assert "pano_reel_0001_20260101-080000_p_000005.jpg" in names
    assert any("chicago" in p for p in paths)


def test_filter_files_by_manifest_matches_by_name(tmp_path):
    # Files live in DIFFERENT folders than the manifest Path — name match must win.
    names = {"pano_reel_0001_20260101-080000_p_000001.jpg",
             "pano_reel_0001_20260101-080000_p_000005.jpg"}
    paths = set()
    on_disk = [
        Path("D:/local/final/H/pano_reel_0001_20260101-080000_p_000001.jpg"),
        Path("D:/local/final/H/pano_reel_0001_20260101-080000_p_000005.jpg"),
        Path("D:/local/final/H/pano_reel_0001_20260101-080000_p_000099.jpg"),  # not kept
    ]
    kept = _filter_files_by_manifest(on_disk, names, paths)
    kept_names = {f.name for f in kept}
    assert kept_names == names
    assert "pano_reel_0001_20260101-080000_p_000099.jpg" not in kept_names


def test_filter_is_case_insensitive_on_name(tmp_path):
    names = {"pano_reel_0001_20260101-080000_p_000001.jpg"}
    on_disk = [Path("D:/x/PANO_REEL_0001_20260101-080000_P_000001.JPG")]
    kept = _filter_files_by_manifest(on_disk, names, set())
    assert len(kept) == 1


def test_load_manifest_handles_bom_and_casing(tmp_path):
    # Header casing tolerance + utf-8-sig BOM.
    p = tmp_path / "m.csv"
    p.write_text("﻿path,NAME\nC:/a/x.jpg,x.jpg\n", encoding="utf-8")
    names, paths = load_manifest_keys(str(p))
    assert "x.jpg" in names
