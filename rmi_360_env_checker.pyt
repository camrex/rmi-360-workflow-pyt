# =============================================================================
# 🧪 RMI 360 Imaging Environment Checker Toolbox (rmi_360_env_checker.pyt)
# -----------------------------------------------------------------------------
# Purpose:             Checks ArcGIS Pro Python environment for required packages
# Project:             RMI 360 Imaging Toolbox / Environment Validation
# Version:             1.1.1
# Author:              RMI Valuation, LLC
# Created:             2025-05-23
# Last Updated:        2025-05-23
#
# Description:
#   This self-contained ArcGIS Python Toolbox checks that all Python packages
#   required by the RMI 360 Imaging Toolbox (as listed in requirements.txt)
#   are installed in the current ArcGIS Pro Python environment.
#   No parameters are required; requirements.txt must be present in the same folder.
#
# File Location:        /rmi_360_env_checker.pyt
# Called By:            ArcGIS Pro (Toolbox registration), ArcGIS Python Toolbox Loader
#
# Directory Layout:
#   rmi_360_env_checker.pyt   → This toolbox (entry point, all logic inside)
#   requirements.txt          → List of required packages (no version checks)
#
# Registered Tools:
#   - 🧪 CheckEnvTool
#
# Documentation:
#   See: README.md or project documentation for toolbox usage.
#
# Notes:
#   - No business logic for imaging/processing is included; this is an environment validation utility only.
#   - Supports ArcGIS Pro 3.4+ Python 3.9+ environments.
#   - Reports any missing packages in the tool output panel.
# =============================================================================
import arcpy
import pkg_resources
import os

class Toolbox(object):
    def __init__(self):
        self.label = "RMI 360 Imaging Env Checker"
        self.alias = "rmi360envchecker"
        self.tools = [CheckEnvTool]

class CheckEnvTool(object):
    def __init__(self):
        self.label = "Check Required Python Packages"
        self.description = (
            "Checks if all required packages for RMI 360 Imaging Toolbox "
            "are present in this ArcGIS Pro Python environment."
        )

    def getParameterInfo(self):
        # No parameters needed!
        return []

    def execute(self, parameters, messages):
        # Find the directory where this .pyt lives
        base_dir = os.path.dirname(os.path.abspath(__file__))
        req_path = os.path.join(base_dir, 'requirements.txt')

        if not os.path.isfile(req_path):
            arcpy.AddError(f"requirements.txt not found in {base_dir}. Please ensure the file is present.")
            return

        with open(req_path, 'r') as f:
            # Ignore comments and blank lines
            requirements = [
                line.split('#')[0].strip() for line in f
                if line.strip() and not line.strip().startswith('#')
            ]

        # Only check the base package name (no version check)
        required_pkgs = [req.split()[0].lower() for req in requirements if req]

        installed_pkgs = {pkg.key for pkg in pkg_resources.working_set}

        missing = [pkg for pkg in required_pkgs if pkg not in installed_pkgs]

        if not missing:
            arcpy.AddMessage("✅ All required packages are installed in this ArcGIS Pro environment!")
        else:
            arcpy.AddWarning(
                "The following required packages are missing:\n" +
                "\n".join(f"- {pkg}" for pkg in missing)
            )
            arcpy.AddWarning(
                "You may need to install missing packages using the Python Command Prompt with 'conda install <package>' "
                "or via the ArcGIS Pro Package Manager."
            )
