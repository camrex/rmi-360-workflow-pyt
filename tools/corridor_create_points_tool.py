# =============================================================================
# 🛰️ Corridor 00 — Create Panorama Points (tools/corridor_create_points_tool.py)
# -----------------------------------------------------------------------------
# Tool Name:          CorridorCreatePointsTool
# Toolbox Context:    rmi_360_corridor_thinning.pyt
# Version:            1.0.0
# Author:             RMI Valuation, LLC
#
# Description:
#   Build the panorama point feature class the corridor pipeline consumes:
#   GeoTagged Photos -> Points, parse reel / reel_start_ts / frame from the
#   filename, and add empty editorial fields (include / mp_pre / track).
# =============================================================================

import arcpy

from utils.corridor import toolparams as tp
from utils.corridor.create_points import create_points


class CorridorCreatePointsTool(object):
    def __init__(self):
        self.label = "00 - Create Panorama Points"
        self.description = (
            "Create the panorama point feature class from geotagged panoramas "
            "(GeoTagged Photos to Points), parse reel/reel_start_ts/frame from the "
            "filename, and add empty editorial fields (include/mp_pre/track) for you "
            "to populate before Calculate Mileposts."
        )
        self.category = tp.CATEGORY

    def getParameterInfo(self):
        photo = arcpy.Parameter(
            displayName="Panorama Photo Folder", name="photo_folder",
            datatype="DEFolder", parameterType="Required", direction="Input")
        out = arcpy.Parameter(
            displayName="Output Point Feature Class", name="out_fc",
            datatype="DEFeatureClass", parameterType="Required", direction="Output")
        regex = tp.string_param("filename_regex", "Filename Regex (reel, reel_start_ts, frame)",
                                default=r"reel_(\d+)_(\d{8}-\d{6})_.*_(\d+)\.jpg$")
        non_geo = tp.bool_param("include_non_geotagged", "Include Non-GeoTagged Photos", default=False)
        editorial = tp.bool_param("add_editorial_fields", "Add Empty Editorial Fields (include/mp_pre/track)", default=True)
        return [tp.project_param(), photo, out, regex, non_geo, editorial, tp.config_param()]

    def execute(self, parameters, messages):
        project_folder = parameters[0].valueAsText
        photo_folder = parameters[1].valueAsText
        out_fc = parameters[2].valueAsText
        regex = parameters[3].valueAsText
        include_non_geotagged = bool(parameters[4].value)
        add_editorial = bool(parameters[5].value)
        config_file = parameters[6].valueAsText

        cfg = tp.build_cfg(project_folder, config_file, messages)
        create_points(
            photo_folder=photo_folder,
            out_fc=out_fc,
            include_non_geotagged=include_non_geotagged,
            add_editorial_fields=add_editorial,
            filename_regex=regex,
            cfg=cfg,
            messages=messages,
        )
