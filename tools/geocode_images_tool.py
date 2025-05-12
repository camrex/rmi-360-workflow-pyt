# =============================================================================
# 🌍 Geocode Images (tools/geocode_images_tool.py)
# -----------------------------------------------------------------------------
# Tool Name:          GeocodeImagesTool
# Toolbox Context:    rmi_360_workflow.pyt
# Version:            1.0.0
# Author:             RMI Valuation, LLC
# Created:            2025-05-08
#
# Description:
#   Implements ArcPy Tool class that geotags images from an Oriented Imagery Dataset (OID)
#   using GPS metadata and ExifTool. Adds XMP geolocation data to image files in-place and
#   supports project-specific geolocation configuration files.
#
# File Location:      /tools/geocode_images_tool.py
# Uses:
#   - utils/geocode_images.py
#   - utils/config_loader.py
#
# Documentation:
#   See: docs_legacy/TOOL_GUIDES.md and docs_legacy/tools/geocode_images.md
#
# Parameters:
#   - Oriented Imagery Feature Class {oid_fc} (Feature Class): The OID containing images to geotag.
#   - Config File (optional) {config_file} (File): Optional config.yaml with geolocation DB and output settings.
#
# Notes:
#   - Requires ExifTool to be installed and available in PATH
#   - Can be re-run safely; overwrites existing XMP location tags
# =============================================================================

import arcpy
from utils.geocode_images import geocode_images
from utils.config_loader import get_default_config_path


class GeocodeImagesTool:
    def __init__(self):
        self.label = "07 - Geocode Images"
        self.description = "Applies location tags to images using ExifTool and GPS metadata."
        self.canRunInBackground = True
        self.category = "Individual Tools"

    def getParameterInfo(self):
        params = []
        oid_param = arcpy.Parameter(
            displayName="Oriented Imagery Feature Class",
            name="oid_fc",
            datatype="DEFeatureClass",
            parameterType="Required",
            direction="Input"
        )
        oid_param.description = "The Oriented Imagery Dataset to process."
        params.append(oid_param)

        config_param = arcpy.Parameter(
            displayName="Config File (optional)",
            name="config_file",
            datatype="DEFile",
            parameterType="Optional",
            direction="Input"
        )
        config_param.description = "Config.yaml file containing project-specific settings."
        config_param.filter.list = ["yaml", "yml"]
        params.append(config_param)

        return params

    def execute(self, parameters, messages):
        oid_fc = parameters[0].valueAsText
        config_file = parameters[1].valueAsText or get_default_config_path()

        geocode_images(
            oid_fc=oid_fc,
            config_file=config_file,
            messages=messages,
        )
