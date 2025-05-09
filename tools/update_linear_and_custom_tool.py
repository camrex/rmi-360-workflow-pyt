import arcpy
from utils.update_linear_and_custom import update_linear_and_custom
from utils.config_loader import get_default_config_path


class UpdateLinearAndCustomTool(object):
    def __init__(self):
        self.label = "06 - Update Linear and Custom Attributes"
        self.description = ("Locates images along a route and updates linear referencing (e.g. MP) and custom "
                            "attributes (e.g. RR).")
        self.category = "Individual Tools"

    def getParameterInfo(self):
        params = []

        oid_param = arcpy.Parameter(
            displayName="Oriented Imagery Dataset (OID)",
            name="oid_fc",
            datatype="DEFeatureClass",
            parameterType="Required",
            direction="Input"
        )
        oid_param.filter.list = []
        oid_param.description = "The Oriented Imagery Dataset feature class containing 360° image points."
        params.append(oid_param)

        centerline_param = arcpy.Parameter(
            displayName="M-Enabled Centerline",
            name="centerline_fc",
            datatype="DEFeatureClass",
            parameterType="Required",
            direction="Input"
        )
        centerline_param.filter.list = ["Polyline"]
        centerline_param.description = "Centerline feature class with route calibration (M values)."
        params.append(centerline_param)

        route_id_param = arcpy.Parameter(
            displayName="Route ID Field",
            name="route_id_field",
            datatype="Field",
            parameterType="Required",
            direction="Input"
        )
        route_id_param.parameterDependencies = [centerline_param.name]
        route_id_param.filter.list = ["Short", "Long", "Text"]
        route_id_param.description = "Field in the centerline layer that uniquely identifies each route."
        params.append(route_id_param)

        enable_lr_param = arcpy.Parameter(
            displayName="Enable Linear Referencing",
            name="enable_linear_ref",
            datatype="GPBoolean",
            parameterType="Optional",
            direction="Input"
        )
        enable_lr_param.value = True
        enable_lr_param.description = ("If checked, calculates MP values (MP_Pre and MP_Num) using "
                                       "UpdateLinearAndCustom.")
        params.append(enable_lr_param)

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
        oid_fc = parameters[0].valueAsText
        centerline_fc = parameters[1].valueAsText
        route_id_field = parameters[2].valueAsText
        enable_linear_ref = parameters[3].value if parameters[3].value is not None else True
        config_file = parameters[4].valueAsText or get_default_config_path()

        update_linear_and_custom(
            oid_fc=oid_fc,
            centerline_fc=centerline_fc,
            route_id_field=route_id_field,
            enable_linear_ref=enable_linear_ref,
            config_file=config_file,
            messages=messages
        )
