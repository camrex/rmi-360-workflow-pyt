#!/usr/bin/env python
# -*- coding: utf-8 -*-

from __future__ import annotations
from pathlib import Path
import argparse
import sys
import traceback

# Ensure repo root (which contains `utils/`) is on sys.path no matter where we run from
REPO_ROOT = Path(__file__).resolve().parents[1]  # one level up from /scripts
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

# --- skip arcpy imports if ArcGIS not installed ---
import builtins
if 'arcpy' not in sys.modules:
    import types
    sys.modules['arcpy'] = types.SimpleNamespace(
        env=types.SimpleNamespace(workspace=None),
        Exists=lambda *a, **k: False,
    )


def main() -> int:
    parser = argparse.ArgumentParser(description="Upload RAW Mosaic reels to S3 (rmi-360-raw).")
    parser.add_argument("--config", required=True, help="Path to config.yaml (can be minimal).")
    parser.add_argument("--folder", required=True, help="Local folder containing reels or a single reel folder.")
    parser.add_argument("--prefix", required=True, help="S3 prefix under aws.s3_bucket_raw (e.g., RMI25320/reels/).")
    parser.add_argument("--project-base", help="Base folder for logs (defaults to config's parent).")
    parser.add_argument("--dry-run", action="store_true", help="Discover and list targets, but do not upload.")
    args = parser.parse_args()

    try:
        cfg_path = Path(args.config).resolve()
        folder = Path(args.folder).resolve()
        if not folder.exists():
            print(f"[ERROR] Local folder not found: {folder}", file=sys.stderr)
            return 2

        # Lazy import to avoid arcpy touching anything
        from utils.manager.config_manager import ConfigManager
        from scripts.upload_helpers import collect_upload_tasks, RAW_EXTS, upload_raw_reels

        # Determine a reasonable project_base (for logs) if not provided
        project_base = Path(args.project_base).resolve() if args.project_base else cfg_path.parent
        print(f"[INFO] Starting RAW upload helper")
        print(f"[INFO] Config: {cfg_path}")
        print(f"[INFO] Project base: {project_base}")
        print(f"[INFO] Local folder: {folder}")
        print(f"[INFO] S3 prefix: {args.prefix}")

        # Build a temporary config object with explicit project_base
        cfg = ConfigManager.from_file(str(cfg_path), project_base=str(project_base))

        # Always show discovery count first
        tasks = collect_upload_tasks(folder, RAW_EXTS, args.prefix)
        print(f"[INFO] Discovered {len(tasks)} files to consider for upload "
              f"(exts={sorted(RAW_EXTS)})")

        if args.dry_run:
            for p, k in tasks[:20]:
                print(f"[DRY-RUN] would upload: {p}  ->  {k}")
            if len(tasks) > 20:
                print(f"[DRY-RUN] ...and {len(tasks)-20} more")
            print("[DRY-RUN] Exiting without uploading.")
            return 0

        # Run real upload (it will also print a completion summary)
        stats = upload_raw_reels(cfg, folder, args.prefix)
        print(
            f"[DONE] Uploaded={stats['uploaded']} Skipped={stats['skipped']} "
            f"Failed={stats['failed']} TotalMB={stats['total_mb']} "
            f"AvgMBps={stats['avg_mb_s']} Log={stats['log_file']}"
        )
        return 0

    except Exception as e:
        print("[FATAL] An exception occurred. See details below.", file=sys.stderr)
        traceback.print_exc()
        return 1

if __name__ == "__main__":
    raise SystemExit(main())
