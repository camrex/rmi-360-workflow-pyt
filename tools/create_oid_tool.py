import arcpy
from utils.create_oid_feature_class import create_oriented_imagery_dataset
from utils.config_loader import get_default_config_path


class CreateOrientedImageryDatasetTool(object):
    def __init__(self):
        self.label = "02 - Create Oriented Imagery Dataset"
        self.description = "Creates a new Oriented Imagery Dataset using the template schema."
        self.category = "Individual Tools"

    def getParameterInfo(self):
        """
        Defines the input and output parameters for the Create Oriented Imagery Dataset tool.
        
        Returns:
            A list of ArcPy Parameter objects specifying the required and optional inputs for
            creating an Oriented Imagery Dataset, including output feature class, spatial
            reference, configuration file, and project folder.
        """
        params = []

        # Output OID feature class
        output_param = arcpy.Parameter(
            displayName="Output Oriented Imagery Dataset",
            name="output_fc",
            datatype="DEFeatureClass",
            parameterType="Required",
            direction="Output"
        )
        output_param.description = "Path to the new Oriented Imagery Dataset (OID) feature class to be created."
        params.append(output_param)

        # Optional spatial reference
        sr_param = arcpy.Parameter(
            displayName="Spatial Reference (optional)",
            name="spatial_ref",
            datatype="GPSpatialReference",
            parameterType="Optional",
            direction="Input"
        )
        sr_param.description = (
            "Spatial reference for the output OID. If omitted, the default defined in config.yaml will be used. "
            "Defaults to WGS 1984 (4326) with vertical WKID 5703 (ellipsoidal height)."
        )
        params.append(sr_param)

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

        # Project folder - Root folder for this Mosaic 360 imagery project. All imagery and logs will be organized
        # under this folder.
        project_param = arcpy.Parameter(
            displayName="Project Folder",
            name="project_folder",
            datatype="DEFolder",
            parameterType="Optional",
            direction="Input"
        )
        params.append(project_param)

        return params

    def execute(self, parameters, messages):
        """
        Executes the tool to create a new Oriented Imagery Dataset feature class.
        
        Extracts input and output parameters, applies defaults where necessary, and delegates
        the creation of the dataset to the underlying utility function.
        """
        output_fc = parameters[0].valueAsText
        spatial_ref = parameters[1].value
        config_file = parameters[2].valueAsText or get_default_config_path()
        project_folder = parameters[3].valueAsText

        create_oriented_imagery_dataset(
            output_fc_path=output_fc,
            spatial_reference=spatial_ref,
            config_file=config_file,
            project_folder=project_folder,
            messages=messages
        )
