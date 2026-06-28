# =============================================================================
# 🧭 Linear Referencing + Custom Attribute Updater (utils/update_linear_and_custom.py)
# -----------------------------------------------------------------------------
# Purpose:             Assigns route ID, milepost, and custom fields to OID features using config-driven expressions
# Project:             RMI 360 Imaging Workflow Python Toolbox
# Version:             1.1.0
# Author:              RMI Valuation, LLC
# Created:             2025-05-13
# Last Updated:        2025-05-20
#
# Description:
#   Performs linear referencing of image points against an M-enabled centerline using LocateFeaturesAlongRoutes.
#   Updates route and MP fields as well as user-defined custom fields from config expressions.
#   Supports dynamic expression evaluation and field type coercion with warning messaging on failure.
#
# File Location:        /utils/update_linear_and_custom.py
# Validator:            /utils/validators/update_linear_and_custom_validator.py
# Called By:            tools/update_linear_and_custom_tool.py, orchestrator
# Int. Dependencies:    utils.manager.config_manager, utils.shared.expression_utils
# Ext. Dependencies:    arcpy, typing
#
# Documentation:
#   See: docs_legacy/TOOL_GUIDES.md and docs_legacy/tools/update_linear_and_custom.md
#
# Notes:
#   - Automatically projects OID to match centerline SR for referencing
#   - Supports optional disabling of linear referencing via config/tool parameter
# =============================================================================

__all__ = ["update_linear_and_custom"]

import arcpy
from datetime import datetime
from typing import Optional, List, Dict, Any, Tuple

from utils.manager.config_manager import ConfigManager
from utils.shared.expression_utils import resolve_expression
from utils.shared.manifest_fields import (
    load_manifest_attr_map,
    populate_oid_fields_from_manifest,
    resolve_manifest_path,
)
from utils.shared.oid_storage_paths import extract_filename_from_image_path


def _linear_field_manifest_spec(cfg: ConfigManager, key: str):
    """Return ``(oid_field_name, manifest_column, None, field_type)`` for a single
    linear-ref field (by config key) that declares a ``manifest_field``, else None."""
    field = (cfg.get("oid_schema_template.linear_ref_fields", {}) or {}).get(key, {})
    manifest_col = field.get("manifest_field")
    if field.get("name") and manifest_col:
        return (field.get("name"), str(manifest_col), None, field.get("type"))
    return None


def _event_allowed(route_id_val, join_key, intended_route_by_join_key) -> bool:
    """Whether a LocateFeaturesAlongRoutes event may be considered for a point.

    With no intended-route map (non-manifest), all events are allowed (classic
    nearest-event behavior). In relocate mode, an event is allowed only if its route
    matches the point's intended subdivision (or the point has no intended entry)."""
    if intended_route_by_join_key is None:
        return True
    intended = intended_route_by_join_key.get(join_key)
    return intended is None or str(route_id_val) == str(intended)


def _build_intended_route_map(cfg: ConfigManager, oid_fc_path: str, manifest_path: str,
                              intended_col: str, logger) -> dict:
    """Map JOIN_KEY (``OID_<objectid>``) -> intended subdivision id, by joining the
    manifest's ``intended_col`` (mp_pre) to each OID row by image filename."""
    import arcpy

    attr_map = load_manifest_attr_map(manifest_path, [intended_col], logger)
    col = intended_col.lower()
    out: dict = {}
    total = 0
    with arcpy.da.SearchCursor(oid_fc_path, ["OID@", "ImagePath"]) as cursor:
        for oid, image_path in cursor:
            total += 1
            filename = extract_filename_from_image_path(image_path)
            rec = attr_map.get(filename.lower()) if filename else None
            if rec and rec.get(col):
                out[f"OID_{oid}"] = rec[col]
    if total and not out:
        # Join keys on the ORIGINAL filename, so this must run before Rename Images.
        logger.error(
            f"No OID image name matched the manifest (of {total:,}) for linear relocation. "
            "Update Linear must run BEFORE Rename Images — check step order or the manifest path.",
            error_type=RuntimeError, indent=1,
        )
    return out


def get_located_points(oid_fc: str, centerline_fc: str, route_id_field: str, logger,
                       intended_route_by_join_key: Optional[Dict[str, Any]] = None) -> dict:
    """
    Finds the route identifier and milepost value for each point in the OID feature class by projecting it to the
    centerline's spatial reference and locating features along routes.

    Projects the input feature class to match the centerline's spatial reference, computes a suitable search tolerance
    based on the maximum distance from points to routes, and uses ArcPy's LocateFeaturesAlongRoutes to associate each
    point with its nearest route and milepost value.

    When ``intended_route_by_join_key`` is provided (manifest/pre-thin "relocate"
    mode), a point's events are restricted to its INTENDED subdivision route — the
    geometrically nearest but wrong-subdivision event is ignored. This is the
    orchestrated equivalent of the corridor per-route Locate (see utils/corridor/
    calc_mp.py). Points whose intended route has no event within tolerance get no
    entry (measure stays null), mirroring calc_mp's beyond-radius behavior. With no
    map (None), behavior is unchanged (nearest event wins).

    Returns:
        dict: A mapping from each object ID (OID) to a dictionary with 'route_id' and 'mp_value' keys.
    """
    try:

        # Get target spatial reference
        route_sr = arcpy.Describe(centerline_fc).spatialReference

        # Ensure JOIN_KEY exists and is populated with a guaranteed-unique key per feature.
        existing_fields = {f.name for f in arcpy.ListFields(oid_fc)}
        if "JOIN_KEY" not in existing_fields:
            arcpy.management.AddField(oid_fc, "JOIN_KEY", "TEXT", field_length=40, field_alias="OID Join Key")

        with arcpy.da.UpdateCursor(oid_fc, ["OID@", "JOIN_KEY"]) as cursor:
            for row in cursor:
                row[1] = f"OID_{row[0]}"
                cursor.updateRow(row)

        # Project OID feature class with the JOIN_KEY field included
        projected_oid_fc = arcpy.CreateUniqueName("projected_oid_fc", arcpy.env.scratchGDB)

        arcpy.management.Project(
            in_dataset=oid_fc,
            out_dataset=projected_oid_fc,
            out_coor_system=route_sr
        )



        # Load all route geometries
        routes = [row[0] for row in arcpy.da.SearchCursor(centerline_fc, ["SHAPE@"])]

        # Compute adaptive tolerance based on max distance from OID points to nearest route
        max_dist = 0
        with arcpy.da.SearchCursor(projected_oid_fc, ["SHAPE@"]) as cursor:
            for (point_geom,) in cursor:
                point = point_geom.centroid
                if not routes:
                    logger.warning("No route geometries found - skipping linear referencing.", indent=1)
                    return {}
                min_dist = min(route.queryPointAndDistance(point, use_percentage=False)[2] for route in routes)
                max_dist = max(max_dist, min_dist)
        tolerance = round(max_dist + 5, 2)

        logger.info(f"📏 Max distance to nearest route: {round(max_dist, 2)} → Using {round(tolerance, 2)} tolerance", indent=1)

        # Perform location along routes
        oid_table = arcpy.CreateUniqueName("oid_temp_table", arcpy.env.scratchGDB)

        if logger:
            # Count input features and log spatial state for debugging
            input_count = int(arcpy.GetCount_management(projected_oid_fc)[0])
            orig_count = int(arcpy.GetCount_management(oid_fc)[0])
            desc = arcpy.Describe(oid_fc)
            logger.debug("📍 Linear referencing input diagnostics:", indent=2)
            logger.debug(f"   • Original features: {orig_count}", indent=3)
            logger.debug(f"   • Projected features: {input_count}", indent=3)
            logger.debug(f"   • Has spatial index: {desc.hasSpatialIndex}", indent=3)
            logger.debug(f"   • Tolerance: {tolerance} (max distance was {round(max_dist, 2)})", indent=3)

            # Sample a few join keys and their distances to route for debugging
            sample_distances = []
            with arcpy.da.SearchCursor(projected_oid_fc, ["JOIN_KEY", "SHAPE@"]) as cursor:
                for i, (join_key, geom) in enumerate(cursor):
                    if i >= 3:  # Just sample first 3
                        break
                    if routes:
                        point = geom.centroid
                        min_dist = min(route.queryPointAndDistance(point, use_percentage=False)[2] for route in routes)
                        sample_distances.append(f"JOIN_KEY {join_key}: {round(min_dist, 2)}m from route")

            if sample_distances:
                logger.debug("   • Sample distances to route:", indent=3)
                for dist_info in sample_distances:
                    logger.debug(f"     - {dist_info}", indent=4)

        arcpy.lr.LocateFeaturesAlongRoutes(
            in_features=projected_oid_fc,
            in_routes=centerline_fc,
            route_id_field=route_id_field,
            radius_or_tolerance=tolerance,
            out_table=oid_table,
            out_event_properties=f"{route_id_field} POINT MP",
            route_locations="ALL",
            distance_field="DISTANCE",
            in_fields="FIELDS"  # Include all fields from input features
        )

        if logger:
            # Count output records for debugging
            output_count = int(arcpy.GetCount_management(oid_table)[0])
            logger.debug(f"📍 LocateFeaturesAlongRoutes produced {output_count} records", indent=2)

        # Parse result table into a dict using JOIN_KEY, selecting the nearest event when
        # multiple routes are returned for a point.
        join_key_to_loc = {}
        total_located = 0
        invalid_mp_values = []
        sample_values = []  # For debugging - collect sample of MP values
        null_mp_join_keys = []   # Track join keys that got NULL MP values from LocateFeaturesAlongRoutes
        with arcpy.da.SearchCursor(oid_table, [route_id_field, "MP", "JOIN_KEY", "DISTANCE"]) as cursor:
            for route_id_val, mp, join_key, distance_val in cursor:
                try:
                    distance_abs = abs(float(distance_val)) if distance_val is not None else float("inf")
                except (TypeError, ValueError):
                    distance_abs = float("inf")

                # Track NULL MP values from LocateFeaturesAlongRoutes
                if mp is None:
                    null_mp_join_keys.append(join_key)

                # Validate and clean MP value
                cleaned_mp = None
                if mp is not None:
                    # Check for various invalid values that LocateFeaturesAlongRoutes might return
                    if isinstance(mp, str):
                        mp = mp.strip()
                        if mp == "" or mp.lower() in ["nan", "null", "none"]:
                            mp = None

                    if mp is not None:
                        try:
                            cleaned_mp = float(mp)
                            # Check for NaN or infinite values
                            if not (cleaned_mp == cleaned_mp and abs(cleaned_mp) != float('inf')):  # NaN check
                                cleaned_mp = None
                                invalid_mp_values.append(f"JOIN_KEY {join_key}: NaN/Inf value")
                        except (ValueError, TypeError):
                            invalid_mp_values.append(f"JOIN_KEY {join_key}: '{mp}' ({type(mp).__name__})")
                            cleaned_mp = None

                # Relocate mode: restrict each point to its intended subdivision route.
                if not _event_allowed(route_id_val, join_key, intended_route_by_join_key):
                    continue  # ignore events on a different (wrong) subdivision

                candidate = {
                    "route_id": route_id_val,
                    "mp_value": cleaned_mp,
                    "distance": distance_abs,
                }

                existing = join_key_to_loc.get(join_key)
                if existing is None or candidate["distance"] < existing["distance"]:
                    join_key_to_loc[join_key] = candidate

                # Collect sample for debugging (first 5 records)
                if len(sample_values) < 5:
                    sample_values.append(
                        f"JOIN_KEY {join_key}: route={route_id_val}, mp={repr(mp)} -> {cleaned_mp}, dist={distance_abs:.2f}"
                    )

        total_located = sum(1 for v in join_key_to_loc.values() if v.get("mp_value") is not None)

        # Now map the join_key results back to OBJECTIDs
        oid_to_loc = {}
        with arcpy.da.SearchCursor(oid_fc, ["OBJECTID", "JOIN_KEY"]) as cursor:
            for oid, join_key in cursor:
                if join_key in join_key_to_loc:
                    oid_to_loc[oid] = {
                        "route_id": join_key_to_loc[join_key].get("route_id"),
                        "mp_value": join_key_to_loc[join_key].get("mp_value"),
                    }

        # Summarize selected route distribution to make multi-route behavior easy to verify.
        route_assignment_counts = {}
        null_route_count = 0
        for loc in oid_to_loc.values():
            route_id_val = loc.get("route_id")
            if route_id_val is None or str(route_id_val).strip() == "":
                null_route_count += 1
                continue
            route_key = str(route_id_val)
            route_assignment_counts[route_key] = route_assignment_counts.get(route_key, 0) + 1

        if logger:
            logger.debug("📍 Route assignment distribution (nearest-event selection):", indent=2)
            if route_assignment_counts:
                for route_key in sorted(route_assignment_counts):
                    logger.debug(f"  • {route_key}: {route_assignment_counts[route_key]} image(s)", indent=3)
            else:
                logger.debug("  • No route assignments were produced.", indent=3)
            if null_route_count:
                logger.debug(f"  • NULL/blank route assignments: {null_route_count}", indent=3)

        if logger:
            logger.info(f"📏 Linear referencing results: {total_located}/{len(oid_to_loc)} images located along route", indent=2)

            # Show sample of MP values for debugging
            if sample_values:
                logger.debug("Sample MP values from locate operation:", indent=2)
                for sample in sample_values:
                    logger.debug(f"  • {sample}", indent=3)

            # Report NULL MP values from LocateFeaturesAlongRoutes
            if null_mp_join_keys:
                logger.warning(f"🚨 LocateFeaturesAlongRoutes returned NULL for {len(null_mp_join_keys)} join keys:", indent=2)
                if len(null_mp_join_keys) <= 10:
                    logger.warning(f"  NULL MP join keys: {sorted(null_mp_join_keys)}", indent=3)
                else:
                    sample_nulls = sorted(null_mp_join_keys)[:5]
                    logger.warning(f"  Sample NULL MP join keys: {sample_nulls} (and {len(null_mp_join_keys)-5} more)", indent=3)

                # Check distances for NULL join keys to see if they're within tolerance
                logger.debug("Investigating NULL join key distances to route:", indent=3)
                routes = [row[0] for row in arcpy.da.SearchCursor(centerline_fc, ["SHAPE@"])]
                null_distances = []
                if null_mp_join_keys[:5]:  # Only if we have NULL join keys to investigate
                    join_key_list = "','".join(null_mp_join_keys[:5])
                    with arcpy.da.SearchCursor(projected_oid_fc, ["JOIN_KEY", "SHAPE@"], where_clause=f"JOIN_KEY IN ('{join_key_list}')") as cursor:
                        for join_key, geom in cursor:
                            if routes and geom:
                                point = geom.centroid
                                min_dist = min(route.queryPointAndDistance(point, use_percentage=False)[2] for route in routes)
                                null_distances.append(f"JOIN_KEY {join_key}: {round(min_dist, 2)}m (tolerance: {round(tolerance, 2)}m)")

                if null_distances:
                    for dist_info in null_distances:
                        logger.debug(f"  • {dist_info}", indent=4)

            if invalid_mp_values:
                logger.warning(f"Found {len(invalid_mp_values)} invalid MP values:", indent=2)
                for invalid_msg in invalid_mp_values[:5]:  # Show first 5
                    logger.warning(f"  • {invalid_msg}", indent=3)
                if len(invalid_mp_values) > 5:
                    logger.warning(f"  • ... and {len(invalid_mp_values) - 5} more", indent=3)

        return oid_to_loc

    except Exception as e:
        logger.warning(f"Linear referencing failed: {e}", indent=1)
        return {}

def compute_linear_and_custom_updates(
    cfg: ConfigManager,
    row: List[Any],
    update_fields: List[str],
    linear_fields: Dict,
    custom_field_defs: List[Tuple[str, str, str, str]],
    oid_to_loc: Dict,
    enable_linear_ref: bool,
    logger=None
) -> Tuple[List[Any], bool]:
    """
    Given a row and config, return the updated row and a boolean indicating if it was changed.
    """
    update = False
    context = dict(zip(update_fields, row))
    oid = row[0]
    # Linear reference updates
    if enable_linear_ref:
        loc = oid_to_loc.get(oid)
        route_id = mp_value = None
        if loc:
            route_id = loc.get("route_id")
            mp_value = loc.get("mp_value")
        for key, field_def in linear_fields.items():
            field_name = field_def.get("name")
            if key == "route_identifier":
                value = route_id
            elif key == "route_measure":
                value = mp_value
            else:
                continue

            # Skip update if value is None (failed to locate along route)
            if value is None:
                continue

            idx = update_fields.index(field_name)
            if field_def["type"] == "DOUBLE":
                try:
                    value = float(value)
                except (ValueError, TypeError):
                    if logger:
                        logger.warning(f"OID {oid}: Could not convert {field_name} value '{value}' (type: {type(value).__name__}) to float", indent=2)
                        # Log additional context for debugging
                        logger.debug(f"  Raw mp_value from locate: {repr(mp_value)}", indent=3)
                        logger.debug(f"  Route ID: {route_id}", indent=3)
                    value = None
            row[idx] = value
            update = True
    # Custom field updates
    for _, target_field, expression, field_type in custom_field_defs:
        try:
            # resolve_expression may raise
            value = resolve_expression(expression, cfg, row=context)
            if field_type == "DOUBLE":
                try:
                    value = float(value)
                except (ValueError, TypeError):
                    if logger:
                        logger.warning(f"Could not convert value for {target_field} to float.", indent=2)
                    continue
            row[update_fields.index(target_field)] = value
            update = True
        except Exception as e:
            if logger:
                logger.warning(f"Failed to resolve expression for {target_field}: {e}", indent=2)
    return row, update

def update_linear_and_custom(
        cfg: ConfigManager,
        oid_fc_path: str,
        centerline_fc: Optional[str] = None,
        route_id_field: Optional[str] = None,
        enable_linear_ref: bool = True):
    """
    Updates linear referencing and custom attribute fields for an Oriented Imagery Dataset feature class.

    If linear referencing is enabled, locates each image point along M-enabled centerlines and updates route identifier
    and milepost fields. Also evaluates and updates custom attribute fields based on configured expressions.

    Args:
        cfg: ConfigManager instance (must be validated).
        oid_fc_path: Path to the OID feature class.
        centerline_fc: Path to centerline routes (optional).
        route_id_field: Field name used for route matching (if linear ref is enabled).
        enable_linear_ref: Whether to compute linear route measures.
    """
    logger = cfg.get_logger()
    cfg.validate(tool="update_linear_and_custom")

    # Load linear field definitions
    linear_fields = cfg.get("oid_schema_template.linear_ref_fields", {}) if enable_linear_ref else {}
    route_id_field_config = cfg.get("oid_schema_template.linear_ref_fields.route_identifier.name")
    route_meas_field_config = cfg.get("oid_schema_template.linear_ref_fields.route_measure.name")
    linear_field_names = [route_id_field_config, route_meas_field_config] if enable_linear_ref else []

    # Load custom field definitions
    custom_fields = cfg.get("oid_schema_template.custom_fields", {})
    custom_field_defs = [
        (key, field["name"], field.get("expression"), field.get("type"))
        for key, field in custom_fields.items()
        if "expression" in field
    ]
    custom_field_names = [name for _, name, _, _ in custom_field_defs]

    update_fields = ["OID@"] + linear_field_names + custom_field_names

    # Resolve manifest mode (pre-thin). MP_Pre always comes from the manifest's
    # intended subdivision; MP_Num source is controlled by mp_num_source.
    manifest_path = resolve_manifest_path(cfg)
    id_spec = _linear_field_manifest_spec(cfg, "route_identifier")
    meas_spec = _linear_field_manifest_spec(cfg, "route_measure")
    manifest_mode = bool(manifest_path) and id_spec is not None
    mp_num_source = str(cfg.get("corridor_thinning.manifest.mp_num_source", "relocate")).lower()
    can_relocate = bool(enable_linear_ref and centerline_fc and route_id_field)
    relocate_mode = manifest_mode and mp_num_source == "relocate" and can_relocate

    # In relocate mode, constrain linear referencing to each image's intended route.
    intended_route_by_jk = None
    if relocate_mode:
        intended_route_by_jk = _build_intended_route_map(cfg, oid_fc_path, manifest_path, id_spec[1], logger)
        logger.info(
            f"Manifest relocate mode: constraining linear referencing to intended subdivision "
            f"for {len(intended_route_by_jk):,} image(s).",
            indent=1,
        )

    # 🔁 Only run linear referencing if requested
    oid_to_loc = {}
    if enable_linear_ref and centerline_fc and route_id_field:
        oid_to_loc = get_located_points(
            oid_fc_path, centerline_fc, route_id_field, logger,
            intended_route_by_join_key=intended_route_by_jk,
        )

    row_count = int(arcpy.management.GetCount(oid_fc_path)[0])

    # Update records
    updated_oids = set()
    failed_oids = set()
    skipped_mp_oids = set()  # Track OIDs that couldn't be assigned MP values
    with cfg.get_progressor(total=row_count, label="Updating linear/custom fields") as progressor:
        with arcpy.da.UpdateCursor(oid_fc_path, update_fields) as cursor:
            for i, row in enumerate(cursor, start=1):
                oid = row[0]
                try:
                    new_row, update = compute_linear_and_custom_updates(
                        cfg=cfg,
                        row=list(row),
                        update_fields=update_fields,
                        linear_fields=linear_fields,
                        custom_field_defs=custom_field_defs,
                        oid_to_loc=oid_to_loc,
                        enable_linear_ref=enable_linear_ref,
                        logger=logger
                    )
                    if update:
                        cursor.updateRow(new_row)
                        updated_oids.add(oid)

                    # Check if MP_Num assignment was skipped (only if linear referencing is enabled)
                    if enable_linear_ref:
                        if oid not in oid_to_loc:
                            # OID not found in linear referencing results at all
                            skipped_mp_oids.add(oid)
                        elif oid_to_loc[oid].get("mp_value") is None:
                            # OID found but MP value is None
                            skipped_mp_oids.add(oid)
                except Exception as e:
                    failed_oids.add(oid)
                    logger.error(f"Failed to update OID {oid}: {e}", indent=2)
                progressor.update(i)
    logger.success(f"Updated {len(updated_oids)} feature(s) with linear and custom attributes." + (f" Failed to update {len(failed_oids)} OIDs." if failed_oids else ""), indent=1)

    # Report MP assignment results
    if enable_linear_ref and skipped_mp_oids:
        logger.warning(f"⚠️ Skipped MP assignment for {len(skipped_mp_oids)} feature(s) - MP values were None", indent=1)
        if len(skipped_mp_oids) <= 10:
            logger.debug(f"Skipped MP OIDs: {sorted(skipped_mp_oids)}", indent=2)
        else:
            sample_skipped = sorted(skipped_mp_oids)[:5]
            logger.debug(f"Sample skipped MP OIDs: {sample_skipped} (and {len(skipped_mp_oids)-5} more)", indent=2)

    if updated_oids:
        logger.debug(f"Updated OIDs: {sorted(updated_oids)}", indent=2)
    if failed_oids:
        logger.warning(f"Failed OIDs: {sorted(failed_oids)}", indent=2)

    # Manifest linear-ref reconciliation (pre-thin). MP_Pre is always set from the
    # manifest's intended subdivision. MP_Num is either re-measured along that route
    # (relocate mode, handled above by constraining the Locate) or taken from the
    # manifest's mp_meas. No-op without a manifest, so non-manifest runs are unchanged.
    if manifest_mode:
        if relocate_mode:
            # Locate already produced the intended-route measure; here we only ensure
            # MP_Pre = intended for every manifest image (incl. those beyond radius).
            specs = [id_spec]
        else:
            if mp_num_source == "relocate" and not can_relocate:
                logger.warning(
                    "mp_num_source='relocate' but no centerline/linear ref available; "
                    "taking MP_Num from the manifest (mp_meas) instead.",
                    indent=1,
                )
            specs = [s for s in (id_spec, meas_spec) if s]
        logger.info(
            f"Applying manifest linear-ref values ({'MP_Pre only, relocate measure' if relocate_mode else mp_num_source})...",
            indent=1,
        )
        populate_oid_fields_from_manifest(cfg, oid_fc_path, specs, manifest_path, logger)

    assign_sequence_order(cfg, oid_fc_path, enable_linear_ref, logger)


def _parse_datetime_sort_key(value):
    if value is None:
        return (1, datetime.max)
    if isinstance(value, datetime):
        return (0, value)
    if isinstance(value, str):
        text = value.strip()
        if not text:
            return (1, datetime.max)
        try:
            return (0, datetime.fromisoformat(text.replace("Z", "+00:00")))
        except ValueError:
            return (1, datetime.max)
    return (1, datetime.max)


def _resolve_prefix_rank(prefix: str, ordered_prefixes: list[str]) -> tuple[int, str]:
    normalized = (prefix or "").strip()
    if normalized in ordered_prefixes:
        return (ordered_prefixes.index(normalized), normalized)
    return (len(ordered_prefixes), normalized)


def assign_sequence_order(cfg: ConfigManager, oid_fc_path: str, enable_linear_ref: bool, logger) -> None:
    """Populate SequenceOrder when enabled by config.

    SequenceOrder remains null when disabled. Ordering behavior:
      - LR enabled: grouped by MP_Pre, sorted by MP_Num within group.
      - LR disabled: sorted by AcquisitionDate only.
    """
    sequence_cfg = cfg.get("sequence_order", {})
    if not sequence_cfg.get("enabled", False):
        logger.info("SequenceOrder population disabled by config; leaving values as-is.", indent=1)
        return

    sequence_field = cfg.get("sequence_order.field_name", "SequenceOrder")
    available_fields = {f.name for f in arcpy.ListFields(oid_fc_path)}
    if sequence_field not in available_fields:
        logger.warning(f"{sequence_field} field not present; skipping SequenceOrder population.", indent=1)
        return

    acquisition_field = cfg.get("sequence_order.acquisition_datetime_field", "AcquisitionDate")
    prefix_field = cfg.get("sequence_order.lr_prefix_field", cfg.get("oid_schema_template.linear_ref_fields.route_identifier.name", "MP_Pre"))
    mile_field = cfg.get("sequence_order.lr_mile_field", cfg.get("oid_schema_template.linear_ref_fields.route_measure.name", "MP_Num"))
    ordered_prefixes = cfg.get("sequence_order.prefix_order", []) or []
    descending_prefixes = set(cfg.get("sequence_order.descending_prefixes", []) or [])
    null_milepost_position = (cfg.get("sequence_order.null_milepost_position", "end") or "end").lower()

    use_lr_ordering = bool(enable_linear_ref and prefix_field in available_fields and mile_field in available_fields)
    if enable_linear_ref and not use_lr_ordering:
        logger.warning(
            f"SequenceOrder LR ordering requested, but required fields are missing ({prefix_field}, {mile_field}). Falling back to acquisition datetime ordering.",
            indent=1,
        )

    search_fields = ["OID@", acquisition_field]
    if use_lr_ordering:
        search_fields.extend([prefix_field, mile_field])

    rows = []
    with arcpy.da.SearchCursor(oid_fc_path, search_fields) as cursor:
        for row in cursor:
            entry = {
                "oid": row[0],
                "acq": row[1],
                "prefix": "",
                "mile": None,
            }
            if use_lr_ordering:
                entry["prefix"] = "" if row[2] is None else str(row[2]).strip()
                entry["mile"] = row[3]
            rows.append(entry)

    if not rows:
        logger.warning("No rows found for SequenceOrder assignment.", indent=1)
        return

    if use_lr_ordering:
        null_mile_count = sum(1 for r in rows if r["mile"] is None)
        if null_mile_count:
            logger.warning(
                f"Found {null_mile_count} row(s) with null milepost while assigning SequenceOrder. Rows will be placed deterministically by configured null position.",
                indent=1,
            )

        # lr_sort_key rule: NULL mileposts map to +/-infinity from
        # null_milepost_position, and descending_prefixes only negates finite
        # mile_sort values. For descending prefixes, NULL mileposts still remain
        # at the configured null_milepost_position (they are not inverted).
        def lr_sort_key(item):
            prefix = item["prefix"]
            prefix_rank = _resolve_prefix_rank(prefix, ordered_prefixes)
            desc = prefix in descending_prefixes
            mile = item["mile"]

            if mile is None:
                null_rank = 1 if null_milepost_position == "end" else -1
                mile_sort = float("inf") if null_milepost_position == "end" else float("-inf")
            else:
                null_rank = 0
                try:
                    mile_sort = float(mile)
                except (TypeError, ValueError):
                    null_rank = 1 if null_milepost_position == "end" else -1
                    mile_sort = float("inf") if null_milepost_position == "end" else float("-inf")

            if desc and mile_sort not in (float("inf"), float("-inf")):
                mile_sort = -mile_sort

            return (
                prefix_rank,
                null_rank,
                mile_sort,
                _parse_datetime_sort_key(item["acq"]),
                item["oid"],
            )

        ordered_rows = sorted(rows, key=lr_sort_key)
    else:
        ordered_rows = sorted(rows, key=lambda item: (_parse_datetime_sort_key(item["acq"]), item["oid"]))

    sequence_by_oid = {entry["oid"]: i for i, entry in enumerate(ordered_rows, start=1)}

    updated = 0
    with arcpy.da.UpdateCursor(oid_fc_path, ["OID@", sequence_field]) as cursor:
        for oid, existing in cursor:
            desired = sequence_by_oid.get(oid)
            if desired is None or existing == desired:
                continue
            cursor.updateRow([oid, desired])
            updated += 1

    logger.success(
        f"Assigned {sequence_field} for {updated} row(s) using {'LR-aware' if use_lr_ordering else 'acquisition datetime'} ordering.",
        indent=1,
    )

