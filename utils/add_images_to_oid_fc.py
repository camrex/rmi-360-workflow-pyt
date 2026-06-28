# =============================================================================
# 🧭 OID Image Import Logic (utils/add_images_to_oid_fc.py)
# -----------------------------------------------------------------------------
# Purpose:             Adds geotagged 360° images to an ArcGIS Oriented Imagery Dataset (OID)
# Project:             RMI 360 Imaging Workflow Python Toolbox
# Version:             1.3.0
# Author:              RMI Valuation, LLC
# Created:             2025-05-13
# Last Updated:        2025-10-30
#
# Description:
#   Scans and validates a folder of final images, checks for reel_info
#   collisions, and appends entries to a target Oriented Imagery Dataset using
#   ArcPy’s Oriented Imagery tools. Includes schema validation and recursive support.
#
# File Location:        /utils/add_images_to_oid_fc.py
# Validator:            /utils/validators/add_images_to_oid_validator.py
# Called By:            tools/add_images_to_oid_tool.py
# Int. Dependencies:    utils/manager/config_manager, utils/shared/expression_utils
# Ext. Dependencies:    arcpy, pathlib
#
# Documentation:
#   See: docs_legacy/TOOL_GUIDES.md and docs_legacy/tools/add_images_to_oid.md
#   (Ensure these docs are current; update if needed.)
#
# Notes:
#   - Supports recursive reel folder discovery and duplicate prevention
#   - Integrates schema validation and status/error logging
# =============================================================================

__all__ = [
    "add_images_to_oid",
    "load_manifest_keys",
    "load_manifest_attr_map",
    "populate_manifest_custom_fields",
]

import csv
from pathlib import Path
from typing import Optional

import arcpy

from utils.manager.config_manager import ConfigManager
from utils.shared.expression_utils import load_field_registry
from utils.shared.manifest_fields import (
    load_manifest_attr_map,
    populate_oid_fields_from_manifest,
)


def load_manifest_keys(manifest_path: str, logger=None) -> tuple:
    """Read a corridor manifest CSV and return ``(names, paths)`` sets of kept images.

    ``names`` are filename basenames (the robust key — storage folders do not map
    1:1 to subdivisions, so the filename, not the folder, identifies an image).
    ``paths`` are normalized absolute-ish path strings as a secondary match.
    The manifest is expected to have a "Path" and/or "Name" column (case-sensitive
    headers as written by the corridor Export Manifest stage).
    """
    names, paths = set(), set()
    with open(manifest_path, "r", newline="", encoding="utf-8-sig") as f:
        reader = csv.DictReader(f)
        # Be tolerant of header casing.
        field_map = {fn.lower(): fn for fn in (reader.fieldnames or [])}
        name_col = field_map.get("name")
        path_col = field_map.get("path")
        for row in reader:
            if name_col and row.get(name_col):
                names.add(Path(str(row[name_col]).strip()).name.lower())
            if path_col and row.get(path_col):
                p = str(row[path_col]).strip()
                paths.add(p.replace("\\", "/").lower())
                names.add(Path(p).name.lower())  # derive name from path too
    if logger:
        logger.info(f"Manifest: {len(names):,} unique image name(s) loaded from {manifest_path}", indent=1)
    return names, paths


def _filter_files_by_manifest(jpg_files, names, paths):
    """Return the subset of ``jpg_files`` (Path objects) present in the manifest,
    matched by filename first, then by full path."""
    kept = []
    for f in jpg_files:
        fname = f.name.lower()
        fpath = str(f).replace("\\", "/").lower()
        if fname in names or fpath in paths:
            kept.append(f)
    return kept


def _manifest_custom_field_defs(cfg: ConfigManager):
    """Return ``[(oid_field_name, manifest_column, default, field_type)]`` for
    custom fields populated by a manifest join (i.e. carrying a ``manifest_field``)."""
    custom_fields = cfg.get("oid_schema_template.custom_fields", {}) or {}
    defs = []
    for _key, field in custom_fields.items():
        manifest_col = field.get("manifest_field")
        if manifest_col:
            defs.append((field.get("name"), str(manifest_col), field.get("default"), field.get("type")))
    return defs


def populate_manifest_custom_fields(cfg: ConfigManager, oid_fc_path: str, manifest_path: str, logger) -> int:
    """Populate manifest-sourced custom fields (those declaring ``manifest_field``)
    on the OID by joining the manifest to each image by filename. No-op when none
    are declared."""
    return populate_oid_fields_from_manifest(
        cfg, oid_fc_path, _manifest_custom_field_defs(cfg), manifest_path, logger
    )


def _write_image_listing(cfg: ConfigManager, files, manifest_path, logger) -> Path:
    """Write the kept image paths to a .txt (one absolute path per line) for the
    Esri Add Images tool, and return its path. Leaves an auditable artifact of
    exactly which images were ingested."""
    out_dir = cfg.paths.logs
    out_dir.mkdir(parents=True, exist_ok=True)
    stem = Path(manifest_path).stem if manifest_path else str(cfg.get("project.slug", "project"))
    listing = out_dir / f"add_images_{stem}.txt"
    with open(listing, "w", encoding="utf-8") as fh:
        for f in files:
            fh.write(f"{f}\n")
    logger.info(f"Wrote {len(files):,} image path(s) to listing: {listing}", indent=1)
    return listing


def warn_if_multiple_reel_info(image_folder, logger):
    """
    Checks for multiple 'reel_info.json' files within the specified image folder and its subfolders.
    
    If more than one 'reel_info.json' file is found, logs an error message listing all detected file paths.
    """
    reel_info_paths = list(image_folder.rglob("reel_info.json"))
    if len(reel_info_paths) > 1:
        logger.warning(
            f"Multiple reel_info.json files detected in image folder '{image_folder}':\n"
            + "\n".join(str(p) for p in reel_info_paths), indent=1
        )


def add_images_to_oid(cfg: ConfigManager, oid_fc_path: str, manifest_path: Optional[str] = None) -> None:
    """
    Adds images from a project folder to an existing Oriented Imagery Dataset (OID).

    Resolves configuration to determine the image folder, validates the presence of required files and directories,
    and adds JPEG images (including those in subfolders) to the specified OID feature class using ArcPy. Logs errors
    if the OID, image folder, or images are missing, and integrates with ArcGIS messaging for status updates.

    Pre-thin (manifest-driven) mode: when ``manifest_path`` is provided (or
    configured via ``corridor_thinning.manifest.path`` while ``thinning_mode`` is
    "pre"), ONLY the images listed in the corridor manifest are added. This is the
    convergence point that lets pre-thinning create OID entries for kept images
    only, instead of adding all panoramas and culling later (post-thin).

    Args:
        cfg: Validated configuration manager.
        oid_fc_path: Path to the existing OID feature class.
        manifest_path: Optional corridor manifest CSV; restricts the added images
            to the kept set. When None, the configured manifest is used if
            ``thinning_mode`` is "pre"; otherwise all images are added.
    """
    logger = cfg.get_logger()
    cfg.validate(tool="add_images_to_oid")

    # Resolve manifest: explicit arg wins; else honor pre-thin config.
    if manifest_path is None and str(cfg.get("thinning_mode", "post")).lower() == "pre":
        configured = cfg.get("corridor_thinning.manifest.path")
        if configured:
            manifest_path = str(configured)

    image_folder = cfg.paths.original

    with cfg.get_progressor(total=2, label="Adding images to OID") as progressor:
        warn_if_multiple_reel_info(image_folder, logger)

        if not arcpy.Exists(oid_fc_path):
            logger.error(f"OID does not exist at path: {oid_fc_path}", error_type=FileNotFoundError, indent=1)
            return

        if not image_folder.is_dir():
            logger.error(f"Image folder not found: {image_folder}", error_type=FileNotFoundError, indent=1)
            return

        # Use pathlib to collect all .jpg files recursively
        jpg_files = list(image_folder.rglob("*.jpg"))
        if not jpg_files:
            logger.error(f"No .jpg files found in image folder or its subfolders: {image_folder}", error_type=RuntimeError, indent=1)
            return

        registry = load_field_registry(cfg)
        if not registry:
            logger.error("Failed to load field registry", error_type=ValueError, indent=1)
            return

        imagery_type = registry.get("OrientedImageryType", {}).get("oid_default", "360")

        # Pre-thin: restrict to the manifest's kept images and add them explicitly.
        if manifest_path:
            if not Path(manifest_path).is_file():
                logger.error(f"Manifest not found: {manifest_path}", error_type=FileNotFoundError, indent=1)
                return
            names, paths = load_manifest_keys(manifest_path, logger)
            kept_files = _filter_files_by_manifest(jpg_files, names, paths)
            matched_names = {f.name.lower() for f in kept_files}
            missing = len(names) - len(matched_names & names)
            logger.info(
                f"Pre-thin manifest mode: {len(kept_files):,} of {len(jpg_files):,} images "
                f"on disk matched the manifest ({len(names):,} manifest entries).",
                indent=1,
            )
            if missing > 0:
                logger.warning(
                    f"{missing:,} manifest entr(ies) had no matching file under {image_folder}.",
                    indent=1,
                )
            if not kept_files:
                logger.error("No images matched the manifest — nothing to add.", error_type=RuntimeError, indent=1)
                return
            # Feed Esri a .txt of explicit image paths (one per line) rather than a
            # large in-memory list: scales to big corridors and leaves an artifact.
            listing_path = _write_image_listing(cfg, kept_files, manifest_path, logger)
            input_data = str(listing_path)
            include_sub = "NOSUBFOLDERS"  # Esri keyword has no underscore
        else:
            logger.info(f"Adding all images from '{image_folder}' (including subfolders) to OID: {oid_fc_path}", indent=1)
            input_data = [str(image_folder)]
            include_sub = "SUBFOLDERS"

        progressor.update(1)

        try:
            arcpy.oi.AddImagesToOrientedImageryDataset(
                in_oriented_imagery_dataset=oid_fc_path,
                imagery_category=imagery_type,
                input_data=input_data,
                include_sub_folders=include_sub
            )
            progressor.update(2)
        except arcpy.ExecuteError as exc:
            logger.error(f"Failed to add images to OID: {exc}", error_type=RuntimeError, indent=1)
            return

        # Join per-image manifest attributes (e.g. Track) onto the rows just added.
        # Only meaningful in manifest/pre-thin mode; post-thin leaves these null.
        if manifest_path:
            populate_manifest_custom_fields(cfg, oid_fc_path, manifest_path, logger)

    logger.success("Images successfully added to OID.", indent=1)
