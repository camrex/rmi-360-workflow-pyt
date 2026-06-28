# =============================================================================
# 🔁 Corridor 03 — Detect Reversals (tools/corridor_detect_reversals_tool.py)
# -----------------------------------------------------------------------------
# Tool Name:          CorridorDetectReversalsTool
# Toolbox Context:    rmi_360_corridor_thinning.pyt
# Version:            1.0.0
# Author:             RMI Valuation, LLC
#
# Description:
#   Detect and REPORT capture back-ups (reversals) per capture run. Detection only;
#   nothing is excluded. Detect on ALL points, report LIVE (include=1) separately.
# =============================================================================

from utils.corridor import toolparams as tp
from utils.corridor.detect_reversals import detect_reversals


class CorridorDetectReversalsTool(object):
    def __init__(self):
        self.label = "03 - Detect Reversals (report-only)"
        self.description = (
            "Detect capture reversals (back-ups) within each capture run and report "
            "LIVE (include=1) vs HANDLED (include=0). Resolution is future work."
        )
        self.category = tp.CATEGORY

    def getParameterInfo(self):
        points = tp.points_fc_param()
        pre = tp.field_param("pre_field", "Subdivision Field (mp_pre)", "points_fc", default="mp_pre")
        meas = tp.field_param("meas_field", "Measure Field (mp_meas)", "points_fc", default="mp_meas")
        include = tp.field_param("include_field", "Include Field", "points_fc", default="include")
        backtrack = tp.number_param("min_backtrack_ft", "Min Backtrack (data units)", default=15.0)
        oppose = tp.number_param("oppose_deg", "Opposing Angle (deg)", default=120.0)
        prevail = tp.number_param("prevail_window", "Prevailing Window (frames)", default=7, datatype="GPLong")
        min_frames = tp.number_param("min_reversal_frames", "Min Reversal Frames", default=2, datatype="GPLong")
        only_live = tp.bool_param("only_report_live", "Only Report LIVE Reversals", default=True)
        write_id = tp.bool_param("write_reversal_id", "Write reversal_id (if field exists)", default=False)
        regex = tp.string_param("filename_regex", "Filename Regex",
                                default=r"reel_(\d+)_(\d{8}-\d{6})_.*_(\d+)\.jpg$")
        return [tp.project_param(), points, pre, meas, include, backtrack, oppose, prevail,
                min_frames, only_live, write_id, regex, tp.config_param()]

    def execute(self, parameters, messages):
        project_folder = parameters[0].valueAsText
        fc = parameters[1].valueAsText
        pre_field = parameters[2].valueAsText or "mp_pre"
        meas_field = parameters[3].valueAsText or "mp_meas"
        include_field = parameters[4].valueAsText or "include"
        min_backtrack_ft = float(parameters[5].value) if parameters[5].value is not None else 15.0
        oppose_deg = float(parameters[6].value) if parameters[6].value is not None else 120.0
        prevail_window = int(parameters[7].value) if parameters[7].value is not None else 7
        min_reversal_frames = int(parameters[8].value) if parameters[8].value is not None else 2
        only_report_live = bool(parameters[9].value)
        write_reversal_id = bool(parameters[10].value)
        regex = parameters[11].valueAsText
        config_file = parameters[12].valueAsText

        cfg = tp.build_cfg(project_folder, config_file, messages)
        detect_reversals(
            fc=fc, pre_field=pre_field, meas_field=meas_field, include_field=include_field,
            min_backtrack_ft=min_backtrack_ft, oppose_deg=oppose_deg, prevail_window=prevail_window,
            min_reversal_frames=min_reversal_frames, only_report_live=only_report_live,
            write_reversal_id=write_reversal_id, filename_regex=regex, cfg=cfg, messages=messages,
        )
