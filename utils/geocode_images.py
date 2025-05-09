___all___ = ["geocode_images"]

import os
import subprocess
import arcpy
from typing import Optional
from utils.config_loader import resolve_config
from utils.arcpy_utils import validate_fields_exist, log_message
from utils.path_utils import get_log_path


def geocode_images(
        oid_fc: str,
        config: Optional[dict] = None,
        config_file: Optional[str] = None,
        messages=None) -> None:
    """
    Applies reverse geocoding tags to images in a feature class using ExifTool.

    This function processes each image referenced in the input feature class, copying GPSPosition metadata to the XMP
    geolocate tag using ExifTool. It supports different ExifTool geolocation databases as specified in the
    configuration. Images without valid paths are skipped, and all actions are logged. The function writes ExifTool
    argument and log files, then executes the ExifTool command to update image metadata in place.
    """
    config = resolve_config(
        config=config,
        config_file=config_file,
        oid_fc_path=oid_fc,
        messages=messages,
        tool_name="geocode_images")

    geocoding_cfg = config.get("geocoding", {})
    method = geocoding_cfg.get("method", "").lower()

    if method != "exiftool":
        log_message("🔕 Geocoding skipped (unsupported method)", messages, level="warning", config=config)
        return

    db_choice = geocoding_cfg.get("exiftool_geodb", "default").lower()
    log_message(f"🌍 Using geolocation DB: {db_choice}", messages, config=config)
    exiftool_cmd = ["exiftool"]

    # Config validation (including ExifTool config path + geoDir check) is performed by validate_config.py.
    # This script assumes config has already been validated.

    # Handle alternate DBs with config files
    if db_choice in {"geolocation500", "geocustom"}:
        key = "geoloc500_config_path" if db_choice == "geolocation500" else "geocustom_config_path"
        config_path = geocoding_cfg.get(key)
        exiftool_cmd.extend(["-config", os.path.abspath(config_path)])

    # Prepare args + log files
    args_file = get_log_path("geocode_args", config)
    log_file = get_log_path("geocode_logs", config)
    lines = []
    log_entries = []

    # Ensure necessary fields exist
    required_fields = ["OID@", "ImagePath", "X", "Y"]
    validate_fields_exist(oid_fc, ["ImagePath", "X", "Y"])

    with arcpy.da.SearchCursor(oid_fc, required_fields) as cursor:
        for oid, path, x, y in cursor:
            if not os.path.exists(path):
                log_message(f"⚠️ Image path does not exist: {path}", messages, level="warning", config=config)
                continue

            lines.extend([
                "-overwrite_original_in_place",
                "-XMP:XMP-iptcExt:geolocate<gpsposition",
                path.replace('\\', '/'),
                "-execute",
                ""
            ])
            log_entries.append(f"📍 Geocoded OID {oid} → {os.path.basename(path)}")

    with open(args_file, "w", encoding="utf-8") as f:
        f.write("\n".join(lines))
    with open(log_file, "w", encoding="utf-8") as f:
        f.write("\n".join(log_entries))

    # Execute ExifTool command
    exiftool_cmd.extend(["-@", args_file])
    try:
        subprocess.run(exiftool_cmd, check=True)
        log_message("✅ Reverse geocoding completed.", messages, config=config)
    except subprocess.CalledProcessError as e:
        log_message(f"❌ ExifTool geocoding failed: {e}", messages, level="error", config=config)


if __name__ == "__main__":
    log_message("This is a library module. Import and call geocode_images(...) from your toolbox or script.")
