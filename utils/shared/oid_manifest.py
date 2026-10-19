# =============================================================================
# 🧾 OID Manifest Builder (utils/shared/oid_manifest.py)
# -----------------------------------------------------------------------------
# Purpose:             Build an oriented-imagery-table CSV from the panoramas' EXIF, so an OID can
#                      be (re)built without the images on disk
# Project:             RMI 360 Imaging Workflow Python Toolbox
# Version:             1.0.0
# Author:              RMI Valuation, LLC
# Created:             2026-10-19
# Last Updated:        2026-10-19
#
# Description:
#   Esri's Add Images To Oriented Imagery Dataset accepts a CSV in the oriented imagery table
#   schema and never opens the images. When it reads images itself it takes only: position (GPS
#   lat/lon), Z (GPSAltitude, the raw ellipsoidal height), AcquisitionDate (DateTimeOriginal),
#   CameraHeading (GPSImgDirection), Name and ImagePath, plus fixed 360 defaults. This module
#   reads those tags with exiftool and writes the same values, rounded the way Esri rounds them
#   (Z and heading to 3 decimals), so a CSV build matches an image build (verified 2026-10-19).
#   Calculate OID Attributes then converts Z (frame shift + GEOID18) exactly as for an image build.
#
#   The EXIF/XMP block sits in the first few KB of each JPEG (about 6.7 KB on 26-150 finals), so
#   panoramas that are only in S3 can be read from a ranged GET of the first 32 KB
#   (``fetch_headers``), widened automatically if the image data marker is not inside it.
#
# File Location:        /utils/shared/oid_manifest.py
# Called By:            scripts/build_oid_manifest.py
# Int. Dependencies:    utils/shared/heading_check
# Ext. Dependencies:    exiftool (on PATH or configured), botocore (S3 fetch only)
# =============================================================================
from __future__ import annotations

import concurrent.futures as cf
import csv
import datetime as dt
import json
import re
import subprocess
import tempfile
from dataclasses import dataclass
from pathlib import Path
from typing import Callable, Dict, Iterable, List, Optional, Sequence, Tuple

from utils.shared.heading_check import Frame

EXIF_TAGS = (
    "-GPS:GPSLatitude", "-GPS:GPSLatitudeRef", "-GPS:GPSLongitude", "-GPS:GPSLongitudeRef",
    "-GPS:GPSAltitude", "-GPS:GPSAltitudeRef", "-GPS:GPSImgDirection", "-ExifIFD:DateTimeOriginal",
)
MANIFEST_COLUMNS = (
    "ImagePath", "Name", "X", "Y", "Z", "SRS", "AcquisitionDate", "CameraHeading",
    "HorizontalFieldOfView", "VerticalFieldOfView", "OrientedImageryType", "HeadingSource",
)
JPEG_SOS = b"\xff\xda"        # start of the image data: everything before it is metadata
HEADER_BYTES = 32 * 1024
HEADER_BYTES_MAX = 512 * 1024

_FINAL_RE = re.compile(r"_RL(\d{4})_FR(\d{6})\.jpe?g$", re.IGNORECASE)
_ORIGINAL_RE = re.compile(r"reel_(\d{4})_.*_(\d{6})\.jpe?g$", re.IGNORECASE)


def parse_reel_frame(name: str) -> Optional[Tuple[str, int]]:
    """(reel, frame) from a final name (..._RL0002_FR000587.jpg) or an original capture name."""
    m = _FINAL_RE.search(name) or _ORIGINAL_RE.search(name)
    return (m.group(1), int(m.group(2))) if m else None


@dataclass
class ImageRecord:
    """What the manifest needs from one image. ``z`` is the raw EXIF altitude (ellipsoidal)."""
    name: str
    lon: float
    lat: float
    z: float
    acquired: dt.datetime
    heading: float
    reel: str
    frame: int
    source: str = ""        # the file exiftool read (local image or cached S3 header)

    def to_frame(self) -> Frame:
        return Frame(name=self.name, day=self.acquired.date().isoformat(), reel=self.reel, frame=self.frame,
                     lon=self.lon, lat=self.lat, heading=self.heading)


def read_exif(paths: Sequence[Path], exiftool: str = "exiftool", chunk: int = 2000) -> List[dict]:
    """Run exiftool over ``paths`` (in chunks, via an argument file) and return its JSON records."""
    out: List[dict] = []
    for i in range(0, len(paths), chunk):
        part = paths[i:i + chunk]
        with tempfile.NamedTemporaryFile("w", suffix=".args", delete=False, encoding="utf-8") as fh:
            fh.write("\n".join(str(p) for p in part))
            argfile = fh.name
        try:
            proc = subprocess.run([exiftool, "-json", "-n", "-G1", "-charset", "filename=utf8", *EXIF_TAGS,
                                   "-@", argfile], capture_output=True, text=True, encoding="utf-8")
            if proc.returncode not in (0, 1) or not proc.stdout.strip():   # 1 = some files had warnings
                raise RuntimeError(f"exiftool failed (exit {proc.returncode}): {proc.stderr.strip()[:500]}")
            out.extend(json.loads(proc.stdout))
        finally:
            Path(argfile).unlink(missing_ok=True)
    return out


def record_from_exif(e: dict) -> Tuple[Optional[ImageRecord], str]:
    """(record, "") or (None, reason) for one exiftool JSON record."""
    name = Path(e.get("SourceFile", "")).name
    rf = parse_reel_frame(name)
    if rf is None:
        return None, "name has no reel/frame"
    try:
        lat, lon = float(e["GPS:GPSLatitude"]), float(e["GPS:GPSLongitude"])
        alt = float(e["GPS:GPSAltitude"])
    except (KeyError, TypeError, ValueError):
        return None, "no GPS position/altitude"
    if e.get("GPS:GPSLatitudeRef") == "S":
        lat = -abs(lat)
    if e.get("GPS:GPSLongitudeRef") == "W":
        lon = -abs(lon)
    if e.get("GPS:GPSAltitudeRef") == 1:
        alt = -abs(alt)
    try:
        acquired = dt.datetime.strptime(str(e["ExifIFD:DateTimeOriginal"]), "%Y:%m:%d %H:%M:%S")
    except (KeyError, ValueError):
        return None, "no DateTimeOriginal"
    try:
        heading = float(e["GPS:GPSImgDirection"])
    except (KeyError, TypeError, ValueError):
        return None, "no GPSImgDirection"
    return ImageRecord(name=name, lon=lon, lat=lat, z=alt, acquired=acquired, heading=heading,
                       reel=rf[0], frame=rf[1], source=str(e.get("SourceFile", ""))), ""


def records_from_exif(exif: Iterable[dict]) -> Tuple[List[ImageRecord], Dict[str, str]]:
    """Records, plus {name or source: reason} for images that cannot go in the manifest.

    Name is the OID's key, so a second image with the same name is skipped (reported by its
    full source path) rather than given the first one's row.
    """
    recs: List[ImageRecord] = []
    skipped: Dict[str, str] = {}
    first: Dict[str, str] = {}
    for e in exif:
        rec, why = record_from_exif(e)
        if rec is None:
            skipped[Path(e.get("SourceFile", "")).name] = why
        elif rec.name in first:
            skipped[rec.source] = f"duplicate name (also {first[rec.name]})"
        else:
            first[rec.name] = rec.source
            recs.append(rec)
    return recs, skipped


def manifest_rows(records: Sequence[ImageRecord], frames: Sequence[Frame],
                  image_path: Callable[[str], str]) -> List[dict]:
    """Manifest rows from records and their (possibly corrected) heading-check frames.

    ``frames`` carries each image's final heading, heading source and exclusion (from
    ``heading_check.apply_corrections``); excluded frames are left out.
    """
    by_name = {f.name: f for f in frames}
    rows = []
    for r in sorted(records, key=lambda r: (r.acquired.date(), r.reel, r.frame)):
        f = by_name.get(r.name)
        if f is not None and f.excluded:
            continue
        heading = f.heading if f is not None else r.heading
        rows.append({
            "ImagePath": image_path(r.name), "Name": r.name,
            "X": r.lon, "Y": r.lat, "Z": round(r.z, 3), "SRS": "4326",
            "AcquisitionDate": r.acquired.strftime("%Y-%m-%d %H:%M:%S"),
            "CameraHeading": round(heading % 360.0, 3),
            "HorizontalFieldOfView": 360, "VerticalFieldOfView": 180, "OrientedImageryType": "360",
            "HeadingSource": f.heading_source if f is not None else "exif",
        })
    return rows


def write_manifest(rows: Sequence[dict], path: Path) -> Path:
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    with open(path, "w", newline="", encoding="utf-8") as fh:
        w = csv.DictWriter(fh, fieldnames=list(MANIFEST_COLUMNS))
        w.writeheader()
        w.writerows(rows)
    return path


# --- panoramas that are only in S3 ------------------------------------------------------------

def list_image_keys(s3, bucket: str, prefix: str) -> List[str]:
    """Every .jpg/.jpeg key under ``prefix/`` (ListObjectsV2, paginated)."""
    keys: List[str] = []
    pfx = prefix.strip("/") + "/" if prefix.strip("/") else ""
    for page in s3.get_paginator("list_objects_v2").paginate(Bucket=bucket, Prefix=pfx):
        for obj in page.get("Contents", []) or []:
            if obj["Key"].lower().endswith((".jpg", ".jpeg")):
                keys.append(obj["Key"])
    return keys


def header_cache_path(dest_dir: Path, key: str) -> Path:
    """Where ``key``'s header is cached: the key's own path under ``dest_dir``, so two keys with
    the same file name never share a file."""
    return Path(dest_dir).joinpath(*[p for p in key.split("/") if p not in ("", ".", "..")])


def _fetch_one(s3, bucket: str, key: str, dest: Path, nbytes: int) -> Tuple[str, Optional[str]]:
    """Write the first bytes of ``key`` (through the end of the metadata) to ``dest``."""
    if dest.exists() and JPEG_SOS in dest.read_bytes():
        return key, None                                            # resume: already fetched
    size = nbytes
    while True:
        try:
            body = s3.get_object(Bucket=bucket, Key=key, Range=f"bytes=0-{size - 1}")["Body"].read()
        except Exception as e:  # noqa: BLE001 — reported per key
            return key, f"{type(e).__name__}: {e}"
        if JPEG_SOS in body or len(body) < size or size >= HEADER_BYTES_MAX:
            if JPEG_SOS not in body:
                return key, "metadata not found within the fetched bytes"
            dest.parent.mkdir(parents=True, exist_ok=True)
            dest.write_bytes(body)
            return key, None
        size *= 4


def fetch_headers(s3, bucket: str, keys: Sequence[str], dest_dir: Path, nbytes: int = HEADER_BYTES,
                  max_workers: int = 16, progress: Optional[Callable[[int, int], None]] = None
                  ) -> Tuple[List[Path], Dict[str, str]]:
    """Fetch the metadata header of each key into ``dest_dir`` (at the key's path). Resumable.

    Returns (local header paths, {key: error}). Ranged GETs only: about 32 KB per image.
    """
    dest_dir = Path(dest_dir)
    dest_dir.mkdir(parents=True, exist_ok=True)
    paths: List[Path] = []
    errors: Dict[str, str] = {}
    with cf.ThreadPoolExecutor(max_workers=max_workers) as ex:
        futs = {ex.submit(_fetch_one, s3, bucket, k, header_cache_path(dest_dir, k), nbytes): k for k in keys}
        for n, fut in enumerate(cf.as_completed(futs), start=1):
            key, err = fut.result()
            if err:
                errors[key] = err
            else:
                paths.append(header_cache_path(dest_dir, key))
            if progress:
                progress(n, len(keys))
    return sorted(paths), errors
