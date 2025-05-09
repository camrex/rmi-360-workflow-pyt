import arcpy
from utils.config_loader import get_default_config_path
from utils.smooth_gps_noise import smooth_gps_noise
from utils.correct_gps_outliers import correct_gps_outliers
from utils.arcpy_utils import log_message


class SmoothGPSNoiseTool(object):
    def __init__(self):
        self.label = "04 - Smooth GPS Noise"
        self.description = ("Detect and flag GPS outlier points in a 360° Oriented Imagery Dataset using configurable "
                            "geometric and route-based rules.")
        self.category = "Individual Tools"

    def getParameterInfo(self):
        params = []

        oid_param = arcpy.Parameter(
            displayName="Oriented Imagery Dataset",
            name="oid_fc",
            datatype="DEFeatureClass",
            parameterType="Required",
            direction="Input"
        )
        oid_param.filter.list = []
        oid_param.description = "The Oriented Imagery Dataset feature class to analyze."
        params.append(oid_param)

        route_param = arcpy.Parameter(
            displayName="Reference Centerline (optional)",
            name="centerline_fc",
            datatype="DEFeatureClass",
            parameterType="Optional",
            direction="Input"
        )
        route_param.filter.list = ["Polyline"]
        route_param.description = "Optional M-aware centerline feature to validate points against known track/route."
        params.append(route_param)

        flag_param = arcpy.Parameter(
            displayName="Flag Only (No Geometry Updates)",
            name="flag_only",
            datatype="GPBoolean",
            parameterType="Optional",
            direction="Input"
        )
        flag_param.value = False
        flag_param.description = "Only flag GPS outliers in QCFlag field without modifying geometry."
        params.append(flag_param)

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
        """
        Executes the GPS outlier detection and correction workflow for an Oriented Imagery Dataset.
        
        Extracts tool parameters, runs GPS outlier detection using geometric and route-based rules, and optionally
        corrects flagged GPS points based on configuration settings. The correction step is skipped if flag-only mode
        is enabled.
        """
        oid_fc = parameters[0].valueAsText
        centerline_fc = parameters[1].valueAsText if parameters[1].value else None
        flag_only = parameters[2].value if parameters[2].altered else False
        config_file = parameters[3].valueAsText or get_default_config_path()

        log_message("\n--- Running GPS Outlier Detection ---", messages)
        smooth_gps_noise(
            oid_fc=oid_fc,
            centerline_fc=centerline_fc,
            config_file=config_file,
            messages=messages,
        )

        if not flag_only:
            log_message("\n--- Correcting Flagged GPS Points ---", messages)
            correct_gps_outliers(
                oid_fc=oid_fc,
                config_file=config_file,
                messages=messages
            )
        else:
            log_message("\nSkipped correction step (flag-only mode or no outliers).", messages)

        log_message("\n--- SmoothGPSNoise Tool Complete ---", messages)
