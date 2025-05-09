import arcpy
from utils.build_oid_schema import create_oid_schema_template
from utils.config_loader import get_default_config_path
from utils.arcpy_utils import log_message


class CreateOIDTemplateTool(object):
    def __init__(self):
        self.label = "Create OID Schema Template"
        self.description = ("Creates a reusable schema table for Oriented Imagery Datasets (OIDs) based on config.yaml "
                            "settings.")
        self.category = "Setup"

    def getParameterInfo(self):
        """
        Defines the input parameters required for the tool.
        
        Returns:
            A list containing a single required file parameter for specifying the config.yaml file.
        """
        params = []

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
        Creates an OID schema template based on the provided configuration file.
        
        Uses the specified config file to generate a reusable schema table for Oriented Imagery Datasets (OIDs) and
        logs the location of the created template.
        """
        config_file = parameters[0].valueAsText or get_default_config_path()
        schema_path = create_oid_schema_template(config_file=config_file, messages=messages)
        log_message(f"✅ Template created at: {schema_path}", messages)
