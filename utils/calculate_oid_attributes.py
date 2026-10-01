# =============================================================================
# 🧮 OID Attribute Enrichment Logic (utils/calculate_oid_attributes.py)
# -----------------------------------------------------------------------------
# Purpose:             Enriches Oriented Imagery Dataset features with camera orientation, reel, and Z attributes
# Project:             RMI 360 Imaging Workflow Python Toolbox
# Version:             1.3.0
# Author:              RMI Valuation, LLC
# Created:             2025-05-13
# Last Updated:        2026-10-01
#
# Description:
#   Applies default and derived values to fields in an OID feature class, including
#   orientation, SRS, reel, and frame info. Incorporates validation against a field
#   registry and adjusts Z-values using configured camera offsets. Converts camera
#   heights from ellipsoidal (source frame, e.g. ITRF2014 from POLARIS) to NAD83(2011)
#   at the capture epoch, then to NAVD88 orthometric (GEOID18), so the Z values match
#   the OID's vertical CRS (EPSG:5703) and Terrain3D elevation source. The original
#   ellipsoidal value is preserved in Z_Ellipsoidal and the applied frame/epoch in
#   Z_Frame. Validates field-of-view defaults and integrates reel_info.json metadata.
#
# File Location:        /utils/calculate_oid_attributes.py
# Validator:            /utils/validators/calculate_oid_attributes_validator.py
# Called By:            tools/add_images_to_oid_tool.py
# Int. Dependencies:    utils/manager/config_manager, utils/shared/expression_utils
# Ext. Dependencies:    arcpy, os, json, re, typing
#
# Documentation:
#   See: docs_legacy/TOOL_GUIDES.md and docs_legacy/tools/add_images_to_oid.md
#   (Ensure these docs are current; update if needed.)
#
# Notes:
#   - Integrates reel_info.json if present to supplement reel assignment
#   - Skips processing if OID is empty or missing required fields
# =============================================================================

__all__ = [
    "enrich_oid_attributes",
    "convert_heights_to_navd88",
    "resolve_source_frame",
    "frame_tag",
    "ELLIPSOIDAL_Z_FIELD",
    "Z_FRAME_FIELD",
]

import arcpy
import re
import os
import json
from typing import Optional, Tuple

from utils.manager.config_manager import ConfigManager
from utils.shared.expression_utils import load_field_registry
from utils.shared.geoid_transform import (
    SOURCE_FRAMES,
    GeoidTransformError,
    decimal_year,
    ellipsoidal_to_orthometric,
    to_nad83_2011,
)

# Field that preserves the original ellipsoidal Z (m) after geoid conversion.
# Added at runtime (like QCFlag); a populated value marks the row's SHAPE@Z as
# already NAVD88, making the conversion idempotent across re-runs.
ELLIPSOIDAL_Z_FIELD = "Z_Ellipsoidal"

# Field recording the reference frame (and capture epoch) the row's height was
# moved from before GEOID18, e.g. "ITRF2014@2026.051" or "NAD83_2011". Empty on
# rows converted before the frame step existed (schema 1.5.0), which lets the
# Fix OID Elevations tool find and correct them exactly once.
Z_FRAME_FIELD = "Z_Frame"
_Z_FRAME_LENGTH = 32
_ACQUISITION_FIELD = "AcquisitionDate"


def resolve_source_frame(cfg: ConfigManager, override: Optional[str] = None) -> str:
    """The reference frame of the input ellipsoidal heights: ``override`` (a tool
    parameter) wins, else ``spatial_ref.geoid_correction.source_frame``. Never
    guessed — a missing/unknown value raises GeoidTransformError."""
    frame = override or cfg.get("spatial_ref.geoid_correction.source_frame")
    if not frame:
        raise GeoidTransformError(
            "spatial_ref.geoid_correction.source_frame is not set. Set it to the frame of the "
            "camera heights (POLARIS mount point = ITRF2014; POLARIS_LOCAL = NAD83_2011) — "
            "upgrade the config with the Config Editor, or pass Source Frame to the tool."
        )
    frame = str(frame).strip().upper()
    if frame not in SOURCE_FRAMES:
        raise GeoidTransformError(
            f"Unsupported source_frame '{frame}'. Supported: {', '.join(SOURCE_FRAMES)}."
        )
    return frame


def frame_tag(source_frame: str, epoch: Optional[float]) -> str:
    """Z_Frame value: the frame name, plus ``@epoch`` when a time-dependent shift applied."""
    if SOURCE_FRAMES.get(source_frame) is None or epoch is None:
        return source_frame
    return f"{source_frame}@{epoch:.3f}"


def _safe_float(value, default=0.0) -> float:
    try:
        return float(value)
    except (ValueError, TypeError):
        return default


def check_oid_fov_defaults(oid_fc_path: str, registry: dict, logger):
    """
    Checks that HFOV and VFOV values in the OID feature class match expected defaults.
    
    Logs an error for each row where the HorizontalFieldOfView or VerticalFieldOfView
    differs from the default values specified in the registry.
    """
    expected_hfov = registry.get("HFOV", {}).get("oid_default")
    expected_vfov = registry.get("VFOV", {}).get("oid_default")

    with arcpy.da.SearchCursor(oid_fc_path, ["HorizontalFieldOfView", "VerticalFieldOfView"]) as cursor:
        for i, row in enumerate(cursor):
            hfov, vfov = row
            if hfov != expected_hfov or vfov != expected_vfov:
                logger.error(f"Row {i}: HFOV or VFOV does not match expected values from registry.\n "
                             f"Expected HFOV={expected_hfov}, VFOV={expected_vfov}, but got HFOV={hfov}, VFOV={vfov}",
                             error_type=ValueError, indent=1)


def load_reel_from_info_file(image_path: str, logger) -> Tuple[Optional[str], Optional[str]]:
    """
    Attempts to find and read a reel_info.json file near the specified image path.
    
    Searches the parent and grandparent directories of the image for a reel_info.json file.
    If exactly one file is found, returns its "reel" value and the file path. If multiple files
    are found or an error occurs, logs a warning and returns (None, None).
    
    Args:
        image_path: Full path to the image file.
        logger: Logger instance.
    
    Returns:
        A tuple containing the reel value and the path to the reel_info.json file, or (None, None)
        if not found or if an error occurs.
    """
    try:
        dirs_to_check = [
            os.path.dirname(os.path.dirname(image_path)),   # grandparent
            os.path.dirname(image_path)                     # parent
        ]

        reel_info_paths = [os.path.join(d, "reel_info.json") for d in dirs_to_check if os.path.isfile(os.path.join(d, "reel_info.json"))]

        if len(reel_info_paths) == 1:
            path = reel_info_paths[0]
            with open(path, "r") as f:
                reel_data = json.load(f)
                return reel_data.get("reel"), path

        if len(reel_info_paths) > 1:
            logger.warning(f"Multiple reel_info.json files found near: {image_path}\nFiles:\n" + "\n".join(reel_info_paths), indent=1)
    except Exception as e:
        logger.error(f"Failed to load reel_info.json near: {image_path}\n{e}", indent=1)

    return None, None


def extract_reel_from_path(image_path: str) -> Optional[str]:
    """
    Extract a 4-digit reel number from image context.
    
    Priority:
      1) grandparent folder matching 'reel_XXXX'
      2) filename token matching 'reel_XXXX'
      3) filename token matching 'RLXXXX'

    Returns the 4-digit reel string when found, otherwise None.
    """
    reel_folder = os.path.basename(os.path.dirname(os.path.dirname(image_path)))
    match = re.search(r"reel_(\d{4})", reel_folder, re.IGNORECASE)
    if match:
        return match.group(1)

    image_file = os.path.basename(image_path)
    match = re.search(r"(?:^|_)reel_(\d{4})(?:_|$)", image_file, re.IGNORECASE)
    if match:
        return match.group(1)

    match = re.search(r"(?:^|_)RL(\d{4})(?:_|$)", image_file, re.IGNORECASE)
    if match:
        return match.group(1)

    return None


def extract_frame_from_filename(image_path: str) -> Optional[str]:
    """
    Extracts a 6-digit frame number from the image filename.
    
    The function searches for a pattern like '_000234.jpg' at the end of the filename and returns the frame number if
    found. Returns None if the pattern is not present or an error occurs.
    """

    image_file = os.path.basename(image_path)
    match = re.search(r"_(\d{6})\.jpg$", image_file, re.IGNORECASE)
    return match.group(1) if match else None


def convert_heights_to_navd88(cfg: ConfigManager, oid_fc_path: str, logger) -> Optional[dict]:
    """Batch-convert camera Z values from ellipsoidal to NAVD88 orthometric.

    The XVN/Point One chain only outputs ellipsoidal heights, in the frame of its
    RTK corrections (POLARIS mount point = ITRF2014 at the current epoch), while the
    OID's vertical CRS (EPSG:5703) and Terrain3D are NAVD88 orthometric. Two
    vectorized pyproj steps: source frame -> NAD83(2011) at each row's capture
    epoch (from AcquisitionDate), then GEOID18.

    Idempotent: the original ellipsoidal Z is preserved in ``Z_Ellipsoidal`` (added
    here if missing), and rows where that field is already populated are re-derived
    from it rather than converted twice. The applied frame/epoch is recorded in
    ``Z_Frame``. Horizontal coordinates are never changed.

    Returns:
        Mapping ``{objectid: (z_navd88, z_ellipsoidal, z_frame)}`` on success, or
        None on failure (unset/unknown frame, missing AcquisitionDate, missing grid
        or frame operation, out-of-coverage points, implausible shifts) — callers
        must treat None as a hard stop, never write unconverted heights.
    """
    geoid_model = str(cfg.get("spatial_ref.geoid_correction.model", "GEOID18"))
    try:
        source_frame = resolve_source_frame(cfg)
    except GeoidTransformError as e:
        logger.error(f"Geoid conversion not attempted: {e}", error_type=GeoidTransformError, indent=1)
        return None
    needs_epoch = SOURCE_FRAMES[source_frame] is not None

    existing = {f.name for f in arcpy.ListFields(oid_fc_path)}
    if needs_epoch and _ACQUISITION_FIELD not in existing:
        logger.error(
            f"The OID has no {_ACQUISITION_FIELD} field, which is needed for the {source_frame} -> "
            "NAD83(2011) capture epoch. Nothing converted.", error_type=GeoidTransformError, indent=1
        )
        return None
    if ELLIPSOIDAL_Z_FIELD not in existing:
        arcpy.management.AddField(
            oid_fc_path, ELLIPSOIDAL_Z_FIELD, "DOUBLE",
            field_alias="Ellipsoidal Z (source frame, m)"
        )
    if Z_FRAME_FIELD not in existing:
        arcpy.management.AddField(
            oid_fc_path, Z_FRAME_FIELD, "TEXT", field_length=_Z_FRAME_LENGTH,
            field_alias="Z source frame@epoch"
        )

    read_fields = ["OID@", "SHAPE@X", "SHAPE@Y", "SHAPE@Z", ELLIPSOIDAL_Z_FIELD]
    if needs_epoch:
        read_fields.append(_ACQUISITION_FIELD)

    oids, lons, lats, z_src, epochs = [], [], [], [], []
    already_converted = 0
    missing_date = []
    with arcpy.da.SearchCursor(oid_fc_path, read_fields) as cursor:
        for row in cursor:
            oid, x, y, z, z_ellip = row[:5]
            if x is None or y is None or (z is None and z_ellip is None):
                continue
            acquired = row[5] if needs_epoch else None
            if needs_epoch and acquired is None:
                missing_date.append(oid)
                continue
            if z_ellip is not None:
                already_converted += 1
            oids.append(oid)
            lons.append(x)
            lats.append(y)
            # A populated Z_Ellipsoidal means this row was converted before —
            # re-derive from the preserved original instead of converting twice.
            z_src.append(z_ellip if z_ellip is not None else z)
            epochs.append(decimal_year(acquired) if needs_epoch else None)

    if missing_date:
        logger.error(
            f"{len(missing_date):,} row(s) have no {_ACQUISITION_FIELD} (first OID {missing_date[0]}); "
            f"the capture epoch is required for the {source_frame} -> NAD83(2011) shift. "
            "Nothing converted.", error_type=GeoidTransformError, indent=1
        )
        return None
    if not oids:
        logger.warning("No rows with usable geometry found for geoid conversion.", indent=1)
        return {}

    try:
        h_nad83, frame_shift = to_nad83_2011(
            lons, lats, z_src, source_frame, epochs if needs_epoch else 0.0
        )
        z_navd88, separation = ellipsoidal_to_orthometric(lons, lats, h_nad83, model=geoid_model)
    except GeoidTransformError as e:
        logger.error(f"Geoid conversion failed: {e}", error_type=GeoidTransformError, indent=1)
        return None
    except ImportError as e:
        logger.error(
            f"pyproj is required for the geoid conversion but could not be imported: {e}",
            error_type=ImportError, indent=1
        )
        return None

    if already_converted:
        logger.info(
            f"{already_converted:,} row(s) already had {ELLIPSOIDAL_Z_FIELD} populated; "
            "re-derived NAVD88 from the preserved ellipsoidal values.", indent=1
        )
    if needs_epoch:
        logger.info(
            f"Reference frame {source_frame} -> NAD83(2011) at capture epoch "
            f"{min(epochs):.3f}..{max(epochs):.3f}: height shift min {frame_shift.min():+.3f}, "
            f"mean {frame_shift.mean():+.3f}, max {frame_shift.max():+.3f} m.", indent=1
        )
    else:
        logger.info("Source frame NAD83_2011: no reference-frame shift applied.", indent=1)
    logger.info(
        f"Converted {len(oids):,} camera height(s) to NAVD88 via {geoid_model}: "
        f"ellipsoidal Z [{min(z_src):.2f}, {max(z_src):.2f}] m -> "
        f"NAVD88 Z [{z_navd88.min():.2f}, {z_navd88.max():.2f}] m "
        f"(geoid separation N: min {separation.min():.2f}, "
        f"mean {separation.mean():.2f}, max {separation.max():.2f} m).", indent=1
    )

    return {
        oid: (float(h), float(src), frame_tag(source_frame, ep))
        for oid, h, src, ep in zip(oids, z_navd88, z_src, epochs)
    }


def enrich_oid_attributes(cfg: ConfigManager, oid_fc_path: str, adjust_z: bool = True) -> None:
    """
    Enriches an Oriented Imagery Dataset with derived and default attribute values.

    This function updates the specified OID feature class by setting default values for camera parameters, converting
    camera heights from ellipsoidal to NAVD88 orthometric (unless spatial_ref.geoid_correction.enabled is false),
    adjusting Z coordinates by camera offset if requested, and populating orientation, spatial reference, reel, and
    frame fields.
    Reel and frame numbers are extracted from image paths or associated metadata files. Field of view values are
    validated against expected defaults. The function is typically used after adding images to the dataset.
    """
    logger = cfg.get_logger()
    cfg.validate(tool="calculate_oid_attributes")

    # Load registry and schema safely
    registry = load_field_registry(cfg)

    # Compute Z offset and camera height
    try:
        z_cm = sum(_safe_float(v) for v in cfg.get("camera_offset.z", {}).values())
        height_cm = sum(_safe_float(v) for v in cfg.get("camera_offset.camera_height").values())
        z_offset = z_cm / 100.0
        camera_height = height_cm / 100.0
    except Exception as e:
        logger.error(f"Failed to compute camera offset or height: {e}", error_type=ValueError, indent=1)
        return

    h_wkid = cfg.get("spatial_ref.gcs_horizontal_wkid", 4326)
    v_wkid = cfg.get("spatial_ref.vcs_vertical_wkid", 5703)

    # Ellipsoidal -> NAVD88 orthometric conversion (default on). The XVN/Point One
    # heights are ellipsoidal; the OID vertical CRS (5703) and Terrain3D are
    # orthometric, so unconverted Z would sit ~8-33 m low across CONUS.
    apply_geoid = bool(cfg.get("spatial_ref.geoid_correction.enabled", True))
    navd88_by_oid = None
    if apply_geoid:
        navd88_by_oid = convert_heights_to_navd88(cfg, oid_fc_path, logger)
        if navd88_by_oid is None:
            # Hard stop — never write ellipsoidal heights labeled as NAVD88.
            return
    else:
        logger.warning(
            "Geoid correction disabled (spatial_ref.geoid_correction.enabled=false): "
            f"camera Z values remain ellipsoidal but are labeled vertical WKID {v_wkid} (NAVD88).",
            indent=1
        )

    pitch = registry.get("CameraPitch", {}).get("oid_default", 90)
    roll = registry.get("CameraRoll", {}).get("oid_default", 0)
    near = registry.get("NearDistance", {}).get("oid_default", 2)
    far = registry.get("FarDistance", {}).get("oid_default", 50)
    image_rotation = registry.get("ImageRotation", {}).get("oid_default", 0)
    orientation_accuracy = registry.get(
        "OrientationAccuracy", {}
    ).get("oid_default", "15;0.2;0.5;0.5;0.5;0;0;1")

    # Determine fields to fetch and update
    esri_cfg = cfg.get("oid_schema_template.esri_default", {})
    schema_cfg = cfg.get("oid_schema_template", {})
    fields = ["OID@", "SHAPE@X", "SHAPE@Y", "SHAPE@Z"]

    for field in registry.values():
        # not_applicable fields (for example CameraOffset, OffsetFromStart) are
        # intentionally excluded unless explicitly enabled in config.
        if field.get("category") == "standard" or (field.get("category") == "not_applicable" and
                                                   esri_cfg.get("not_applicable", False)):
            fields.append(field["name"])

    for fdef in schema_cfg.get("mosaic_fields", {}).values():
        fields.append(fdef["name"])

    if navd88_by_oid is not None:
        fields.extend([ELLIPSOIDAL_Z_FIELD, Z_FRAME_FIELD])

    # Deduplicate in case of overlap
    fields = list(dict.fromkeys(fields))
    field_to_index = {name: i for i, name in enumerate(fields)}

    check_oid_fov_defaults(oid_fc_path, registry, logger)

    # Read first image path to extract reel metadata
    first_image_path = None
    with arcpy.da.SearchCursor(oid_fc_path, ["ImagePath"], where_clause="ImagePath IS NOT NULL") as cursor:
        first_image_path = next((row[0].strip() for row in cursor if row[0]), None)

    # Handle empty dataset scenario
    if not first_image_path:
        logger.error("No images found in the OID dataset. Skipping OID attribute calculation.", indent=1)
        return

    reel_from_info, reel_info_path_used = load_reel_from_info_file(first_image_path, logger)
    if reel_info_path_used:
        logger.info(f"📄 Using reel_info.json from: {reel_info_path_used}", indent=1)

    # Count rows to prepare progressor
    row_count = int(arcpy.management.GetCount(oid_fc_path)[0])

    updated = 0
    with cfg.get_progressor(total=row_count, label="Enriching OID attributes") as progressor:
        with arcpy.da.UpdateCursor(oid_fc_path, fields) as cursor:
            for i, row in enumerate(cursor, start=1):
                # Safely access required fields
                try:
                    x = row[field_to_index["SHAPE@X"]]
                    y = row[field_to_index["SHAPE@Y"]]
                    z = row[field_to_index["SHAPE@Z"]]
                except KeyError:
                    logger.warning(f"Missing SHAPE@X/Y/Z fields on row {i}, skipping row.", indent=2)
                    continue

                z_ellipsoidal = z_frame = None
                if navd88_by_oid is not None:
                    converted = navd88_by_oid.get(row[field_to_index["OID@"]])
                    if converted is None:
                        logger.warning(f"No geoid-converted Z for row {i}, skipping row.", indent=2)
                        continue
                    z, z_ellipsoidal, z_frame = converted
                adjusted_z = z + z_offset if adjust_z else z

                heading = row[field_to_index["CameraHeading"]] if "CameraHeading" in field_to_index else None
                if heading is None:
                    logger.warning(f"Missing CameraHeading for row {i}, skipping row.", indent=2)
                    continue

                image_path = row[field_to_index["ImagePath"]].strip() if "ImagePath" in field_to_index and row[field_to_index["ImagePath"]] else None
                if not image_path:
                    logger.warning(f"Missing ImagePath for row {i}, skipping row.", indent=2)
                    continue

                orientation = f"1|{h_wkid}|{v_wkid}|{x:.6f}|{y:.6f}|{adjusted_z:.3f}|{heading:.1f}|{pitch:.1f}|{roll:.1f}"
                reel = extract_reel_from_path(image_path) or reel_from_info
                frame = extract_frame_from_filename(image_path)

                # Only assign to fields that exist in the schema
                if "CameraPitch" in field_to_index:
                    row[field_to_index["CameraPitch"]] = pitch
                if "CameraRoll" in field_to_index:
                    row[field_to_index["CameraRoll"]] = roll
                if "NearDistance" in field_to_index:
                    row[field_to_index["NearDistance"]] = near
                if "FarDistance" in field_to_index:
                    row[field_to_index["FarDistance"]] = far
                if "ImageRotation" in field_to_index:
                    row[field_to_index["ImageRotation"]] = image_rotation
                if "OrientationAccuracy" in field_to_index:
                    row[field_to_index["OrientationAccuracy"]] = orientation_accuracy
                if "X" in field_to_index:
                    row[field_to_index["X"]] = x
                if "Y" in field_to_index:
                    row[field_to_index["Y"]] = y
                if "Z" in field_to_index:
                    row[field_to_index["Z"]] = adjusted_z
                if "SHAPE@Z" in field_to_index:
                    row[field_to_index["SHAPE@Z"]] = adjusted_z
                if z_ellipsoidal is not None and ELLIPSOIDAL_Z_FIELD in field_to_index:
                    row[field_to_index[ELLIPSOIDAL_Z_FIELD]] = z_ellipsoidal
                if z_frame is not None and Z_FRAME_FIELD in field_to_index:
                    row[field_to_index[Z_FRAME_FIELD]] = z_frame
                if "SRS" in field_to_index:
                    row[field_to_index["SRS"]] = f"{h_wkid},{v_wkid}"
                if "CameraHeight" in field_to_index:
                    row[field_to_index["CameraHeight"]] = camera_height
                if "CameraOrientation" in field_to_index:
                    row[field_to_index["CameraOrientation"]] = orientation
                if "Reel" in field_to_index:
                    row[field_to_index["Reel"]] = reel
                if "Frame" in field_to_index:
                    row[field_to_index["Frame"]] = frame

                cursor.updateRow(row)
                updated += 1
                progressor.update(i)

    logger.success(f"Updated {updated} image(s) with orientation, Z, and mosaic fields.", indent=1)
