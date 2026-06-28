# =============================================================================
# 🔎 Corridor 05 — QC Sequence (tools/corridor_qc_sequence_tool.py)
# -----------------------------------------------------------------------------
# Tool Name:          CorridorQCSequenceTool
# Toolbox Context:    rmi_360_corridor_thinning.pyt
# Version:            1.0.0
# Author:             RMI Valuation, LLC
#
# Description:
#   Read-only QC of sub_order sequencing (contiguity, reconciliation, step
#   distance, large jumps, cluster order, NULL audit). Nothing is modified.
# =============================================================================

from utils.corridor import toolparams as tp
from utils.corridor.qc_sub_order import qc_sub_order


class CorridorQCSequenceTool(object):
    def __init__(self):
        self.label = "05 - QC Sequence (read-only)"
        self.description = "Read-only validation of the sub_order sequence, partition-aware."
        self.category = tp.CATEGORY

    def getParameterInfo(self):
        points = tp.points_fc_param()
        pre = tp.field_param("pre_field", "Subdivision Field (mp_pre)", "points_fc", default="mp_pre")
        track = tp.field_param("track_field", "Track Field", "points_fc", default="track")
        meas = tp.field_param("meas_field", "Measure Field (mp_meas)", "points_fc", default="mp_meas")
        sub = tp.field_param("sub_order_field", "Sub-Order Field", "points_fc", default="sub_order", required=True)
        include = tp.field_param("include_field", "Include Field", "points_fc", default="include")
        jump = tp.number_param("jump_threshold_ft", "Large-Jump Threshold (data units)", default=100.0)
        return [tp.project_param(), points, pre, track, meas, sub, include, jump, tp.config_param()]

    def execute(self, parameters, messages):
        project_folder = parameters[0].valueAsText
        fc = parameters[1].valueAsText
        pre_field = parameters[2].valueAsText or "mp_pre"
        track_field = parameters[3].valueAsText or "track"
        meas_field = parameters[4].valueAsText or "mp_meas"
        sub_order_field = parameters[5].valueAsText or "sub_order"
        include_field = parameters[6].valueAsText or "include"
        jump_threshold_ft = float(parameters[7].value) if parameters[7].value is not None else 100.0
        config_file = parameters[8].valueAsText

        cfg = tp.build_cfg(project_folder, config_file, messages)
        qc_sub_order(
            fc=fc, track_field=track_field, meas_field=meas_field, sub_order_field=sub_order_field,
            pre_field=pre_field, include_field=include_field, jump_threshold_ft=jump_threshold_ft,
            cfg=cfg, messages=messages,
        )
