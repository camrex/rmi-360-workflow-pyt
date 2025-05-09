import boto3
import json
from datetime import datetime, timezone
from botocore.exceptions import ClientError

s3 = boto3.client("s3")

# Replace these with fallback defaults
DEFAULT_BUCKET = "rmi-orient-img"
DEFAULT_PROJECT_SLUG = "default"
FAIL_THRESHOLD = 6  # e.g. 6 x 5-minute intervals = 30 minutes


def generate_html(status, count, percent, eta_hr, eta_min, eta_sec, elapsed_min, avg_time, start, end_time,
                  project_info, camera_info, cloud_info, expected_total):
    """
    Generates an HTML dashboard summarizing the status of an image upload process.

    The HTML page displays project, camera, and cloud export information, along with a visual upload progress bar,
    status indicator, counts, percentages, elapsed time, estimated time remaining (ETA), and average time per image.
    The dashboard is styled for clarity and includes auto-refresh and last updated timestamps.

    Args:
        status: Current upload status ("In Progress", "Complete", or "Failed").
        count: Number of images uploaded so far.
        percent: Percentage of images uploaded.
        eta_hr: Estimated hours remaining.
        eta_min: Estimated minutes remaining.
        eta_sec: Estimated seconds remaining.
        elapsed_min: Elapsed time in minutes since upload started.
        avg_time: Average time per image in seconds.
        start: UTC datetime when the upload started.
        end_time: UTC datetime when the upload ended, or None if ongoing.
        project_info: Dictionary with project metadata.
        camera_info: Dictionary with camera metadata.
        cloud_info: Dictionary with cloud storage metadata.
        expected_total: Total number of images expected to be uploaded.

    Returns:
        A string containing the complete HTML for the status dashboard.
    """

    status_colors = {
        "In Progress": "#2b8eff",
        "Complete": "#28a745",
        "Failed": "#dc3545"
    }
    status_color = status_colors.get(status, "#888")

    percent_display = f"{percent:.2f}%" if expected_total > 0 else "—"
    percent_bar_width = f"{percent:.2f}%" if expected_total > 0 else "0%"
    count_display = f"{count:,}" if isinstance(count, (int, float)) else str(count)
    total_display = f"{expected_total:,}" if isinstance(expected_total, (int, float)) else str(expected_total)

    html = f"""
    <!DOCTYPE html>
    <html lang='en'>
    <head>
        <meta charset='UTF-8'>
        <title>RMI Mosaic 360 Tool</title>
        <meta http-equiv='refresh' content='60'>
        <link href='https://fonts.googleapis.com/css2?family=Inter:wght@400;600&display=swap' rel='stylesheet'>
        <style>
            body {{
                font-family: 'Inter', sans-serif;
                background: linear-gradient(to right, #0f2027, #203a43, #2c5364);
                color: #f4f4f4;
                margin: 0;
                padding: 2rem;
            }}
            .container {{
                max-width: 900px;
                margin: auto;
                background: rgba(255, 255, 255, 0.05);
                border-radius: 12px;
                box-shadow: 0 0 20px rgba(0,0,0,0.25);
                padding: 2rem;
                backdrop-filter: blur(8px);
            }}
            header {{
                text-align: center;
                margin-bottom: 2rem;
            }}
            h1 {{
                font-size: 2rem;
                color: #00c6ff;
                margin-bottom: 0.5rem;
            }}
            .info-grid {{
                display: flex;
                justify-content: space-between;
                gap: 2rem;
                margin-bottom: 2rem;
            }}
            .card {{
                flex: 1;
                background: rgba(255, 255, 255, 0.08);
                padding: 1rem;
                border-radius: 8px;
            }}
            .card h3 {{
                border-bottom: 1px solid #666;
                padding-bottom: 0.3rem;
                margin-top: 0;
            }}
            .metric {{
                margin: 0.4rem 0;
                font-size: 0.95rem;
            }}
            h2 {{
                color: #00f7ff;
                margin-top: 2rem;
                font-size: 1.5rem;
            }}
            .progress-container {{
                background-color: #444;
                border-radius: 25px;
                height: 20px;
                width: 100%;
                overflow: hidden;
                margin: 1rem 0;
            }}
            .progress-bar {{
                height: 100%;
                width: {percent_bar_width};
                background: linear-gradient(90deg, #00c6ff 0%, #0072ff 100%);
            }}
            .status-pill {{
                display: inline-block;
                padding: 0.25rem 0.75rem;
                border-radius: 20px;
                font-weight: 600;
                font-size: 0.95rem;
                background-color: {status_color};
                color: white;
            }}
            .footer {{
                font-size: 0.85rem;
                color: #ccc;
                margin-top: 2rem;
                border-top: 1px solid #555;
                padding-top: 1rem;
            }}
        </style>
    </head>
    <body>
        <div class='container'>
            <header>
                <img src='https://rmi-orient-img.s3.amazonaws.com/status/rmi_logo.png' alt='RMI Logo' height='60'><br>
                <h1>RMI Mosaic 360 Tool</h1>
            </header>

            <div class='info-grid'>
                <div class='card'>
                    <h3>📁 Project Information</h3>
                    <p class='metric'><strong>Project:</strong> {project_info.get("number", "Unknown")} ({project_info.get("slug", "N/A")})</p>
                    <p class='metric'><strong>Client:</strong> {project_info.get("client", "—")}</p>
                    <p class='metric'><strong>Railroad:</strong> {project_info.get("railroad_name", "—")} ({project_info.get("railroad_code", "—")})</p>
                    <p class='metric'><strong>Description:</strong> {project_info.get("description", "—")}</p>
                </div>
                <div class='card'>
                    <h3>📷 Camera Information</h3>
                    <p class='metric'><strong>Make:</strong> {camera_info.get("make", "—")}</p>
                    <p class='metric'><strong>Model:</strong> {camera_info.get("model", "—")} ({camera_info.get("serial_number", "—")})</p>
                    <p class='metric'><strong>Firmware:</strong> {camera_info.get("firmware", "—")}</p>
                    <p class='metric'><strong>Software:</strong> {camera_info.get("software", "—")}</p>
                </div>
            </div>

            <h2>🚀 Upload Status Dashboard</h2>
            <p><strong>Status:</strong> <span class='status-pill'>{status}</span></p>
            <div class='progress-container'>
                <div class='progress-bar'></div>
            </div>
            <p class='metric'>{count_display} of {total_display} images uploaded ({percent_display})</p>
            <p class='metric'><strong>Start Time:</strong> {start.strftime('%Y-%m-%d %H:%M:%S UTC')}</p>
            <p class='metric'><strong>Elapsed Time:</strong> ~{elapsed_min:.1f} minutes</p>
            <p class='metric'><strong>ETA:</strong> {eta_hr}:{eta_min:02}:{eta_sec:02}</p>
            <p class='metric'><strong>Avg. Time per Image:</strong> {avg_time:.1f} sec</p>
            {f"<p class='metric'><strong>End Time:</strong> {end_time.strftime('%Y-%m-%d %H:%M:%S UTC')}</p>" if end_time else ""}

            <div class='card' style='margin-top: 2rem;'>
                <h3>☁️ Cloud Export</h3>
                <p class='metric'><strong>Bucket:</strong> {cloud_info.get("bucket", "—")}</p>
                <p class='metric'><strong>Folder:</strong> {cloud_info.get("prefix", "—")}</p>
            </div>

            <div class='footer'>
                <p>🔃 Last updated: {datetime.now(timezone.utc).strftime('%Y-%m-%d %H:%M:%S UTC')}</p>
                <p>🔁 Page refreshes every minute, while Lambda data updates every 5 minutes.</p>
            </div>
        </div>
    </body>
    </html>
    """
    return html.strip()


def lambda_handler(event, context):
    """
    AWS Lambda handler that monitors image upload progress for a project in S3, updates progress metadata, and generates
    a live HTML status dashboard.
    
    This function retrieves or initializes progress data for a given project, counts uploaded images in the specified
    S3 bucket and prefix, calculates progress metrics (percentage complete, ETA, average time per image), and determines
    the current upload status ("In Progress", "Complete", or "Failed"). If the upload is complete or has stalled beyond
    a threshold, it attempts to disable the associated CloudWatch monitoring rule. The function updates the progress
    JSON and generates an HTML dashboard, saving both to S3. Returns an HTTP 200 response summarizing the current status.
    
    Args:
        event: Lambda event payload containing optional 'project_slug', 'bucket', and 'prefix'.
        context: Lambda context object.
    
    Returns:
        dict: HTTP response with status code and a summary message.
    """
    project_slug = event.get("project_slug", DEFAULT_PROJECT_SLUG)
    bucket = event.get("bucket", DEFAULT_BUCKET)

    progress_key = f"status/progress_{project_slug}.json"
    status_key = "status/status.html"

    # Try loading project-specific progress file
    try:
        res = s3.get_object(Bucket=bucket, Key=progress_key)
        progress_data = json.loads(res["Body"].read())
    except ClientError as e:
        if e.response['Error']['Code'] == 'NoSuchKey':
            progress_data = {
                "project_slug": project_slug,
                "start_time": datetime.now(timezone.utc).isoformat(),
                "upload_status": "In Progress"
            }
        else:
            raise
    prefix = event.get("prefix") or progress_data.get("project_info", {}).get("number", project_slug) + "/"

    now = datetime.now(timezone.utc)

    # Pull metadata from stored progress file
    project_info = progress_data.get("project_info", {})
    camera_info = progress_data.get("camera_info", {})
    cloud_info = progress_data.get("cloud_info", {
        "bucket": bucket,
        "prefix": prefix
    })
    expected_total = progress_data.get("expected_total", 1)

    # Count uploaded images and find earliest LastModified
    count = 0
    earliest = None
    paginator = s3.get_paginator("list_objects_v2")
    for page in paginator.paginate(Bucket=bucket, Prefix=prefix):
        for obj in page.get("Contents", []):
            count += 1
            mod_time = obj["LastModified"]
            if earliest is None or mod_time < earliest:
                earliest = mod_time

    start = earliest or datetime.fromisoformat(progress_data.get("start_time"))
    elapsed = (now - start).total_seconds()
    elapsed_min = elapsed / 60

    if expected_total > 0:
        percent = min((count / expected_total) * 100, 100.0)
        remaining = expected_total - count
        avg_time = elapsed / count if count > 0 else 0
        eta = remaining * avg_time
        eta_min, eta_sec = divmod(int(eta), 60)
        eta_hr, eta_min = divmod(eta_min, 60)
    else:
        percent = 0.0
        avg_time = 0
        eta_hr = eta_min = eta_sec = 0
        print("[WARN] expected_total is 0 — skipping percent and ETA calculation.")

    # Status logic
    last_count = progress_data.get("count", 0)
    stalls = progress_data.get("stalls", 0)

    if count >= expected_total:
        status = "Complete"
        end_time = now
        stalls = 0
    elif count == last_count:
        stalls += 1
        status = "Failed" if stalls >= FAIL_THRESHOLD else "In Progress"
        end_time = now if status == "Failed" else None
    else:
        status = "In Progress"
        stalls = 0
        end_time = None

    # Optionally disable the CloudWatch rule if upload is done or failed
    if status in ("Complete", "Failed"):
        try:
            lambda_client = boto3.client("lambda")
            lambda_client.invoke(
                FunctionName="DisableUploadMonitorRule",
                InvocationType="Event",  # async call
                Payload=json.dumps({
                    "rule_name": "UploadProgressScheduleRule",
                    "region": cloud_info.get("region", "us-east-2")  # fallback default
                }).encode("utf-8")
            )
        except Exception as e:
            print(f"[WARN] Failed to invoke DisableUploadMonitorRule: {e}")

    # Update progress data
    progress_data.update({
        "last_updated": now.isoformat(),
        "start_time": start.isoformat(),
        "end_time": end_time.isoformat() if end_time else None,
        "upload_status": status,
        "stalls": stalls,
        "count": count,
        "expected_total": expected_total,
        "percent_complete": percent,
        "avg_time_per_image": avg_time,
        "project_info": project_info,
        "camera_info": camera_info,
        "cloud_info": cloud_info
    })

    # Write status.html
    html = generate_html(
        status=status,
        count=count,
        percent=percent,
        eta_hr=eta_hr,
        eta_min=eta_min,
        eta_sec=eta_sec,
        elapsed_min=elapsed_min,
        avg_time=avg_time,
        start=start,
        end_time=end_time,
        project_info=project_info,
        camera_info=camera_info,
        cloud_info=cloud_info,
        expected_total=expected_total
    )
    try:
        s3.put_object(
            Bucket=bucket,
            Key=status_key,
            Body=html.encode("utf-8"),
            ContentType="text/html"
        )
    except Exception as e:
        print(f"[ERROR] Failed to save status HTML: {e}")
        # Continue execution - we still want to try saving the JSON

    # Save updated progress file
    try:
        s3.put_object(
            Bucket=bucket,
            Key=progress_key,
            Body=json.dumps(progress_data, indent=2).encode("utf-8"),
            ContentType="application/json"
        )
    except Exception as e:
        print(f"[ERROR] Failed to save progress JSON: {e}")

    return {
        "statusCode": 200,
        "body": f"Status updated for {project_slug}: {status} ({count}/{expected_total})"
    }
