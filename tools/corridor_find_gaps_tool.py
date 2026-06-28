# =============================================================================
# 📏 Corridor 06 — Find Gaps (tools/corridor_find_gaps_tool.py)
# -----------------------------------------------------------------------------
# Tool Name:          CorridorFindGapsTool
# Toolbox Context:    rmi_360_corridor_thinning.pyt
# Version:            1.0.0
# Author:             RMI Valuation, LLC
#
# Description:
#   Read-only: list large sub_order steps, classified reel-boundary (benign) vs
#   within-run (investigate).
# =============================================================================

from utils.corridor import toolparams as tp
from utils.corridor.find_gaps import find_gaps


class CorridorFindGapsTool(object):
    def __init__(self):
        self.label = "06 - Find Gaps (read-only)"
        self.description = "Read-only list of large sub_order gaps, reel-boundary vs within-run."
        self.category = tp.CATEGORY

    def getParameterInfo(self):
        points = tp.points_fc_param()
        pre = tp.field_param("pre_field", "Subdivision Field (mp_pre)", "points_fc", default="mp_pre")
        track = tp.field_param("track_field", "Track Field", "points_fc", default="track")
        meas = tp.field_param("meas_field", "Measure Field (mp_meas)", "points_fc", default="mp_meas")
        sub = tp.field_param("sub_order_field", "Sub-Order Field", "points_fc", default="sub_order", required=True)
        include = tp.field_param("include_field", "Include Field", "points_fc", default="include")
        reel = tp.field_param("reel_field", "Reel Field", "points_fc", default="reel")
        frame = tp.field_param("frame_field", "Frame Field", "points_fc", default="frame")
        gap = tp.number_param("gap_threshold_ft", "Gap Threshold (data units)", default=15.0)
        return [tp.project_param(), points, pre, track, meas, sub, include, reel, frame, gap, tp.config_param()]

    def execute(self, parameters, messages):
        project_folder = parameters[0].valueAsText
        fc = parameters[1].valueAsText
        pre_field = parameters[2].valueAsText or "mp_pre"
        track_field = parameters[3].valueAsText or "track"
        meas_field = parameters[4].valueAsText or "mp_meas"
        sub_order_field = parameters[5].valueAsText or "sub_order"
        include_field = parameters[6].valueAsText or "include"
        reel_field = parameters[7].valueAsText or "reel"
        frame_field = parameters[8].valueAsText or "frame"
        gap_threshold_ft = float(parameters[9].value) if parameters[9].value is not None else 15.0
        config_file = parameters[10].valueAsText

        cfg = tp.build_cfg(project_folder, config_file, messages)
        find_gaps(
            fc=fc, track_field=track_field, meas_field=meas_field, sub_order_field=sub_order_field,
            pre_field=pre_field, include_field=include_field, gap_threshold_ft=gap_threshold_ft,
            reel_field=reel_field, frame_field=frame_field, cfg=cfg, messages=messages,
        )
