import os
import re
from pathlib import Path
from datetime import datetime, timezone
from typing import Dict, Any, Optional

from jinja2 import Environment, FileSystemLoader, select_autoescape
import matplotlib.pyplot as plt

from utils.arcpy_utils import log_message
from utils.schema_paths import resolve_schema_template_paths


def generate_full_process_report(
    report_data: Dict[str, Any],
    output_dir: str,
    output_basename: str = "report",
    messages=None
):
    """
    Generates a process report in HTML format, including charts and branding.
    
    Creates the output directory if needed, adds a UTC timestamp to the report data, generates chart images for images
    per reel and step execution times, and renders an HTML report using a Jinja2 template. Returns the paths to the
    generated HTML file.
    
    Args:
        report_data: Dictionary containing report content, including reels, steps, and configuration.
        output_dir: Directory where the report files will be saved.
        output_basename: Base filename for the output report files (default is "report").
        messages: Optional message collector for logging.
    
    Returns:
        A dictionary with key "html_path" indicating the location of the generated file.
    """
    os.makedirs(output_dir, exist_ok=True)
    report_data["generated_on"] = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M UTC")

    # Generate charts
    try:
        chart_path_images = os.path.join(output_dir, "chart_images_per_reel.png")
        chart_path_steps = os.path.join(output_dir, "chart_step_times.png")

        # Verify output directory is writable
        test_file = os.path.join(output_dir, ".write_test")
        try:
            with open(test_file, 'w') as f:
                f.write('test')
            os.remove(test_file)
        except (PermissionError, OSError) as e:
            log_message(f"[WARNING] Chart output directory not writable: {e}", messages, level="warning")
            raise

        plot_images_per_reel(report_data.get("reels", []), chart_path_images)
        plot_time_per_step(report_data.get("steps", []), chart_path_steps)
    except Exception as e:
        log_message(f"[WARNING] Failed to generate charts: {e}", messages, level="warning")

    try:
        resolved_paths = resolve_schema_template_paths(report_data.get("config", {}))
        template_dir_resolved = resolved_paths.templates_dir

        # Resolve absolute path to the logo file so it works in browser view
        logo_path = Path(template_dir_resolved) / "assets" / "rmi_logo.png"
        report_data["logo_path"] = logo_path.resolve().as_uri()

        log_message(f"[DEBUG] Resolved template dir: {template_dir_resolved}", messages, level="debug")
        template_path = os.path.join(template_dir_resolved, "process_report_template.html")
        log_message(f"[DEBUG] Checking for template file: {template_path}", messages, level="debug")

        if not os.path.exists(template_path):
            raise FileNotFoundError(
                f"Template file not found at: {template_path}. "
                f"Please ensure the template exists in the {template_dir_resolved} directory "
                f"or check the 'template.templates_dir' setting in your configuration."
            )

        env = Environment(
            loader=FileSystemLoader(template_dir_resolved),
            autoescape=select_autoescape(['html'])
        )

        template = env.get_template("process_report_template.html")
        html_out = template.render(**report_data)

        html_path = os.path.join(output_dir, f"{output_basename}.html")
        with open(html_path, "w", encoding="utf-8") as f:
            f.write(html_out)

        log_message(f"✅ HTML report written to: {html_path}", messages)

        return {
            "html_path": html_path
        }

    except Exception as e:
        log_message(f"[ERROR] Report generation failed: {type(e).__name__}: {e}", messages, level="error")
        raise  # Re-raise if you want upstream logic to catch this


def plot_images_per_reel(reels, output_path):
    """
    Generates and saves a bar chart visualizing the number of images for each reel.
    
    Args:
        reels: List of dictionaries containing reel information, each with 'reel' and 'image_count' keys.
        output_path: Path where the generated PNG chart will be saved.
    
    If the reels list is empty or None, no chart is generated.
    """
    if not reels:
        return
    reels_sorted = sorted(reels, key=lambda r: r["reel"])
    reel_ids = [f"RL{r['reel']}" for r in reels_sorted]
    counts = [r.get("image_count", 0) for r in reels_sorted]

    plt.figure(figsize=(10, 4))
    plt.bar(reel_ids, counts, color="#337ab7")
    plt.xlabel("Reel")
    plt.ylabel("Image Count")
    plt.title("Image Count per Reel")
    plt.tight_layout()
    plt.savefig(output_path)
    plt.close()


def extract_time_seconds(time_str: str) -> float:
    """Extracts the numeric value from a time string."""
    m = re.match(r"([0-9.]+)", str(time_str))
    return float(m.group(1)) if m else 0.0


def plot_time_per_step(steps, output_path, messages=None):
    """
    Generates a horizontal bar chart of execution times for completed workflow steps.
    
    Filters steps with a status of "✅", extracts their names and execution times, and saves
    the resulting chart as a PNG file to the specified output path.
    """
    steps_filtered = [s for s in steps if s["status"] == "✅"]
    step_names = [s["name"] for s in steps_filtered]
    times_sec = []

    # Process the execution times for each step
    for s in steps_filtered:
        try:
            times_sec.append(extract_time_seconds(s["time"]))  # Use the new time extraction function
        except Exception as e:
            # Log any errors, though the function itself ensures 0.0 is returned for invalid times
            log_message(f"Error processing time for step {s['name']}: {e}", messages, level="warning")
            times_sec.append(0.0)

    # Generate the bar chart
    plt.figure(figsize=(10, 6))
    plt.barh(step_names, times_sec, color="#5cb85c")
    plt.xlabel("Time (seconds)")
    plt.title("Execution Time per Workflow Step")
    plt.tight_layout()
    plt.savefig(output_path)
    plt.close()


def generate_report_from_json(
    json_path: str,
    output_dir: str = None,
    messages=None,
    config: Optional[dict] = None,
    config_file: Optional[str] = None
):
    """
    Generates a process report from a JSON file.
    
    Loads report data from the specified JSON file, attaches configuration data if provided or available, determines
    the output directory, and generates an HTML report. Raises an exception if report generation fails.
    """
    import json

    try:
        with open(json_path, "r", encoding="utf-8") as f:
            report_data = json.load(f)

        log_message(f"📄 Loaded report data from: {json_path}", messages, config=config)

        # Reattach config if missing or externally supplied
        if config:
            report_data["config"] = config
        elif config_file:
            from utils.config_loader import resolve_config
            resolved = resolve_config(config_file=config_file, messages=messages)
            report_data["config"] = resolved
        elif "config" not in report_data:
            log_message("[WARNING] Config not found in report JSON — some paths or logos may not resolve", messages,
                        config=config)

        # Derive output_dir if not supplied
        if not output_dir:
            output_dir = report_data.get("paths", {}).get("report_dir", os.path.dirname(json_path))

        return generate_full_process_report(
            report_data=report_data,
            output_dir=output_dir,
            messages=messages
        )

    except Exception as e:
        log_message(f"[ERROR] Failed to generate report from JSON: {e}", messages, level="error", config=config)
        raise
