# =============================================================================
# 🔗 Corridor 09 — Run Corridor Thinning (tools/corridor_orchestrator_tool.py)
# -----------------------------------------------------------------------------
# Tool Name:          CorridorOrchestratorTool
# Toolbox Context:    rmi_360_corridor_thinning.pyt
# Version:            1.0.0
# Author:             RMI Valuation, LLC
#
# Description:
#   Optional chained run of the corridor pipeline end-to-end:
#     Calc MP -> Calc Sequence -> (Detect Reversals) -> QC Sequence -> Find Gaps
#     -> Thin -> QC Thinning -> Export Manifest
#   The granular stage tools remain available to run individually with QC gates;
#   this orchestrator is for when the dataset is already validated.
# =============================================================================

import arcpy

from utils.corridor import toolparams as tp
from utils.corridor.calc_mp import calc_mp
from utils.corridor.calc_sub_order import calc_sub_order
from utils.corridor.detect_reversals import detect_reversals
from utils.corridor.qc_sub_order import qc_sub_order
from utils.corridor.find_gaps import find_gaps
from utils.corridor.thin import thin
from utils.corridor.qc_thin import qc_thin
from utils.corridor.export_manifest import export_manifest


class CorridorOrchestratorTool(object):
    def __init__(self):
        self.label = "09 - Run Corridor Thinning (chained)"
        self.description = (
            "Run the full corridor pipeline end-to-end and export a manifest. Use the "
            "granular tools with QC gates for first-time / unvalidated datasets."
        )
        self.category = tp.CATEGORY

    def getParameterInfo(self):
        points = tp.points_fc_param()
        routes = arcpy.Parameter(
            displayName="Route Centerline (M-enabled)", name="routes_fc",
            datatype="DEFeatureClass", parameterType="Required", direction="Input")
        if routes.filter is not None:
            routes.filter.list = ["Polyline"]
        out = arcpy.Parameter(
            displayName="Output Manifest CSV", name="out_csv",
            datatype="DEFile", parameterType="Required", direction="Output")
        if out.filter is not None:
            out.filter.list = ["csv"]
        route_id = tp.field_param("route_id_field", "Route ID Field (on routes)", "routes_fc", default="mp_pre", required=True)
        radius = tp.linear_unit_param("search_radius", "Search Radius", default="200 Feet")
        eps = tp.number_param("eps_miles", "Tie/near-tie EPS (miles)", default=0.0003)
        threshold = tp.linear_unit_param("threshold", "Thinning Threshold", default="5 Meters")
        trim = tp.linear_unit_param("trim", "Threshold Trim (pull-in)", default="1.5 Meters")
        wkid = tp.number_param("wkid", "Data WKID", default=6455, datatype="GPLong")
        do_reversals = tp.bool_param("run_reversals", "Run Detect Reversals", default=True)
        do_qc = tp.bool_param("run_qc", "Run QC stages", default=True)
        regex = tp.string_param("filename_regex", "Filename Regex",
                                default=r"reel_(\d+)_(\d{8}-\d{6})_.*_(\d+)\.jpg$")
        return [tp.project_param(), points, routes, out, route_id, radius, eps, threshold,
                trim, wkid, do_reversals, do_qc, regex, tp.config_param()]

    def execute(self, parameters, messages):
        project_folder = parameters[0].valueAsText
        points_fc = parameters[1].valueAsText
        routes_fc = parameters[2].valueAsText
        out_csv = parameters[3].valueAsText
        route_id_field = parameters[4].valueAsText or "mp_pre"
        search_radius = parameters[5].valueAsText or "200 Feet"
        eps_miles = float(parameters[6].value) if parameters[6].value is not None else 0.0003
        threshold_m = tp.linear_unit_to_meters(parameters[7].valueAsText, 5.0)
        trim_m = tp.linear_unit_to_meters(parameters[8].valueAsText, 0.0)
        wkid = int(parameters[9].value) if parameters[9].value is not None else None
        run_reversals = bool(parameters[10].value)
        run_qc = bool(parameters[11].value)
        regex = parameters[12].valueAsText
        config_file = parameters[13].valueAsText

        cfg = tp.build_cfg(project_folder, config_file, messages)
        logger = None
        try:
            from utils.corridor.units import resolve_logger
            logger = resolve_logger(cfg, messages)
        except Exception:
            pass

        if logger:
            logger.info("=== Corridor Thinning (chained) START ===", indent=0)

        calc_mp(points_fc=points_fc, routes_fc=routes_fc, route_id_field=route_id_field,
                search_radius=search_radius, cfg=cfg, messages=messages)
        calc_sub_order(fc=points_fc, eps_miles=eps_miles, filename_regex=regex, cfg=cfg, messages=messages)
        if run_reversals:
            detect_reversals(fc=points_fc, filename_regex=regex, cfg=cfg, messages=messages)
        if run_qc:
            qc_sub_order(fc=points_fc, cfg=cfg, messages=messages)
            find_gaps(fc=points_fc, cfg=cfg, messages=messages)
        thin(fc=points_fc, threshold_m=threshold_m, trim_m=trim_m, wkid=wkid, cfg=cfg, messages=messages)
        if run_qc:
            qc_thin(fc=points_fc, threshold_m=threshold_m, wkid=wkid, filename_regex=regex,
                    cfg=cfg, messages=messages)
        export_manifest(fc=points_fc, out_csv=out_csv, cfg=cfg, messages=messages)

        if logger:
            logger.success(f"=== Corridor Thinning (chained) DONE -> {out_csv} ===", indent=0)
