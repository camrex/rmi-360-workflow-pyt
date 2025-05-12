# =============================================================================
# 🧭 Update Linear and Custom Attributes (tools/update_linear_and_custom_tool.py)
# -----------------------------------------------------------------------------
# Tool Name:          UpdateLinearAndCustomTool
# Toolbox Context:    rmi_360_workflow.pyt
# Version:            1.0.0
# Author:             RMI Valuation, LLC
# Created:            2025-05-08
#
# Description:
#   Implements ArcPy Tool class to assign Milepost (MP) values and route identifiers via linear referencing
#   against an M-enabled centerline. Also supports applying user-defined attribute fields based on config
#   expressions. Can selectively enable or skip linear referencing while always applying custom fields.
#
# File Location:      /tools/update_linear_and_custom_tool.py
# Uses:
#   - utils/update_linear_and_custom.py
#   - utils/config_loader.py
#
# Documentation:
#   See: docs_legacy/TOOL_GUIDES.md and docs_legacy/tools/update_linear_and_custom.md
#
# Parameters:
#   - Oriented Imagery Dataset (OID) {oid_fc} (Feature Class): OID feature class containing image points to enrich.
#   - M-Enabled Centerline {centerline_fc} (Feature Class): Line feature class with calibrated M-values for referencing.
#   - Route ID Field {route_id_field} (Field): Field in the centerline that uniquely identifies each route.
#   - Enable Linear Referencing {enable_linear_ref} (Boolean): If checked, computes MP_Pre and MP_Num via Locate Features Along Routes.
#   - Config File {config_file} (File): Path to the project config.yaml file with custom field logic.
#
# Notes:
#   - Linear referencing can be toggled independently of custom attribute updates
#   - Supports complex config-driven field population with modifiers and formatting
# =============================================================================

import arcpy
from utils.update_linear_and_custom import update_linear_and_custom
from utils.config_loader import get_default_config_path


class UpdateLinearAndCustomTool(object):
    def __init__(self):
        self.label = "06 - Update Linear and Custom Attributes"
        self.description = ("Locates images along a route and updates linear referencing (e.g. MP) and custom "
                            "attributes (e.g. RR).")
        self.category = "Individual Tools"

    def getParameterInfo(self):
        params = []

        oid_param = arcpy.Parameter(
            displayName="Oriented Imagery Dataset (OID)",
            name="oid_fc",
            datatype="DEFeatureClass",
            parameterType="Required",
            direction="Input"
        )
        oid_param.filter.list = []
        oid_param.description = "The Oriented Imagery Dataset feature class containing 360° image points."
        params.append(oid_param)

        centerline_param = arcpy.Parameter(
            displayName="M-Enabled Centerline",
            name="centerline_fc",
            datatype="DEFeatureClass",
            parameterType="Required",
            direction="Input"
        )
        centerline_param.filter.list = ["Polyline"]
        centerline_param.description = "Centerline feature class with route calibration (M values)."
        params.append(centerline_param)

        route_id_param = arcpy.Parameter(
            displayName="Route ID Field",
            name="route_id_field",
            datatype="Field",
            parameterType="Required",
            direction="Input"
        )
        route_id_param.parameterDependencies = [centerline_param.name]
        route_id_param.filter.list = ["Short", "Long", "Text"]
        route_id_param.description = "Field in the centerline layer that uniquely identifies each route."
        params.append(route_id_param)

        enable_lr_param = arcpy.Parameter(
            displayName="Enable Linear Referencing",
            name="enable_linear_ref",
            datatype="GPBoolean",
            parameterType="Optional",
            direction="Input"
        )
        enable_lr_param.value = True
        enable_lr_param.description = ("If checked, calculates MP values (MP_Pre and MP_Num) using "
                                       "UpdateLinearAndCustom.")
        params.append(enable_lr_param)

        # Config file
        config_param = arcpy.Parameter(
            displayName="Config File",
            name="config_file",
            datatype="DEFile",
            parameterType="Required",
            direction="Input"
        )
        config_param.description = "Config.yaml file containing project-specific settings."
        params.append(config_param)

        return params

    def execute(self, parameters, messages):
        oid_fc = parameters[0].valueAsText
        centerline_fc = parameters[1].valueAsText
        route_id_field = parameters[2].valueAsText
        enable_linear_ref = parameters[3].value if parameters[3].value is not None else True
        config_file = parameters[4].valueAsText or get_default_config_path()

        update_linear_and_custom(
            oid_fc=oid_fc,
            centerline_fc=centerline_fc,
            route_id_field=route_id_field,
            enable_linear_ref=enable_linear_ref,
            config_file=config_file,
            messages=messages
        )
