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
from typing import Optional

from utils.manager.config_manager import ConfigManager
from utils.shared.expression_utils import resolve_expression


def get_located_points(oid_fc: str, centerline_fc: str, route_id_field:str, logger) -> dict:
    """
    Finds the route identifier and milepost value for each point in the OID feature class by projecting it to the
    centerline's spatial reference and locating features along routes.

    Projects the input feature class to match the centerline's spatial reference, computes a suitable search tolerance
    based on the maximum distance from points to routes, and uses ArcPy's LocateFeaturesAlongRoutes to associate each
    point with its nearest route and milepost value.

    Returns:
        dict: A mapping from each object ID (OID) to a dictionary with 'route_id' and 'mp_value' keys.
    """
    try:

        # Get target spatial reference
        route_sr = arcpy.Describe(centerline_fc).spatialReference

        # Add a join field that combines Reel and Frame for unique identification BEFORE projecting
        arcpy.management.AddField(oid_fc, "JOIN_KEY", "TEXT", field_length=20, field_alias="Reel_Frame Join Key")

        # Populate the join key field with "Reel_Frame" format
        with arcpy.da.UpdateCursor(oid_fc, ["Reel", "Frame", "JOIN_KEY"]) as cursor:
            for row in cursor:
                reel = row[0] if row[0] else "UNKNOWN"
                frame = row[1] if row[1] else "UNKNOWN"
                row[2] = f"{reel}_{frame}"
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
            logger.debug(f"📍 Linear referencing input diagnostics:", indent=2)
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
                logger.debug(f"   • Sample distances to route:", indent=3)
                for dist_info in sample_distances:
                    logger.debug(f"     - {dist_info}", indent=4)

        arcpy.lr.LocateFeaturesAlongRoutes(
            in_features=projected_oid_fc,
            in_routes=centerline_fc,
            route_id_field=route_id_field,
            radius_or_tolerance=tolerance,
            out_table=oid_table,
            out_event_properties=f"{route_id_field} POINT MP",
            route_locations="FIRST",
            distance_field="NO_DISTANCE",
            in_fields="FIELDS"  # Include all fields from input features
        )

        if logger:
            # Count output records for debugging
            output_count = int(arcpy.GetCount_management(oid_table)[0])
            logger.debug(f"📍 LocateFeaturesAlongRoutes produced {output_count} records", indent=2)

        # Parse result table into a dict using JOIN_KEY, then map back to OBJECTIDs
        join_key_to_loc = {}
        total_located = 0
        invalid_mp_values = []
        sample_values = []  # For debugging - collect sample of MP values
        null_mp_join_keys = []   # Track join keys that got NULL MP values from LocateFeaturesAlongRoutes
        with arcpy.da.SearchCursor(oid_table, [route_id_field, "MP", "JOIN_KEY"]) as cursor:
            for route_id_val, mp, join_key in cursor:
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
                        except (ValueError, TypeError) as e:
                            invalid_mp_values.append(f"JOIN_KEY {join_key}: '{mp}' ({type(mp).__name__})")
                            cleaned_mp = None

                join_key_to_loc[join_key] = {"route_id": route_id_val, "mp_value": cleaned_mp}
                if cleaned_mp is not None:
                    total_located += 1

                # Collect sample for debugging (first 5 records)
                if len(sample_values) < 5:
                    sample_values.append(f"JOIN_KEY {join_key}: {repr(mp)} -> {cleaned_mp}")

        # Now map the join_key results back to OBJECTIDs
        oid_to_loc = {}
        with arcpy.da.SearchCursor(oid_fc, ["OBJECTID", "JOIN_KEY"]) as cursor:
            for oid, join_key in cursor:
                if join_key in join_key_to_loc:
                    oid_to_loc[oid] = join_key_to_loc[join_key]

        if logger:
            logger.info(f"📏 Linear referencing results: {total_located}/{len(oid_to_loc)} images located along route", indent=2)

            # Show sample of MP values for debugging
            if sample_values:
                logger.debug(f"Sample MP values from locate operation:", indent=2)
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
                logger.debug(f"Investigating NULL join key distances to route:", indent=3)
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


from typing import List, Dict, Any, Tuple

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

    # 🔁 Only run linear referencing if requested
    oid_to_loc = {}
    if enable_linear_ref and centerline_fc and route_id_field:
        oid_to_loc = get_located_points(oid_fc_path, centerline_fc, route_id_field, logger)

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

