__all__ = ["generate_oid_service"]

import arcpy
import os
from typing import Optional, Literal
from arcgis.gis import GIS
from utils.config_loader import resolve_config
from utils.arcpy_utils import log_message
from utils.expression_utils import resolve_expression


def generate_oid_service(
        oid_fc: str,
        config: Optional[dict] = None,
        config_file: Optional[str] = None,
        messages=None
):
    """
    Duplicates an Oriented Imagery Dataset, updates image paths to AWS S3 URLs, and publishes it as a hosted Oriented
    Imagery Service on ArcGIS Online.

    Args:
        oid_fc: Path to the input Oriented Imagery Dataset feature class.
        config: Optional dictionary containing configuration parameters.
        config_file: Optional path to a configuration file.
        messages: Optional messaging or logging handler.

    Returns:
        The name of the published Oriented Imagery Service.

    Raises:
        Re-raises any exceptions encountered during service publishing.
    """
    log_message("Starting OID Service Generation...", messages, config=config)

    # Load configuration
    config = resolve_config(
        config=config,
        config_file=config_file,
        oid_fc_path=oid_fc,
        messages=messages,
        tool_name="generate_oid_service"
    )

    aws_cfg = config.get("aws", {})
    portal_cfg = config.get("portal", {})

    # Required AWS details
    bucket = aws_cfg.get("s3_bucket")
    region = aws_cfg.get("region")
    bucket_folder_expr = aws_cfg.get("s3_bucket_folder")
    bucket_folder = resolve_expression(bucket_folder_expr, config)

    if not all([bucket, region, bucket_folder]):
        log_message("Missing required AWS values in config.yaml", messages, level="error", error_type=ValueError,
                    config=config)

    # Derive output AWS OID path
    oid_gdb = os.path.dirname(oid_fc)
    oid_name = os.path.splitext(os.path.basename(oid_fc))[0]
    aws_oid_name = f"{oid_name}_aws"
    aws_oid_fc = os.path.join(oid_gdb, aws_oid_name)

    # Step 1: Duplicate the OID feature class
    if arcpy.Exists(aws_oid_fc):
        log_message(f"Overwriting existing AWS OID: {aws_oid_fc}", messages, config=config)
        arcpy.management.Delete(aws_oid_fc)

    arcpy.management.Copy(oid_fc, aws_oid_fc)
    log_message(f"Duplicated OID to: {aws_oid_fc}", messages, config=config)

    # Step 2: Update ImagePath values
    updated_count = 0
    with arcpy.da.UpdateCursor(aws_oid_fc, ["ImagePath"]) as cursor:
        for row in cursor:
            local_path = row[0]
            filename = os.path.basename(local_path)
            aws_url = f"https://{bucket}.s3.{region}.amazonaws.com/{bucket_folder}/{filename}"
            row[0] = aws_url
            cursor.updateRow(row)
            updated_count += 1

    log_message(f"Updated {updated_count} image paths to AWS URLs.", messages, config=config)

    # Step 3: Publish using arcpy.oi.GenerateServiceFromOrientedImageryDataset
    service_name = f"{oid_name}"
    portal_folder = resolve_expression(portal_cfg.get("project_folder", ""), config)
    share_with: Literal["PRIVATE", "ORGANIZATION", "PUBLIC"] = portal_cfg.get("share_with", "PRIVATE")  # type: ignore
    add_footprint: Literal["FOOTPRINT", "NO_FOOTPRINT"] = portal_cfg.get("add_footprint", "FOOTPRINT")  # type: ignore
    tags_list = [resolve_expression(t, config) for t in portal_cfg.get("portal_tags", [])]
    tags_str = ", ".join(tags_list)
    summary = resolve_expression(portal_cfg.get("summary", ""), config)

    # Check if portal folder exists
    try:
        gis = GIS("pro")
        user = gis.users.me
        existing_folders = [f["title"] for f in user.folders]

        if portal_folder not in existing_folders:
            log_message(f"⚠️ Portal folder '{portal_folder}' does not exist. Attempting to create it...",
                        messages, level="warning", config=config)
            try:
                gis.content.folders.create(portal_folder)
                log_message(f"✅ Portal folder '{portal_folder}' created successfully.", messages, config=config)
            except Exception as e:
                log_message(f"❌ Failed to create portal folder '{portal_folder}': {e}", messages, level="error",
                            error_type=RuntimeError, config=config)
        else:
            log_message(f"📁 Portal folder found: {portal_folder}", messages, config=config)
    except Exception as e:
        log_message(f"⚠️ Unable to check portal folders: {e}", messages, level="warning", config=config)

    # Step 4: Publish using arcpy
    log_message("📦 Service generation parameters:", messages, config=config)
    log_message(f"  in_oriented_imagery_dataset: {aws_oid_fc}", messages, config=config)
    log_message(f"  service_name: {service_name}", messages, config=config)
    log_message(f"  portal_folder: {portal_folder}", messages, config=config)
    log_message(f"  share_with: {share_with}", messages, config=config)
    log_message(f"  add_footprint: {add_footprint}", messages, config=config)
    log_message("  attach_images: NO_ATTACH", messages, config=config)
    log_message(f"  tags: {tags_str}", messages, config=config)
    log_message(f"  summary: {summary}", messages, config=config)

    try:
        arcpy.oi.GenerateServiceFromOrientedImageryDataset(
            in_oriented_imagery_dataset=aws_oid_fc,
            service_name=service_name,
            portal_folder=portal_folder,
            share_with=share_with,
            add_footprint=add_footprint,
            attach_images="NO_ATTACH",
            tags=tags_str,
            summary=summary
        )
        log_message(f"🌐 OID service '{service_name}' published successfully.", messages, config=config)

    except Exception as e:
        # Print full geoprocessing messages to aid debugging
        gp_messages = arcpy.GetMessages()
        log_message(f"❌ ArcPy tool failed: {e}\n{gp_messages}", messages, level="warning", config=config)
        raise

    return service_name
