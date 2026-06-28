# =============================================================================
# 📍 Corridor 01 — Calculate Mileposts (tools/corridor_calc_mp_tool.py)
# -----------------------------------------------------------------------------
# Tool Name:          CorridorCalcMPTool
# Toolbox Context:    rmi_360_corridor_thinning.pyt
# Version:            1.0.0
# Author:             RMI Valuation, LLC
#
# Description:
#   Per-route Locate Features Along Routes: write mp_meas at full precision for
#   ALL points. Each subdivision's points locate ONLY against its own route, so
#   cross-route snapping at junctions is structurally impossible.
# =============================================================================

import arcpy

from utils.corridor import toolparams as tp
from utils.corridor.calc_mp import calc_mp


class CorridorCalcMPTool(object):
    def __init__(self):
        self.label = "01 - Calculate Mileposts (per-route)"
        self.description = (
            "Per-route Locate Features Along Routes. Writes mp_meas (DOUBLE) for all "
            "points; NULL where a point is beyond the search radius of its own route."
        )
        self.category = tp.CATEGORY

    def getParameterInfo(self):
        points = tp.points_fc_param()
        routes = arcpy.Parameter(
            displayName="Route Centerline (M-enabled)", name="routes_fc",
            datatype="DEFeatureClass", parameterType="Required", direction="Input")
        if routes.filter is not None:
            routes.filter.list = ["Polyline"]
        route_id = tp.field_param("route_id_field", "Route ID Field (on routes)", "routes_fc", default="mp_pre", required=True)
        point_pre = tp.field_param("point_pre_field", "Subdivision Field (on points)", "points_fc", default="mp_pre", required=True)
        meas = tp.string_param("meas_field", "Measure Field (created if missing)", default="mp_meas")
        key = tp.field_param("key_field", "Unique Key Field (on points)", "points_fc", default="Name", required=True)
        radius = tp.linear_unit_param("search_radius", "Search Radius", default="200 Feet")
        return [tp.project_param(), points, routes, route_id, point_pre, meas, key, radius, tp.config_param()]

    def execute(self, parameters, messages):
        project_folder = parameters[0].valueAsText
        points_fc = parameters[1].valueAsText
        routes_fc = parameters[2].valueAsText
        route_id_field = parameters[3].valueAsText or "mp_pre"
        point_pre_field = parameters[4].valueAsText or "mp_pre"
        meas_field = parameters[5].valueAsText or "mp_meas"
        key_field = parameters[6].valueAsText or "Name"
        search_radius = parameters[7].valueAsText or "200 Feet"
        config_file = parameters[8].valueAsText

        cfg = tp.build_cfg(project_folder, config_file, messages)
        calc_mp(
            points_fc=points_fc, routes_fc=routes_fc, route_id_field=route_id_field,
            point_pre_field=point_pre_field, meas_field=meas_field, key_field=key_field,
            search_radius=search_radius, cfg=cfg, messages=messages,
        )
