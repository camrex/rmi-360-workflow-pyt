# =============================================================================
# 🧪 Deploy Secured Test Set (tools/deploy_secured_test_set_tool.py)
# -----------------------------------------------------------------------------
# Tool Name:          OIDDeploySecuredTestSetTool
# Toolbox Context:    rmi_360_oid_maintenance.pyt
# Version:            0.1.0
# Author:             RMI Valuation, LLC
#
# Description:
#   Stages a SMALL test subset of an existing (already-deployed) OID into a target
#   S3 bucket/region (e.g. us-east-1) and optionally publishes a secured Oriented
#   Imagery service, to validate secured storage in the SAME region as the ArcGIS
#   Enterprise deployment. Two-pass: run with Publish off to stage + get the
#   cloud-store registration values; register the cloud store in Enterprise; re-run
#   with Publish on + the cloud store name. DRY RUN by default.
#
# Core Utils:
#   - utils/deploy_secured_test_set.py  (deploy_secured_test_set)
#   - utils/manager/config_manager.py
# =============================================================================

import arcpy

from utils.manager.config_manager import ConfigManager
from utils.shared.arcpy_utils import str_to_bool
from utils.deploy_secured_test_set import deploy_secured_test_set


class OIDDeploySecuredTestSetTool:
    def __init__(self):
        self.label = "30 - Deploy Secured Test Set (cross-region)"
        self.description = (
            "Stage a small test subset of an existing OID into a target S3 bucket/region "
            "(e.g. us-east-1) and optionally publish a secured service. Two-pass; dry run by default."
        )
        self.canRunInBackground = False
        self.category = "Secured Storage Testing"

    def getParameterInfo(self):
        source_oid = arcpy.Parameter(
            displayName="Source OID (already deployed; images in S3)",
            name="source_oid_fc",
            datatype="DEFeatureClass",
            parameterType="Required",
            direction="Input",
        )

        test_bucket = arcpy.Parameter(
            displayName="Test S3 Bucket (created if missing)",
            name="test_bucket",
            datatype="GPString",
            parameterType="Required",
            direction="Input",
        )

        test_region = arcpy.Parameter(
            displayName="Test Region",
            name="test_region",
            datatype="GPString",
            parameterType="Required",
            direction="Input",
        )
        test_region.value = "us-east-1"

        test_count = arcpy.Parameter(
            displayName="Test Set Size (images)",
            name="test_count",
            datatype="GPLong",
            parameterType="Optional",
            direction="Input",
        )
        test_count.value = 100

        selection = arcpy.Parameter(
            displayName="Selection",
            name="selection",
            datatype="GPString",
            parameterType="Optional",
            direction="Input",
        )
        selection.filter.type = "ValueList"
        selection.filter.list = ["spaced", "first"]
        selection.value = "spaced"

        key_prefix = arcpy.Parameter(
            displayName="Key Prefix Override (blank = resolve from config)",
            name="key_prefix",
            datatype="GPString",
            parameterType="Optional",
            direction="Input",
        )

        source_bucket = arcpy.Parameter(
            displayName="Source Bucket Override (blank = aws.s3_bucket_panos_unsecured)",
            name="source_bucket",
            datatype="GPString",
            parameterType="Optional",
            direction="Input",
        )

        create_bucket = arcpy.Parameter(
            displayName="Create Test Bucket If Missing",
            name="create_bucket",
            datatype="GPBoolean",
            parameterType="Optional",
            direction="Input",
        )
        create_bucket.value = True

        publish = arcpy.Parameter(
            displayName="Publish Service (requires registered cloud store)",
            name="publish",
            datatype="GPBoolean",
            parameterType="Optional",
            direction="Input",
        )
        publish.value = False

        cloud_store_name = arcpy.Parameter(
            displayName="Cloud Store Name (required to publish)",
            name="cloud_store_name",
            datatype="GPString",
            parameterType="Optional",
            direction="Input",
        )

        share_with = arcpy.Parameter(
            displayName="Share With (blank = config default)",
            name="share_with",
            datatype="GPString",
            parameterType="Optional",
            direction="Input",
        )
        share_with.filter.type = "ValueList"
        share_with.filter.list = ["PRIVATE", "ORGANIZATION", "PUBLIC"]

        project_folder = arcpy.Parameter(
            displayName="Project Folder",
            name="project_folder",
            datatype="DEFolder",
            parameterType="Required",
            direction="Input",
        )

        config_file = arcpy.Parameter(
            displayName="Config File",
            name="config_file",
            datatype="DEFile",
            parameterType="Optional",
            direction="Input",
        )

        dry_run = arcpy.Parameter(
            displayName="Dry Run (preview only, no AWS/OID changes)",
            name="dry_run",
            datatype="GPBoolean",
            parameterType="Optional",
            direction="Input",
        )
        dry_run.value = True

        return [
            source_oid,
            test_bucket,
            test_region,
            test_count,
            selection,
            key_prefix,
            source_bucket,
            create_bucket,
            publish,
            cloud_store_name,
            share_with,
            project_folder,
            config_file,
            dry_run,
        ]

    def updateMessages(self, parameters):
        p = {param.name: param for param in parameters}
        pub = p.get("publish")
        csn = p.get("cloud_store_name")
        if pub and bool(pub.value) and csn and not (csn.valueAsText and csn.valueAsText.strip()):
            csn.setErrorMessage("Cloud Store Name is required when Publish Service is enabled.")
        elif csn:
            csn.clearMessage()

    def execute(self, parameters, messages):
        p = {param.name: param.valueAsText for param in parameters}

        cfg = ConfigManager.from_file(
            path=p["config_file"],  # may be None
            project_base=p["project_folder"],
            messages=messages,
            require_supported_version=False,  # operates on older already-deployed projects (e.g. 1.3.x)
        )
        cfg.get_logger(messages)  # bind the tool's message sink so the util's log lines show in the dialog

        def _int(value, default):
            try:
                return int(value)
            except (TypeError, ValueError):
                return default

        result = deploy_secured_test_set(
            cfg,
            source_oid_fc=p["source_oid_fc"],
            test_bucket=(p.get("test_bucket") or "").strip(),
            test_region=(p.get("test_region") or "us-east-1").strip(),
            key_prefix=(p.get("key_prefix") or None),
            test_count=_int(p.get("test_count"), 100),
            selection=(p.get("selection") or "spaced"),
            source_bucket=(p.get("source_bucket") or None),
            create_bucket=str_to_bool(p.get("create_bucket", "true")),
            cloud_store_name=(p.get("cloud_store_name") or None),
            publish=str_to_bool(p.get("publish", "false")),
            share_with=(p.get("share_with") or None),
            dry_run=str_to_bool(p.get("dry_run", "true")),
        )

        logger = cfg.get_logger()
        logger.custom(
            f"Test set: {result['image_count']} image(s) → s3://{result['test_bucket']} "
            f"({result['test_region']}); synced {result['sync']['copied']}, "
            f"published: {result.get('published_service') or '(not this pass)'}.",
            emoji="🧪",
            indent=1,
        )
