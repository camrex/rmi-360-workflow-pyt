# =============================================================================
# 📐 Build OID Footprints (tools/build_oid_footprints_tool.py)
# -----------------------------------------------------------------------------
# Tool Name:          BuildOIDFootprints
# Toolbox Context:    rmi_360_workflow.pyt
# Version:            1.0.0
# Author:             RMI Valuation, LLC
# Created:            2025-05-08
#
# Description:
#   Implements ArcPy Tool class for generating a BUFFER-style footprint feature class from
#   an Oriented Imagery Dataset (OID). Uses ArcGIS’s BuildOrientedImageryFootprint and supports
#   optional config input for custom spatial reference or transformation logic.
#
# File Location:      /tools/build_oid_footprints_tool.py
# Uses:
#   - utils/build_oid_footprints.py
#
# Documentation:
#   See: docs_legacy/TOOL_GUIDES.md and docs_legacy/tools/build_oid_footprints.md
#
# Parameters:
#   - Oriented Imagery Dataset {oid_fc} (Feature Class): Path to an existing OID feature class.
#   - Config File {config_file} (File): Path to the project config.yaml containing spatial reference settings (optional).
#
# Notes:
#   - Can run standalone or as part of the orchestrator workflow
#   - Respects config overrides for spatial reference and geographic transformation
#   - Sets canRunInBackground = False due to ArcPy environment handling
# =============================================================================

import arcpy
from utils.build_oid_footprints import build_oid_footprints


class BuildOIDFootprints(object):
    def __init__(self):
        self.label = "08 - Build OID Footprints"
        self.description = "Generates a BUFFER-style footprint feature class from an Oriented Imagery Dataset."
        self.canRunInBackground = False
        self.category = "Individual Tools"

    def getParameterInfo(self):
        """
        Defines the input parameters for the BuildOIDFootprints geoprocessing tool.
        
        Returns:
            A list of ArcPy Parameter objects for the Oriented Imagery Dataset and optional config file.
        """
        params = []

        # Oriented Imagery Dataset (OID)
        oid_param = arcpy.Parameter(
            displayName="Oriented Imagery Dataset",
            name="oid_fc",
            datatype="DEFeatureClass",
            parameterType="Required",
            direction="Input"
        )
        oid_param.description = "Path to an existing OID feature class."
        params.append(oid_param)

        # Config file
        config_param = arcpy.Parameter(
            displayName="Config File",
            name="config_file",
            datatype="DEFile",
            parameterType="Optional",
            direction="Input"
        )
        config_param.description = "Config.yaml file containing project-specific settings."
        params.append(config_param)

        return params

    def execute(self, parameters, messages):
        """
        Executes the tool to generate footprint features from an Oriented Imagery Dataset.
        
        Extracts input parameters and invokes the core footprint-building function, passing
        the dataset path, optional configuration file, and ArcGIS messaging object.
        """
        oid_fc = parameters[0].valueAsText
        config_file = parameters[1].valueAsText

        # Call the core function with ArcGIS Pro messaging support
        build_oid_footprints(
            oid_fc=oid_fc,
            config_file=config_file,
            messages=messages
        )
