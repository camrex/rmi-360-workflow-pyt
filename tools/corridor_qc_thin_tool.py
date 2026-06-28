# =============================================================================
# 🔬 Corridor 07 — QC Thinning (tools/corridor_qc_thin_tool.py)
# -----------------------------------------------------------------------------
# Tool Name:          CorridorQCThinTool
# Toolbox Context:    rmi_360_corridor_thinning.pyt
# Version:            1.0.0
# Author:             RMI Valuation, LLC
#
# Description:
#   Read-only deep QC of the kept set (flag=1): reconciliation, spacing violations
#   and distribution, stretched gaps, coverage holes, dual-track overlap, funnel.
#   Set the threshold to match the value used by Thin.
# =============================================================================

from utils.corridor import toolparams as tp
from utils.corridor.qc_thin import qc_thin


class CorridorQCThinTool(object):
    def __init__(self):
        self.label = "07 - QC Thinning (read-only)"
        self.description = "Read-only deep QC of the thinned (flag=1) set."
        self.category = tp.CATEGORY

    def getParameterInfo(self):
        points = tp.points_fc_param()
        pre = tp.field_param("pre_field", "Subdivision Field (mp_pre)", "points_fc", default="mp_pre")
        track = tp.field_param("track_field", "Track Field", "points_fc", default="track")
        sub = tp.field_param("sub_order_field", "Sub-Order Field", "points_fc", default="sub_order")
        meas = tp.field_param("meas_field", "Measure Field (mp_meas)", "points_fc", default="mp_meas")
        include = tp.field_param("include_field", "Include Field", "points_fc", default="include")
        flag = tp.field_param("flag_field", "Keep/Drop Flag Field", "points_fc", default="flag_5m", required=True)
        threshold = tp.linear_unit_param("threshold", "Thinning Threshold (match Thin)", default="5 Meters")
        wkid = tp.number_param("wkid", "Data WKID (for unit conversion)", default=6455, datatype="GPLong")
        return [tp.project_param(), points, pre, track, sub, meas, include, flag, threshold, wkid, tp.config_param()]

    def execute(self, parameters, messages):
        project_folder = parameters[0].valueAsText
        fc = parameters[1].valueAsText
        pre_field = parameters[2].valueAsText or "mp_pre"
        track_field = parameters[3].valueAsText or "track"
        sub_order_field = parameters[4].valueAsText or "sub_order"
        meas_field = parameters[5].valueAsText or "mp_meas"
        include_field = parameters[6].valueAsText or "include"
        flag_field = parameters[7].valueAsText or "flag_5m"
        threshold_m = tp.linear_unit_to_meters(parameters[8].valueAsText, 5.0)
        wkid = int(parameters[9].value) if parameters[9].value is not None else None
        config_file = parameters[10].valueAsText

        cfg = tp.build_cfg(project_folder, config_file, messages)
        qc_thin(
            fc=fc, track_field=track_field, flag_field=flag_field, sub_order_field=sub_order_field,
            meas_field=meas_field, pre_field=pre_field, include_field=include_field,
            threshold_m=threshold_m, wkid=wkid, cfg=cfg, messages=messages,
        )
