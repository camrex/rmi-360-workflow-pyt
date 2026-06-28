# =============================================================================
# 🔢 Corridor 02 — Calculate Sequence (tools/corridor_calc_sequence_tool.py)
# -----------------------------------------------------------------------------
# Tool Name:          CorridorCalcSequenceTool
# Toolbox Context:    rmi_360_corridor_thinning.pyt
# Version:            1.0.0
# Author:             RMI Valuation, LLC
#
# Description:
#   Assign sub_order per (mp_pre, track) partition: mp_meas ascending with an
#   oriented-FRAME tie/near-tie break (geometry projection only as fallback).
# =============================================================================

from utils.corridor import toolparams as tp
from utils.corridor.calc_sub_order import calc_sub_order


class CorridorCalcSequenceTool(object):
    def __init__(self):
        self.label = "02 - Calculate Sequence (sub_order)"
        self.description = (
            "Assign sub_order per (mp_pre, track). Primary order mp_meas ascending; "
            "ties within EPS broken by oriented frame. Scope: include = 1."
        )
        self.category = tp.CATEGORY

    def getParameterInfo(self):
        points = tp.points_fc_param()
        pre = tp.field_param("pre_field", "Subdivision Field (mp_pre)", "points_fc", default="mp_pre", required=True)
        track = tp.field_param("track_field", "Track Field", "points_fc", default="track")
        meas = tp.field_param("meas_field", "Measure Field (mp_meas)", "points_fc", default="mp_meas", required=True)
        key = tp.field_param("key_field", "Unique Key Field (Name)", "points_fc", default="Name", required=True)
        include = tp.field_param("include_field", "Include Field", "points_fc", default="include", required=True)
        sub = tp.string_param("sub_order_field", "Sub-Order Field (created if missing)", default="sub_order")
        eps = tp.number_param("eps_miles", "Tie/near-tie EPS (miles)", default=0.0003)
        regex = tp.string_param("filename_regex", "Filename Regex (reel, reel_start_ts, frame)",
                                default=r"reel_(\d+)_(\d{8}-\d{6})_.*_(\d+)\.jpg$")
        return [tp.project_param(), points, pre, track, meas, key, include, sub, eps, regex, tp.config_param()]

    def execute(self, parameters, messages):
        project_folder = parameters[0].valueAsText
        fc = parameters[1].valueAsText
        pre_field = parameters[2].valueAsText or "mp_pre"
        track_field = parameters[3].valueAsText or "track"
        meas_field = parameters[4].valueAsText or "mp_meas"
        key_field = parameters[5].valueAsText or "Name"
        include_field = parameters[6].valueAsText or "include"
        sub_order_field = parameters[7].valueAsText or "sub_order"
        eps_miles = float(parameters[8].value) if parameters[8].value is not None else 0.0003
        regex = parameters[9].valueAsText
        config_file = parameters[10].valueAsText

        cfg = tp.build_cfg(project_folder, config_file, messages)
        calc_sub_order(
            fc=fc, track_field=track_field, meas_field=meas_field,
            sub_order_field=sub_order_field, key_field=key_field, pre_field=pre_field,
            include_field=include_field, eps_miles=eps_miles, filename_regex=regex,
            cfg=cfg, messages=messages,
        )
