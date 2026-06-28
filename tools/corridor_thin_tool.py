# =============================================================================
# ✂️ Corridor 04 — Thin to Interval (tools/corridor_thin_tool.py)
# -----------------------------------------------------------------------------
# Tool Name:          CorridorThinTool
# Toolbox Context:    rmi_360_corridor_thinning.pyt
# Version:            1.0.0
# Author:             RMI Valuation, LLC
#
# Description:
#   Anchor-reset thinning to a target interval per (mp_pre, track). Non-destructive:
#   writes a SHORT flag field (1 keep / 0 drop). Threshold is WKID-aware (meters
#   converted to the FC's linear units via metersPerUnit).
# =============================================================================

from utils.corridor import toolparams as tp
from utils.corridor.thin import thin


class CorridorThinTool(object):
    def __init__(self):
        self.label = "04 - Thin to Interval (flag)"
        self.description = (
            "Anchor-reset thinning to a target interval per (mp_pre, track). Writes a "
            "SHORT keep/drop flag (non-destructive). Resets at every partition boundary "
            "so dual-track overlaps retain both tracks."
        )
        self.category = tp.CATEGORY

    def getParameterInfo(self):
        points = tp.points_fc_param()
        pre = tp.field_param("pre_field", "Subdivision Field (mp_pre)", "points_fc", default="mp_pre")
        track = tp.field_param("track_field", "Track Field", "points_fc", default="track")
        sub = tp.field_param("sub_order_field", "Sub-Order Field", "points_fc", default="sub_order", required=True)
        include = tp.field_param("include_field", "Include Field", "points_fc", default="include")
        flag = tp.string_param("flag_field", "Keep/Drop Flag Field (created if missing)", default="flag_5m")
        threshold = tp.linear_unit_param("threshold", "Thinning Threshold", default="5 Meters")
        trim = tp.linear_unit_param("trim", "Threshold Trim (pull-in)", default="1.5 Meters")
        wkid = tp.number_param("wkid", "Data WKID (for unit conversion)", default=6455, datatype="GPLong")
        return [tp.project_param(), points, pre, track, sub, include, flag, threshold, trim, wkid, tp.config_param()]

    def execute(self, parameters, messages):
        project_folder = parameters[0].valueAsText
        fc = parameters[1].valueAsText
        pre_field = parameters[2].valueAsText or "mp_pre"
        track_field = parameters[3].valueAsText or "track"
        sub_order_field = parameters[4].valueAsText or "sub_order"
        include_field = parameters[5].valueAsText or "include"
        flag_field = parameters[6].valueAsText or "flag_5m"
        threshold_m = tp.linear_unit_to_meters(parameters[7].valueAsText, 5.0)
        trim_m = tp.linear_unit_to_meters(parameters[8].valueAsText, 0.0)
        wkid = int(parameters[9].value) if parameters[9].value is not None else None
        config_file = parameters[10].valueAsText

        cfg = tp.build_cfg(project_folder, config_file, messages)
        thin(
            fc=fc, track_field=track_field, flag_field=flag_field, sub_order_field=sub_order_field,
            pre_field=pre_field, include_field=include_field, threshold_m=threshold_m,
            trim_m=trim_m, wkid=wkid, cfg=cfg, messages=messages,
        )
