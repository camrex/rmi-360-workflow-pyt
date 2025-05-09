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
