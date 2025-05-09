# =============================================================================
# 📝 Generate Report from JSON (tools/generate_report_tool.py)
# -----------------------------------------------------------------------------
# Tool Name:          GenerateReportFromJSONTool
# Toolbox Context:    rmi_360_workflow.pyt
# Version:            1.0.0
# Author:             RMI Valuation, LLC
# Created:            2025-05-08
#
# Description:
#   Implements ArcPy Tool class for generating an HTML (and optionally PDF) report based on
#   a saved report JSON file. Optionally reattaches a configuration file for template path
#   resolution and branding. Output folder can be overridden or defaults to path from JSON.
#
# File Location:      /tools/generate_report_tool.py
# Uses:
#   - utils/generate_report.py
#   - utils/config_loader.py
#
# Documentation:
#   See: docs/TOOL_GUIDES.md and docs/tools/generate_report.md
#
# Parameters:
#   - Report JSON File {report_json} (File): Path to the saved report_data_<slug>.json file containing report input and stats.
#   - Output Folder (Optional) {output_dir} (Folder): Folder to save the HTML and PDF output. Defaults to path from report JSON.
#   - Config File (Optional) {config_file} (File): Optional YAML config file to reattach template, logo, and slug context.
#
# Notes:
#   - Generates HTML report from Jinja2 templates; PDF export is optional
#   - Can be re-run at any time using archived JSON data
# =============================================================================

import arcpy
from utils.generate_report import generate_report_from_json
from utils.config_loader import get_default_config_path


class GenerateReportFromJSONTool(object):
    def __init__(self):
        """
        Initializes the GenerateReportFromJSONTool with label, description, and category metadata.
        """
        self.label = "15 - Generate Report from JSON"
        self.description = "Generates an HTML report from a saved report_data_<slug>.json file."
        self.category = "Individual Tools"

    def getParameterInfo(self):
        """
        Defines the input parameters for the GenerateReportFromJSONTool ArcPy tool.
        
        Returns:
            A list of ArcPy Parameter objects specifying the required and optional inputs
            for generating reports from a JSON file.
        """
        params = []

        # Report JSON file
        json_param = arcpy.Parameter(
            displayName="Report JSON File",
            name="report_json",
            datatype="DEFile",
            parameterType="Required",
            direction="Input"
        )
        json_param.filter.list = ["json"]
        json_param.description = "Path to the saved report_data_<slug>.json file containing all report inputs."
        params.append(json_param)

        # Optional output folder
        out_param = arcpy.Parameter(
            displayName="Output Folder (Optional)",
            name="output_dir",
            datatype="DEFolder",
            parameterType="Optional",
            direction="Input"
        )
        out_param.description = (
            "Folder to save the HTML and PDF report. "
            "If left blank, the default will be the path stored in the report JSON."
        )
        params.append(out_param)

        # Config file (optional reattachment)
        config_param = arcpy.Parameter(
            displayName="Config File (Optional)",
            name="config_file",
            datatype="DEFile",
            parameterType="Optional",
            direction="Input"
        )
        config_param.description = (
            "Optional config.yaml file to reattach config context for paths, templates, and logos. "
            "Used only if not already included in the report JSON."
        )
        params.append(config_param)

        return params

    def execute(self, parameters, messages):
        """
        Executes the tool to generate a report from a JSON file using provided parameters.
        
        Extracts input values for the report JSON file, output directory, and configuration file, then calls the report
        generation function with these inputs.
        """
        json_path = parameters[0].valueAsText
        output_dir = parameters[1].valueAsText
        config_file = parameters[2].valueAsText or get_default_config_path()

        generate_report_from_json(
            json_path=json_path,
            output_dir=output_dir,
            messages=messages,
            config_file=config_file
        )
