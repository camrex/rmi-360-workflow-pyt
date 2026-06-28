# =============================================================================
# 🧰 Corridor Tool Helpers (utils/corridor/toolparams.py)
# -----------------------------------------------------------------------------
# Purpose:             Shared parameter builders and ConfigManager construction for
#                      the corridor-thinning tool classes. NOT a tool itself.
# Project:             RMI 360 Imaging Workflow Python Toolbox
# Version:             1.0.0
# Author:              RMI Valuation, LLC
#
# Description:
#   The corridor stage tools expose their parameters directly on the dialog (the
#   scripts' previously hard-coded values) and are runnable INDEPENDENTLY as
#   checkpoints. Project Folder + Config File are OPTIONAL — when supplied, a
#   ConfigManager provides logging/progressor and project-relative paths; when
#   omitted, the tools fall back to GP messages and the on-dialog values.
# =============================================================================

from __future__ import annotations

import arcpy

CATEGORY = "Corridor Thinning (Pre-Thin)"


def project_param():
    p = arcpy.Parameter(
        displayName="Project Folder (optional — enables config logging/paths)",
        name="project_folder",
        datatype="DEFolder",
        parameterType="Optional",
        direction="Input",
    )
    return p


def config_param():
    p = arcpy.Parameter(
        displayName="Config File (optional)",
        name="config_file",
        datatype="DEFile",
        parameterType="Optional",
        direction="Input",
    )
    if p.filter is not None:
        p.filter.list = ["yaml", "yml"]
    return p


def points_fc_param(name="points_fc", display="Panorama Point Feature Class"):
    p = arcpy.Parameter(
        displayName=display,
        name=name,
        datatype="DEFeatureClass",
        parameterType="Required",
        direction="Input",
    )
    if p.filter is not None:
        p.filter.list = ["Point"]
    return p


def field_param(name, display, depends_on, default=None, required=False):
    p = arcpy.Parameter(
        displayName=display,
        name=name,
        datatype="Field",
        parameterType="Required" if required else "Optional",
        direction="Input",
    )
    p.parameterDependencies = [depends_on]
    if default is not None:
        p.value = default
    return p


def number_param(name, display, default=None, required=False, datatype="GPDouble"):
    p = arcpy.Parameter(
        displayName=display,
        name=name,
        datatype=datatype,
        parameterType="Required" if required else "Optional",
        direction="Input",
    )
    if default is not None:
        p.value = default
    return p


def string_param(name, display, default=None, required=False):
    p = arcpy.Parameter(
        displayName=display,
        name=name,
        datatype="GPString",
        parameterType="Required" if required else "Optional",
        direction="Input",
    )
    if default is not None:
        p.value = default
    return p


def linear_unit_param(name, display, default="5 Meters", required=False):
    p = arcpy.Parameter(
        displayName=display,
        name=name,
        datatype="GPLinearUnit",
        parameterType="Required" if required else "Optional",
        direction="Input",
    )
    if default is not None:
        p.value = default
    return p


def bool_param(name, display, default=False):
    p = arcpy.Parameter(
        displayName=display,
        name=name,
        datatype="GPBoolean",
        parameterType="Optional",
        direction="Input",
    )
    p.value = default
    return p


def build_cfg(project_folder, config_file, messages):
    """Return a ConfigManager when both a project folder and config are available,
    else None (stages then use the lightweight fallback logger)."""
    if not (config_file and project_folder):
        return None
    from utils.manager.config_manager import ConfigManager
    return ConfigManager.from_file(path=config_file, project_base=project_folder, messages=messages)


def linear_unit_to_meters(value, default_m):
    """Parse a GPLinearUnit valueAsText to meters; fall back to default."""
    if not value:
        return default_m
    from utils.corridor.units import linear_unit_to_meters as _conv
    try:
        return _conv(value)
    except Exception:
        return default_m
