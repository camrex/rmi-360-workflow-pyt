#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""
Download config and/or gis_data files from S3 to local project directory.

This script is useful for:
- Setting up a new project on EC2 from S3 storage
- Updating config files from S3
- Syncing GIS reference data

NOTE: By default, this script excludes reels. The orchestrator handles
      reel downloads based on selected reels to process. Use --include-reels
      to explicitly download reels if needed for standalone testing.
"""

from __future__ import annotations
from pathlib import Path
import argparse
import sys
import traceback

# Ensure repo root is on sys.path
REPO_ROOT = Path(__file__).resolve().parents[1]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

# Skip arcpy imports if ArcGIS not installed
import builtins
if 'arcpy' not in sys.modules:
    import types
    sys.modules['arcpy'] = types.SimpleNamespace(
        env=types.SimpleNamespace(workspace=None),
        Exists=lambda *a, **k: False,
    )


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Download config and/or gis_data files from S3 to local project directory."
    )
    parser.add_argument("--config", required=True, help="Path to config.yaml")
    parser.add_argument("--project-key", required=True, help="Project key (e.g., RMI25320)")
    parser.add_argument("--bucket", help="S3 bucket name (default: from config aws.s3_bucket_raw)")
    parser.add_argument(
        "--folder-types",
        nargs='+',
        choices=['config', 'gis_data', 'reels', 'logs', 'report'],
        help="Folder types to download (default: config and gis_data; excludes reels)"
    )
    parser.add_argument(
        "--include-reels",
        action='store_true',
        help="Include reels in download (normally excluded as orchestrator handles reels)"
    )
    parser.add_argument(
        "--local-dir",
        help="Local project directory (default: {local_root}/projects/{project_key})"
    )
    parser.add_argument("--max-workers", type=int, default=16, help="Max concurrent downloads")
    parser.add_argument("--force", action="store_true", help="Re-download files even if they exist")
    parser.add_argument("--dry-run", action="store_true", help="List files but don't download")
    args = parser.parse_args()

    try:
        cfg_path = Path(args.config).resolve()
        if not cfg_path.exists():
            print(f"[ERROR] Config file not found: {cfg_path}", file=sys.stderr)
            return 2

        # Import after path setup
        from utils.manager.config_manager import ConfigManager
        from utils.s3_utils import stage_project_files

        # Load config
        project_base = cfg_path.parent
        cfg = ConfigManager.from_file(str(cfg_path), project_base=str(project_base))

        # Determine bucket
        bucket = args.bucket or cfg.get("aws.s3_bucket_raw")
        if not bucket:
            print("[ERROR] No bucket specified and aws.s3_bucket_raw not in config", file=sys.stderr)
            return 2

        # Determine local directory
        if args.local_dir:
            local_dir = Path(args.local_dir).resolve()
        else:
            local_root = cfg.get("runtime.local_root")
            if not local_root:
                print("[ERROR] No --local-dir specified and runtime.local_root not in config", file=sys.stderr)
                return 2
            local_dir = Path(local_root) / "projects" / args.project_key

        # Folder types - exclude reels by default unless explicitly requested
        if args.folder_types:
            folder_types = args.folder_types
        else:
            folder_types = ['config', 'gis_data']
            if args.include_reels:
                folder_types.append('reels')

        # Warn if reels included
        if 'reels' in folder_types and not args.include_reels:
            print("[WARNING] Downloading reels. Normally orchestrator handles reel downloads.", file=sys.stderr)

        print(f"[INFO] Downloading project files from S3")
        print(f"[INFO] Bucket: {bucket}")
        print(f"[INFO] Project Key: {args.project_key}")
        print(f"[INFO] Folder Types: {', '.join(folder_types)}")
        print(f"[INFO] Local Directory: {local_dir}")
        print(f"[INFO] Max Workers: {args.max_workers}")
        print(f"[INFO] Skip Existing: {not args.force}")

        if args.dry_run:
            print("[DRY-RUN] Would download files to the following locations:")
            for folder_type in folder_types:
                print(f"  - s3://{bucket}/{args.project_key}/{folder_type}/ → {local_dir}/{folder_type}/")
            print("[DRY-RUN] Use without --dry-run to actually download files.")
            return 0

        # Download files
        result_paths = stage_project_files(
            bucket=bucket,
            project_key=args.project_key,
            folder_types=folder_types,
            local_project_dir=local_dir,
            max_workers=args.max_workers,
            skip_if_exists=not args.force
        )

        print("\n[SUCCESS] Downloaded project files:")
        for folder_type, path in result_paths.items():
            file_count = sum(1 for _ in path.rglob('*') if _.is_file())
            print(f"  - {folder_type}: {file_count} files → {path}")

        return 0

    except Exception as e:
        print(f"[FATAL] An exception occurred: {e}", file=sys.stderr)
        traceback.print_exc()
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
