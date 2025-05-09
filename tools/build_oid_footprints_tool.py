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
