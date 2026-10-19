#!/usr/bin/env python3
"""
Build an OID manifest (oriented imagery table CSV) from panoramas' EXIF, plus a heading check.

The manifest lets Process 360 Workflow rebuild an OID without the images on disk (its "OID
Manifest CSV" option). Esri's Add Images reads the CSV and never opens the images.

Sources:
    --folder DIR   panoramas on disk (e.g. a project's finals); read locally, no AWS
    --s3           panoramas only in the project's S3 bucket: only the first ~32 KB of each image
                   (its metadata) is fetched, with ranged GETs under the named AWS profile
                   (aws.profile). About 3.4 GB for 106,000 images. Header files are cached in
                   --cache, so an interrupted run resumes. If any header cannot be fetched no
                   manifest is written (re-run to retry, or --allow-partial).

Heading check (rmi-rail-vision's method): frames whose recorded heading disagrees with the direction
of travel are listed in <report-dir>/heading_runs.csv and .kml. Nothing is corrected unless a
corrections file is given: copy heading_runs.csv, fill its `action` column (keep, flip, from_track,
exclude) and pass it with --corrections. Rows may also name other frame ranges. If --corrections
is heading_runs.csv itself, it is read and left as it is (the report is not rewritten).

Usage:
    # 26-150, from local finals
    python scripts/build_oid_manifest.py --config <project>/config/config.yaml \
        --folder I:/projects/RMI26150/panos/final --out <project>/oid_manifest/manifest.csv

    # 25-320, from S3 headers, applying decided corrections
    python scripts/build_oid_manifest.py --config <project>/config/config.yaml --s3 \
        --cache <project>/oid_manifest/headers --out <project>/oid_manifest/manifest.csv \
        --corrections <project>/oid_manifest/heading_corrections.csv
"""

from __future__ import annotations

import argparse
import csv
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

try:  # ArcGIS Pro's Python has arcpy; elsewhere the utils package still imports with a stand-in
    import arcpy  # noqa: F401
except ImportError:
    from unittest.mock import MagicMock
    for _esri_mod in ("arcpy", "arcgis", "arcgis.gis"):
        sys.modules.setdefault(_esri_mod, MagicMock())


def main() -> int:
    p = argparse.ArgumentParser(description="Build an OID manifest CSV from panoramas' EXIF, with a heading check.")
    p.add_argument("--config", required=True, help="Project config.yaml (schema 1.8.0).")
    p.add_argument("--project-base", help="Project folder (default: the config file's folder's parent).")
    src = p.add_mutually_exclusive_group(required=True)
    src.add_argument("--folder", help="Folder of panoramas on disk (searched recursively).")
    src.add_argument("--s3", action="store_true", help="Read headers from the project's S3 bucket and prefix.")
    p.add_argument("--cache", help="Where S3 header files are kept (required with --s3).")
    p.add_argument("--out", required=True, help="Manifest CSV to write.")
    p.add_argument("--report-dir", help="Heading check output (default: the manifest's folder).")
    p.add_argument("--corrections", help="Corrections CSV (heading_runs.csv with `action` filled in).")
    p.add_argument("--image-path", choices=["published", "local"], default="published",
                   help="ImagePath: the published S3 URL (default) or the local file (--folder only).")
    p.add_argument("--max-workers", type=int, default=16, help="Concurrent S3 header fetches.")
    p.add_argument("--allow-partial", action="store_true",
                   help="Write the manifest even if some S3 headers could not be fetched (they are left out).")
    a = p.parse_args()

    from utils.manager.config_manager import ConfigManager
    from utils.shared import heading_check as hc
    from utils.shared import oid_manifest as om
    from utils.shared.oid_storage_paths import (
        build_oid_image_path, resolve_oid_key_prefix, resolve_oid_target_bucket)

    cfg_path = Path(a.config).resolve()
    if not cfg_path.is_file():
        print(f"[ERROR] Config not found: {cfg_path}", file=sys.stderr)
        return 2
    project_base = Path(a.project_base).resolve() if a.project_base else cfg_path.parent.parent
    cfg = ConfigManager.from_file(str(cfg_path), project_base=str(project_base))
    exiftool = cfg.get("executables.exiftool.exe_path") or "exiftool"
    out = Path(a.out).resolve()
    report_dir = Path(a.report_dir).resolve() if a.report_dir else out.parent
    report_dir.mkdir(parents=True, exist_ok=True)
    runs_csv = report_dir / "heading_runs.csv"

    # Read the operator's decisions first: the report written below must never replace them.
    corrections = None
    if a.corrections:
        corr_path = Path(a.corrections).resolve()
        if not corr_path.is_file():
            print(f"[ERROR] Corrections file not found: {corr_path}", file=sys.stderr)
            return 2
        try:
            corrections = hc.load_corrections(corr_path)
        except (ValueError, KeyError) as e:
            print(f"[ERROR] Corrections file: {e}", file=sys.stderr)
            return 2

    # 1. Image metadata: local files, or headers fetched from S3
    if a.folder:
        folder = Path(a.folder).resolve()
        paths = sorted(q for q in folder.rglob("*") if q.suffix.lower() in (".jpg", ".jpeg"))
        print(f"[INFO] {len(paths):,} panoramas under {folder}")
    else:
        if a.image_path == "local":
            print("[ERROR] --image-path local needs --folder.", file=sys.stderr)
            return 2
        if not a.cache:
            print("[ERROR] --s3 needs --cache (a folder for the header files).", file=sys.stderr)
            return 2
        from utils.shared.aws_utils import get_boto3_session
        bucket, prefix = resolve_oid_target_bucket(cfg), resolve_oid_key_prefix(cfg)
        try:
            s3 = get_boto3_session(cfg).client("s3")
        except RuntimeError as e:
            print(f"[ERROR] {e}", file=sys.stderr)
            return 2
        keys = om.list_image_keys(s3, bucket, prefix)
        print(f"[INFO] {len(keys):,} panoramas in s3://{bucket}/{prefix}/; fetching headers to {a.cache}")

        def progress(n, total):
            if n % 2000 == 0 or n == total:
                print(f"[INFO]   headers {n:,}/{total:,}")

        paths, errors = om.fetch_headers(s3, bucket, keys, Path(a.cache), max_workers=a.max_workers,
                                         progress=progress)
        if errors:
            err_path = report_dir / "header_errors.csv"
            with open(err_path, "w", newline="", encoding="utf-8") as fh:
                w = csv.writer(fh)
                w.writerow(["key", "error"])
                w.writerows(sorted(errors.items()))
            if not a.allow_partial:
                print(f"[ERROR] {len(errors):,} header(s) could not be fetched: {err_path}. No manifest "
                      "written; re-run to retry (fetched headers are kept), or pass --allow-partial.",
                      file=sys.stderr)
                return 1
            print(f"[WARN] {len(errors):,} header(s) could not be fetched: {err_path}. They are left "
                  "out of the manifest (--allow-partial).")

    records, skipped = om.records_from_exif(om.read_exif(paths, exiftool=exiftool))
    print(f"[INFO] {len(records):,} images usable; {len(skipped):,} skipped")
    if skipped:
        sk_path = report_dir / "manifest_skipped.csv"
        with open(sk_path, "w", newline="", encoding="utf-8") as fh:
            w = csv.writer(fh)
            w.writerow(["name", "reason"])
            w.writerows(sorted(skipped.items()))
        print(f"[INFO]   reasons: {sk_path}")
    if not records:
        print("[ERROR] Nothing to write.", file=sys.stderr)
        return 1

    # 2. Heading check (detect; the operator decides)
    result = hc.detect([r.to_frame() for r in records])
    runs = [r for r in result.runs if r.kind == "run"]
    if a.corrections and Path(a.corrections).resolve() == runs_csv:
        print(f"[INFO] {runs_csv} is the corrections file, so it is not rewritten.")
    else:
        hc.write_runs_csv(result.runs, runs_csv)
    hc.write_runs_kml(result.runs, report_dir / "heading_runs.kml", title=f"Heading check {out.stem}")
    print(f"[INFO] Heading check: {result.judged:,} judged, {result.agrees:,} agree, {result.stopped:,} stopped; "
          f"{len(runs)} reversed run(s), {len(result.runs) - len(runs)} blip(s); rig offset "
          f"{result.rig_offset_deg} deg. Report: {runs_csv}")

    # 3. Corrections, if decided
    if corrections is not None:
        counts = hc.apply_corrections(result, corrections)
        print("[INFO] Corrections applied: " + (", ".join(f"{k} {v:,}" for k, v in counts.items() if v) or "none"))
        if counts.get("from_track_unresolved"):
            print("[WARN] Some from_track frames kept their recorded heading: no travel bearing in their "
                  "segment, or no rig offset (no frame agreed with travel).")
    elif runs:
        print("[WARN] Reversed runs found and no --corrections given: headings are written as recorded.")

    # 4. Manifest
    if a.image_path == "local":
        local = {r.name: r.source for r in records}     # names are unique (duplicates skipped)
        image_path = local.__getitem__
    else:
        image_path = lambda name: build_oid_image_path(cfg, name)  # noqa: E731
    rows = om.manifest_rows(records, result.frames, image_path)
    om.write_manifest(rows, out)
    print(f"[SUCCESS] Manifest: {out} ({len(rows):,} rows)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
