# =============================================================================
# 📤 Corridor 08 — Export Manifest (tools/corridor_export_manifest_tool.py)
# -----------------------------------------------------------------------------
# Tool Name:          CorridorExportManifestTool
# Toolbox Context:    rmi_360_corridor_thinning.pyt
# Version:            1.0.0
# Author:             RMI Valuation, LLC
#
# Description:
#   Export the kept set (include=1 AND flag=1) to a single combined manifest CSV,
#   ordered mp_pre then sub_order. Path is the operative key for Add Images To OID.
# =============================================================================

import arcpy

from utils.corridor import toolparams as tp
from utils.corridor.export_manifest import export_manifest


class CorridorExportManifestTool(object):
    def __init__(self):
        self.label = "08 - Export Manifest"
        self.description = (
            "Export the kept set (include=1 AND flag=1) to a combined manifest CSV for "
            "manifest-driven Add Images To OID."
        )
        self.category = tp.CATEGORY

    def getParameterInfo(self):
        points = tp.points_fc_param()
        out = arcpy.Parameter(
            displayName="Output Manifest CSV", name="out_csv",
            datatype="DEFile", parameterType="Required", direction="Output")
        if out.filter is not None:
            out.filter.list = ["csv"]
        pre = tp.field_param("pre_field", "Subdivision Field (mp_pre)", "points_fc", default="mp_pre")
        track = tp.field_param("track_field", "Track Field", "points_fc", default="track")
        sub = tp.field_param("sub_order_field", "Sub-Order Field", "points_fc", default="sub_order")
        flag = tp.field_param("flag_field", "Keep/Drop Flag Field", "points_fc", default="flag_5m", required=True)
        include = tp.field_param("include_field", "Include Field", "points_fc", default="include")
        return [tp.project_param(), points, out, pre, track, sub, flag, include, tp.config_param()]

    def execute(self, parameters, messages):
        project_folder = parameters[0].valueAsText
        fc = parameters[1].valueAsText
        out_csv = parameters[2].valueAsText
        pre_field = parameters[3].valueAsText or "mp_pre"
        track_field = parameters[4].valueAsText or "track"
        sub_order_field = parameters[5].valueAsText or "sub_order"
        flag_field = parameters[6].valueAsText or "flag_5m"
        include_field = parameters[7].valueAsText or "include"
        config_file = parameters[8].valueAsText

        cfg = tp.build_cfg(project_folder, config_file, messages)
        export_manifest(
            fc=fc, out_csv=out_csv, track_field=track_field, flag_field=flag_field,
            pre_field=pre_field, sub_order_field=sub_order_field, include_field=include_field,
            cfg=cfg, messages=messages,
        )
