# =============================================================================
# 🩹 OID Elevation Fix Logic (utils/fix_oid_elevations.py)
# -----------------------------------------------------------------------------
# Purpose:             Repairs existing OIDs whose camera Z values are ellipsoidal (pre-geoid-fix)
# Project:             RMI 360 Imaging Workflow Python Toolbox
# Version:             1.0.0
# Author:              RMI Valuation, LLC
# Created:             2026-07-17
# Last Updated:        2026-07-17
#
# Description:
#   OIDs built before the geoid conversion carry WGS84/ITRF *ellipsoidal* camera
#   heights mislabeled as NAVD88 (EPSG:5703) — cameras sit ~8-33 m below the
#   orthometric ground surface across CONUS. This module converts each row's Z to
#   NAVD88 (GEOID18) in place: SHAPE@Z, the Z attribute, and the CameraOrientation
#   string are rewritten; the pre-offset ellipsoidal source value is preserved in
#   Z_Ellipsoidal (same semantics as the pipeline's Calculate OID Attributes step,
#   so re-runs and future enrich runs stay idempotent). Rows whose Z_Ellipsoidal
#   is already populated are treated as fixed and skipped. Images and horizontal
#   coordinates are never touched.
#
# File Location:        /utils/fix_oid_elevations.py
# Called By:            tools/oid_fix_elevations_tool.py
# Int. Dependencies:    utils/manager/config_manager, utils/shared/geoid_transform
# Ext. Dependencies:    arcpy, dataclasses, typing
#
# Documentation:
#   See: docs/geoid_conversion.md ("Reprocessing existing OIDs")
#
# Notes:
#   - DRY RUN by default (maintenance-toolbox convention): reports what would
#     change without writing.
#   - The camera lever-arm z-offset (config camera_offset.z) was already applied
#     when the OID was built, so the stored Z is (ellipsoidal + offset). The fixed
#     Z is simply (stored Z - N): the geoid separation N is independent of height,
#     so the offset passes through unchanged.
# =============================================================================

__all__ = [
    "fix_oid_elevations",
    "republish_oid_service",
    "preview_service_overwrite",
    "ElevationFixResult",
]

import re
from dataclasses import dataclass, field

import arcpy

from utils.manager.config_manager import ConfigManager
from utils.calculate_oid_attributes import ELLIPSOIDAL_Z_FIELD, _safe_float
from utils.shared.geoid_transform import GeoidTransformError, ellipsoidal_to_orthometric
from utils.shared.oid_storage_paths import (
    extract_filename_from_image_path,
    is_secured_storage_enabled,
    resolve_oid_target_bucket,
    resolve_oid_target_region,
)

# Drive-letter or UNC path — a LOCAL ImagePath, i.e. not yet in delivery form.
_LOCAL_PATH_RE = re.compile(r"^(?:[A-Za-z]:[\\/]|\\\\)")


@dataclass
class ElevationFixResult:
    total: int = 0                # rows inspected
    fixed: int = 0                # rows converted (or that would be, in dry run)
    already_fixed: int = 0        # rows with Z_Ellipsoidal populated — skipped
    skipped: int = 0              # rows lacking geometry/heading — skipped with warning
    dry_run: bool = True
    separation_min: float = 0.0
    separation_max: float = 0.0
    samples: list = field(default_factory=list)  # (oid, z_before, z_after) preview


def fix_oid_elevations(cfg: ConfigManager, oid_fc: str, dry_run: bool = True):
    """Convert an existing OID's camera Z values from ellipsoidal to NAVD88 in place.

    Args:
        cfg: Validated configuration manager (needs spatial_ref + camera_offset,
            both covered by the calculate_oid_attributes validator).
        oid_fc: Path to the OID feature class to repair — either the source OID
            or a prepared *_aws delivery copy. Fix the copy that backs the
            published service (they are independent datasets: fixing the source
            does NOT propagate to an already-generated *_aws copy, and
            vice versa — each carries its own Z_Ellipsoidal marker).
        dry_run: When True (default), report what would change without writing.

    Returns:
        ElevationFixResult on success (fixed may be 0 if everything was already
        converted), or None on hard failure (missing grid, out-of-coverage points,
        implausible separations) — nothing is written in that case.
    """
    logger = cfg.get_logger()
    cfg.validate(tool="calculate_oid_attributes")

    if not arcpy.Exists(oid_fc):
        logger.error(f"OID does not exist at path: {oid_fc}", error_type=FileNotFoundError, indent=1)
        return None

    geoid_model = str(cfg.get("spatial_ref.geoid_correction.model", "GEOID18"))
    h_wkid = cfg.get("spatial_ref.gcs_horizontal_wkid", 4326)
    v_wkid = cfg.get("spatial_ref.vcs_vertical_wkid", 5703)
    z_offset = sum(_safe_float(v) for v in cfg.get("camera_offset.z", {}).values()) / 100.0

    has_ellip_field = ELLIPSOIDAL_Z_FIELD in {f.name for f in arcpy.ListFields(oid_fc)}

    # ---- Pass 1: collect rows still carrying ellipsoidal heights -------------
    fields = ["OID@", "SHAPE@X", "SHAPE@Y", "SHAPE@Z"]
    if has_ellip_field:
        fields.append(ELLIPSOIDAL_Z_FIELD)

    result = ElevationFixResult(dry_run=dry_run)
    oids, lons, lats, z_stored = [], [], [], []
    with arcpy.da.SearchCursor(oid_fc, fields) as cursor:
        for row in cursor:
            result.total += 1
            oid, x, y, z = row[0], row[1], row[2], row[3]
            z_ellip = row[4] if has_ellip_field else None
            if z_ellip is not None:
                result.already_fixed += 1
                continue
            if x is None or y is None or z is None:
                result.skipped += 1
                continue
            oids.append(oid)
            lons.append(x)
            lats.append(y)
            z_stored.append(z)

    if result.already_fixed:
        logger.info(
            f"{result.already_fixed:,} of {result.total:,} row(s) already have "
            f"{ELLIPSOIDAL_Z_FIELD} populated — treated as fixed and skipped.", indent=1
        )
    if not oids:
        logger.info("No rows need elevation conversion — nothing to do.", indent=1)
        return result

    # The stored Z includes the camera lever-arm offset applied at build time.
    # Recover the pre-offset ellipsoidal source so Z_Ellipsoidal keeps the same
    # semantics as the pipeline's enrich step (idempotent re-derivation).
    z_source = [z - z_offset for z in z_stored]

    try:
        z_navd88, separation = ellipsoidal_to_orthometric(lons, lats, z_source, model=geoid_model)
    except GeoidTransformError as e:
        logger.error(f"Geoid conversion failed — nothing written: {e}",
                     error_type=GeoidTransformError, indent=1)
        return None
    except ImportError as e:
        logger.error(
            f"pyproj is required for the geoid conversion but could not be imported — "
            f"nothing written: {e}", error_type=ImportError, indent=1
        )
        return None

    z_fixed = z_navd88 + z_offset
    result.fixed = len(oids)
    result.separation_min = float(separation.min())
    result.separation_max = float(separation.max())
    fixed_by_oid = {
        oid: (float(zf), float(src)) for oid, zf, src in zip(oids, z_fixed, z_source)
    }
    result.samples = [
        (oid, before, fixed_by_oid[oid][0]) for oid, before in zip(oids[:5], z_stored[:5])
    ]

    logger.info(
        f"{result.fixed:,} row(s) to convert via {geoid_model}: "
        f"stored Z [{min(z_stored):.2f}, {max(z_stored):.2f}] m -> "
        f"fixed Z [{z_fixed.min():.2f}, {z_fixed.max():.2f}] m "
        f"(N: min {result.separation_min:.2f}, max {result.separation_max:.2f} m; "
        f"lever-arm offset {z_offset:.3f} m preserved).", indent=1
    )

    if dry_run:
        logger.warning(
            f"DRY RUN: {result.fixed:,} row(s) would be converted. "
            "Re-run with Dry Run unchecked to apply.", indent=1
        )
        return result

    # ---- Pass 2: write ------------------------------------------------------
    if not has_ellip_field:
        arcpy.management.AddField(
            oid_fc, ELLIPSOIDAL_Z_FIELD, "DOUBLE",
            field_alias="Ellipsoidal Z (WGS84, m)"
        )

    update_fields = [
        "OID@", "SHAPE@X", "SHAPE@Y", "SHAPE@Z", "Z", "CameraOrientation",
        "CameraHeading", "CameraPitch", "CameraRoll", ELLIPSOIDAL_Z_FIELD,
    ]
    written = 0
    with cfg.get_progressor(total=result.fixed, label="Fixing OID elevations") as progressor:
        with arcpy.da.UpdateCursor(oid_fc, update_fields) as cursor:
            for row in cursor:
                converted = fixed_by_oid.get(row[0])
                if converted is None:
                    continue
                new_z, z_ellip_src = converted
                x, y = row[1], row[2]
                heading, pitch, roll = row[6], row[7], row[8]
                row[3] = new_z
                row[4] = new_z
                if heading is not None and pitch is not None and roll is not None:
                    row[5] = (
                        f"1|{h_wkid}|{v_wkid}|{x:.6f}|{y:.6f}|{new_z:.3f}"
                        f"|{heading:.1f}|{pitch:.1f}|{roll:.1f}"
                    )
                else:
                    logger.warning(
                        f"OID {row[0]}: missing heading/pitch/roll — Z fixed but "
                        "CameraOrientation left unchanged.", indent=2
                    )
                row[9] = z_ellip_src
                cursor.updateRow(row)
                written += 1
                progressor.update(written)

    logger.success(
        f"Converted {written:,} camera height(s) to NAVD88 ({geoid_model}); original "
        f"ellipsoidal values preserved in {ELLIPSOIDAL_Z_FIELD}.", indent=1
    )
    return result


def _service_identity(oid_fc: str) -> tuple:
    """Derive ``(service_name, is_aws_copy)`` from an OID path. A trailing ``_aws``
    marks the prepared delivery copy produced by Generate OID Service; the
    published service name is the basename WITHOUT that suffix, so fixing either
    the source or the *_aws copy targets the same portal items on republish."""
    import os

    oid_name = os.path.splitext(os.path.basename(oid_fc))[0]
    if oid_name.endswith("_aws"):
        return oid_name[: -len("_aws")], True
    return oid_name, False


def _preflight_republish(cfg: ConfigManager, oid_fc: str, is_aws_copy: bool) -> list:
    """Check everything Generate OID Service needs BEFORE any portal item is deleted.

    The overwrite has to delete the old items first (portal rejects a duplicate
    service name), so a publish failure after that point leaves no service at all.
    This catches the predictable causes up front. Returns a list of problems;
    empty means OK to proceed. Read-only.
    """
    problems = []
    try:
        cfg.validate(tool="generate_oid_service")
    except Exception as e:
        problems.append(f"Config fails Generate OID Service validation: {e}")

    secured = is_secured_storage_enabled(cfg)
    if not (resolve_oid_target_bucket(cfg, secured_mode=secured)
            and resolve_oid_target_region(cfg, secured_mode=secured)):
        problems.append("No target bucket/region resolves from the config (aws.*).")
    if secured and not str(cfg.get("aws.secured_delivery.cloud_store_name", "")).strip():
        problems.append("Secured delivery is enabled but aws.secured_delivery.cloud_store_name is empty.")

    if not arcpy.Exists(oid_fc):
        problems.append(f"OID does not exist: {oid_fc}")
        return problems

    rows = unparseable = local = 0
    with arcpy.da.SearchCursor(oid_fc, ["ImagePath"]) as cursor:
        for (image_path,) in cursor:
            rows += 1
            if not image_path or not extract_filename_from_image_path(image_path):
                unparseable += 1
            elif is_aws_copy and _LOCAL_PATH_RE.match(image_path):
                local += 1
    if rows == 0:
        problems.append("OID has no rows to publish.")
    if unparseable:
        problems.append(f"{unparseable:,} row(s) have an empty or unparseable ImagePath.")
    if local:
        problems.append(
            f"{local:,} ImagePath(s) in the *_aws copy are still LOCAL paths — it is not a "
            "prepared delivery copy. Republish from the source OID instead."
        )
    return problems


def _find_existing_service_items(gis, service_name: str, logger) -> list:
    """Portal items left by a previous publish of ``service_name`` (the hosted
    Feature Service and its Oriented Imagery Layer item). Exact-title,
    owner-scoped match only. Returns ``[(item, item_type), ...]``."""
    found = []
    me = gis.users.me.username
    for item_type in ("Oriented Imagery Layer", "Feature Service"):
        try:
            hits = gis.content.search(
                query=f'title:"{service_name}" AND owner:{me}', item_type=item_type, max_items=25
            )
        except Exception as e:
            logger.warning(f"Portal search for existing {item_type} failed: {e}", indent=2)
            continue
        found.extend((item, item_type) for item in hits if item.title == service_name)
    return found


def _delete_existing_service_items(gis, service_name: str, logger) -> list:
    """Delete the items found by ``_find_existing_service_items``. Logs each
    item's id and URL so a failed republish can be traced/recovered. Returns
    ``[(title, item_type, id, url), ...]`` for the deleted items."""
    deleted = []
    for item, item_type in _find_existing_service_items(gis, service_name, logger):
        ident = (item.title, item_type, getattr(item, "id", "?"), getattr(item, "url", None) or "")
        try:
            item.delete()
        except Exception as e:
            already = "; ".join(f"{t} ({ty}) id={i}" for t, ty, i, _ in deleted) or "none"
            logger.error(
                f"Failed to delete existing portal item '{item.title}' ({item_type}): {e}. "
                f"Already deleted: {already}. Nothing was published.",
                error_type=RuntimeError, indent=2
            )
        deleted.append(ident)
        logger.info(f"Deleted existing portal item: {ident[0]} ({item_type}) id={ident[2]} {ident[3]}", indent=2)
    return deleted


def preview_service_overwrite(cfg: ConfigManager, oid_fc: str) -> None:
    """Read-only dry-run preview of the republish step: lists the portal items an
    overwrite republish would delete. Never deletes or publishes anything."""
    from arcgis.gis import GIS

    logger = cfg.get_logger()
    service_name, is_aws_copy = _service_identity(oid_fc)
    if is_aws_copy:
        logger.info(
            f"Input is a prepared *_aws delivery copy — it would be published "
            f"directly (no re-copy/ImagePath rewrite) as service '{service_name}'.", indent=2
        )
    problems = _preflight_republish(cfg, oid_fc, is_aws_copy)
    if problems:
        logger.warning("Republish preflight would FAIL (nothing would be deleted):", indent=2)
        for problem in problems:
            logger.warning(f"  - {problem}", indent=3)
    else:
        logger.info("Republish preflight passed.", indent=2)

    try:
        gis = GIS("pro")
    except Exception as e:
        logger.warning(f"Republish preview unavailable (no portal connection): {e}", indent=2)
        return

    found = _find_existing_service_items(gis, service_name, logger)
    if found:
        logger.info(f"Republish would DELETE {len(found)} portal item(s), then publish '{service_name}':", indent=2)
        for item, item_type in found:
            logger.info(f"  - {item.title} ({item_type}) id={getattr(item, 'id', '?')}", indent=3)
    else:
        logger.info(f"Republish would publish '{service_name}' fresh (no existing portal items found).", indent=2)


def republish_oid_service(cfg: ConfigManager, oid_fc: str) -> None:
    """Republish the OID as a hosted service, overwriting a previous publish.

    Runs a read-only preflight first and aborts — deleting nothing — if the
    publish would predictably fail. Then removes the existing portal items for
    this OID's service name (exact title match, owned by the signed-in user;
    portal rejects a duplicate service name, so they must go first) and publishes:
    - source OID input: standard Generate OID Service flow (duplicate to *_aws,
      rewrite ImagePaths, publish). NOTE: this regenerates the *_aws copy from
      the source — if the published copy was thinned/subset separately, fix and
      republish that *_aws copy instead.
    - *_aws copy input: published directly under the service name WITHOUT the
      suffix (no re-copy, no ImagePath rewrite — the copy is already in
      delivery form).
    The S3 objects themselves are untouched — only the service/portal side changes.
    """
    from arcgis.gis import GIS

    from utils.generate_oid_service import generate_oid_service

    logger = cfg.get_logger()
    service_name, is_aws_copy = _service_identity(oid_fc)

    logger.custom(f"Republishing OID service '{service_name}' (overwrite)...", emoji="🌐", indent=1)
    if is_aws_copy:
        logger.info("Input is a prepared *_aws delivery copy — publishing it directly.", indent=2)

    problems = _preflight_republish(cfg, oid_fc, is_aws_copy)
    if problems:
        for problem in problems:
            logger.error(f"Preflight: {problem}", indent=2)
        logger.error(
            "Republish aborted before deleting anything — the existing service is untouched.",
            error_type=RuntimeError, indent=1
        )
        return

    try:
        gis = GIS("pro")
    except Exception as e:
        logger.error(f"Could not connect to portal via ArcGIS Pro sign-in: {e}",
                     error_type=RuntimeError, indent=1)
        return

    deleted = _delete_existing_service_items(gis, service_name, logger)
    if not deleted:
        logger.info(f"No existing portal items named '{service_name}' found — publishing fresh.", indent=2)

    try:
        generate_oid_service(
            cfg=cfg, oid_fc=oid_fc, service_name=service_name, prepare_copy=not is_aws_copy
        )
    except Exception:
        if deleted:
            logger.error(
                f"Publish FAILED after the previous '{service_name}' items were deleted — the "
                "service is currently unavailable. Deleted: "
                + "; ".join(f"{t} ({ty}) id={i}" for t, ty, i, _ in deleted)
                + ". Fix the error above, then re-run this tool with Republish (already-fixed "
                "rows are skipped) or run Generate OID Service on this OID.", indent=1
            )
        raise
