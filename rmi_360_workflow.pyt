# Import tools to run individually
from tools.process_360_orchestrator import Process360Workflow
from tools.run_mosaic_processor_tool import RunMosaicProcessorTool
from tools.create_oid_tool import CreateOrientedImageryDatasetTool
from tools.add_images_to_oid_tool import AddImagesToOIDTool
from tools.smooth_gps_noise_tool import SmoothGPSNoiseTool
from tools.update_linear_and_custom_tool import UpdateLinearAndCustomTool
from tools.rename_and_tag_tool import RenameAndTagImagesTool
from tools.geocode_images_tool import GeocodeImagesTool
from tools.build_oid_footprints_tool import BuildOIDFootprints
from tools.copy_to_aws_tool import CopyToAwsTool
from tools.generate_oid_service_tool import GenerateOIDService
from tools.generate_report_tool import GenerateReportFromJSONTool
from tools.create_oid_template_tool import CreateOIDTemplateTool
from tools.set_aws_keyring_tool import SetAWSKeyringCredentialsTool


class Toolbox(object):
    def __init__(self):
        self.label = "RMI 360 Imaging Workflow Python Toolbox"
        self.alias = "rmi360workflow"
        self.tools = [
            Process360Workflow,
            RunMosaicProcessorTool,
            CreateOrientedImageryDatasetTool,
            AddImagesToOIDTool,
            SmoothGPSNoiseTool,
            UpdateLinearAndCustomTool,
            RenameAndTagImagesTool,
            GeocodeImagesTool,
            BuildOIDFootprints,
            CopyToAwsTool,
            GenerateOIDService,
            GenerateReportFromJSONTool,
            CreateOIDTemplateTool,
            SetAWSKeyringCredentialsTool
        ]
