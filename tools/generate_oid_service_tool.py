import arcpy
from utils.generate_oid_service import generate_oid_service
from utils.config_loader import get_default_config_path


class GenerateOIDService(object):
    def __init__(self):
        self.label = "10 - Generate OID Service"
        self.description = "Duplicates an OID with AWS paths and publishes it as a hosted Oriented Imagery service."
        self.canRunInBackground = False
        self.category = "Individual Tools"

    def getParameterInfo(self):
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
        oid_fc = parameters[0].valueAsText
        config_file = parameters[1].valueAsText or get_default_config_path()

        generate_oid_service(
            oid_fc=oid_fc,
            config_file=config_file,
            messages=messages
        )
