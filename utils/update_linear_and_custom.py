__all__ = ["update_linear_and_custom"]

import arcpy
from typing import Optional
from utils.config_loader import resolve_config
from utils.arcpy_utils import log_message
from utils.expression_utils import resolve_expression


def get_located_points(oid_fc, centerline_fc, route_id_field, messages=None):
    """
    Finds the route identifier and milepost value for each point in the OID feature class by projecting it to the
    centerline's spatial reference and locating features along routes.
    
    Projects the input feature class to match the centerline's spatial reference, computes a suitable search tolerance
    based on the maximum distance from points to routes, and uses ArcPy's LocateFeaturesAlongRoutes to associate each
    point with its nearest route and milepost value.
    
    Returns:
        dict: A mapping from each object ID (OID) to a dictionary with 'route_id' and 'mp_value' keys.
    """
    route_sr = arcpy.Describe(centerline_fc).spatialReference
    projected_oid_fc = arcpy.management.Project(
        oid_fc,
        arcpy.CreateUniqueName("projected_oid_fc", arcpy.env.scratchGDB),
        route_sr
    )[0]

    routes = [row[0] for row in arcpy.da.SearchCursor(centerline_fc, ["SHAPE@"])]

    max_dist = 0
    with arcpy.da.SearchCursor(projected_oid_fc, ["SHAPE@"]) as cursor:
        for row in cursor:
            point = row[0].centroid
            min_dist = float("inf")
            for route in routes:
                dist = route.queryPointAndDistance(point, use_percentage=False)[2]
                min_dist = min(min_dist, dist)
            max_dist = max(max_dist, min_dist)
    tolerance = max_dist + 5

    log_message(f"📏 Max queryPointAndDistance: {round(max_dist, 2)} → Using {round(tolerance, 2)} tolerance", messages)

    oid_table = arcpy.CreateUniqueName("oid_temp_table", arcpy.env.scratchGDB)
    arcpy.lr.LocateFeaturesAlongRoutes(
        in_features=projected_oid_fc,
        in_routes=centerline_fc,
        route_id_field=route_id_field,
        radius_or_tolerance=tolerance,
        out_table=oid_table,
        out_event_properties=f"{route_id_field} POINT MP",
        route_locations="FIRST",
        distance_field="NO_DISTANCE",
        in_fields="NO_FIELDS"
    )

    oid_to_loc = {}
    with arcpy.da.SearchCursor(oid_table, [route_id_field, "MP", "OID@"]) as cursor:
        for route_id_val, mp, oid in cursor:
            oid_to_loc[oid] = {"route_id": route_id_val, "mp_value": mp}
    return oid_to_loc


def update_linear_and_custom(
        oid_fc: str,
        centerline_fc: str,
        route_id_field: str,
        enable_linear_ref: bool = True,
        config: Optional[dict] = None,
        config_file: Optional[str] = None,
        messages=None
):
    """
    Updates linear referencing and custom attribute fields for an Oriented Imagery Dataset feature class.

    If linear referencing is enabled, locates each image point along M-enabled centerlines and updates route identifier
    and milepost fields. Also evaluates and updates custom attribute fields based on configured expressions.

    Args:
        oid_fc: Path to the Oriented Imagery Dataset feature class (point features).
        centerline_fc: Path to the M-enabled polyline centerline feature class.
        route_id_field: Name of the field in the centerline used to identify routes.
        enable_linear_ref: If True, performs linear referencing and updates related fields.
        config: Optional configuration dictionary specifying field mappings and expressions.
        config_file: Optional path to a configuration YAML file (used if config is not provided).
        messages: Optional message handler for status and warning output.
    """
    config = resolve_config(
        config=config,
        config_file=config_file,
        oid_fc_path=oid_fc,
        messages=messages,
        tool_name="update_linear_and_custom"
    )

    # Load field definitions
    linear_fields = config.get("oid_schema_template", {}).get("linear_ref_fields", {}) if enable_linear_ref else {}
    custom_fields = config.get("oid_schema_template", {}).get("custom_fields", {})

    # Extract field names for update
    route_id_field_config = linear_fields.get("route_identifier", {}).get("name")
    route_meas_field_config = linear_fields.get("route_measure", {}).get("name")
    linear_field_names = [route_id_field_config, route_meas_field_config] if enable_linear_ref else []

    custom_field_defs = [
        (key, field["name"], field.get("expression"), field.get("type"))
        for key, field in custom_fields.items()
        if "expression" in field
    ]
    custom_field_names = [name for _, name, _, _ in custom_field_defs]

    update_fields = ["OID@"] + linear_field_names + custom_field_names

    # Lookup table only if linear referencing is enabled
    oid_to_loc = get_located_points(oid_fc, centerline_fc, route_id_field, messages) if enable_linear_ref else {}

    # Update records
    with arcpy.da.UpdateCursor(oid_fc, update_fields) as cursor:
        for row in cursor:
            oid = row[0]
            context = oid_to_loc.get(oid, {})  # May be empty if not doing linear ref

            # Update linear reference fields
            if enable_linear_ref:
                for key, field_def in linear_fields.items():
                    field_name = field_def.get("name")
                    value = context.get("route_id" if key == "route_identifier" else "mp_value")
                    idx = update_fields.index(field_name)
                    if field_def["type"] == "DOUBLE":
                        try:
                            value = float(value)
                        except (ValueError, TypeError):
                            log_message(f"⚠️ Warning: Could not convert value for {field_name} to float.", messages,
                                        level="warning", config=config)
                            value = None
                    row[idx] = value

            # Update custom fields from expressions
            for _, field_name, expression, field_type in custom_field_defs:
                idx = update_fields.index(field_name)
                value = resolve_expression(expression, row=context, config=config)
                if field_type == "DOUBLE":
                    try:
                        value = float(value)
                    except (ValueError, TypeError):
                        log_message(f"⚠️ Warning: Could not convert value for {field_name} to float.", messages,
                                    level="warning", config=config)
                        value = None
                row[idx] = value

            cursor.updateRow(row)

    log_message("✅ update_linear_and_custom complete.", messages, config=config)
