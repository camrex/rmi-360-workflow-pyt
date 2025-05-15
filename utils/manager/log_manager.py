# =============================================================================
# 🗾 Log Manager Utility (utils/manager/log_manager.py)
# -----------------------------------------------------------------------------
# Purpose:             Provides structured logging across CLI, ArcGIS, and web output
# Project:             RMI 360 Imaging Workflow Python Toolbox
# Version:             1.1.0
# Author:              RMI Valuation, LLC
# Created:             2025-05-11
# Last Updated:        2025-05-14
#
# Description:
#   Centralized logging framework that supports text, HTML, and JSON output.
#   Includes step-based indentation, duration tracking, context metadata, and
#   optional "celebration" features. Designed to support both ArcPy tools and
#   CLI pipelines. Compatible with PathManager for output directory control.
#
# File Location:        /utils/manager/log_manager.py
# Called By:            Tools, orchestrators, testing pipelines
# Int. Dependencies:    utils/manager/path_manager
# Ext. Dependencies:    json, time, html, contextlib, typing
#
# Documentation:
#   See: docs_legacy/LOG_MANAGER.md
#   (Ensure this doc is current; update if needed.)
#
# Notes:
#   - HTML logs are collapsible with toggleable timestamps
#   - JSON output includes metadata for downstream automation
#   - Supports playful methods like .party(), .fireworks(), and .success()
# =============================================================================

from datetime import datetime
from typing import Optional, List, Type, Dict, Generator
from contextlib import contextmanager
import time
import html
import json
from utils.manager.path_manager import PathManager

class LogManager:
    """
    LogManager provides structured logging for command-line, ArcGIS, and web-based workflows.

    Logs are collected in plain text, HTML, and JSON formats with support for:
    - Multiple log levels (info, warning, error, debug)
    - Step-based indentation and timing
    - Context metadata (tool, file, reel, etc.)
    - ArcGIS Pro messaging (if a message object is provided)
    - Export to .txt, .html, and .json files via PathManager

    Optional celebratory methods (.success(), .fireworks(), .party()) are included for end-of-run flair.
    Designed for use in orchestration scripts, CLI tools, and ArcGIS Python Toolbox tools.
    """

    LEVEL_PREFIX = {
        "debug": "🛠️",
        "info": "ℹ️",
        "warning": "⚠️",
        "error": "❌"
    }

    def __init__(
            self,
            messages=None,
            config: Optional[dict] = None,
            path_manager: Optional[PathManager] = None,
            enable_file_output: bool = True,
            pop_on_error: bool = True,
    ):
        """
        Initialize the LogManager.

        Args:
            messages (optional): ArcPy messaging object for integrated tool messages.
            config (dict, optional): Project-level configuration, including debug flag.
            path_manager (PathManager, optional): Provides log file directories.
            enable_file_output (bool): If True, log to .txt, .html, and .json files.
            pop_on_error (bool): If True, reduces stack depth and timing on error.
        """
        self.messages = messages
        self.config = config or {}
        self.path_manager = path_manager
        self.enable_file_output = enable_file_output
        self.pop_on_error = pop_on_error
        self.entries: List[str] = []
        self.html_blocks: List[str] = []
        self.records: List[Dict] = []
        self.depth = 0
        self.indent_char = "    "
        self._timing_stack: List[float] = []

    def log(self, msg: str, level: str = "info", error_type: Optional[Type[Exception]] = None, context: Optional[Dict] = None) -> None:
        """Log a message with a specified level, optional context, and error type.

        Args:
            msg (str): The message to log.
            level (str): Logging level ('info', 'warning', 'error', 'debug').
            error_type (Exception, optional): Exception to raise if level is 'error'.
            context (dict, optional): Metadata context appended and recorded.
        """
        valid_levels = {"debug", "info", "warning", "error"}
        if level not in valid_levels:
            self.log(f"⚠️ Invalid log level '{level}' (defaulting to info)", level="warning")
            level = "info"

        if level == "debug" and not self.config.get("debug_messages", False):
            return

        prefix = self.LEVEL_PREFIX.get(level, "")

        context_str = ""
        if context:
            context_str = "  " + " ".join(f"{k}={v}" for k, v in context.items())

        indent = self.indent_char * self.depth
        timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        iso_timestamp = datetime.now().isoformat()
        full_msg = f"[{timestamp}] {prefix} {indent}{msg}{context_str}"
        self.entries.append(full_msg)

        self.records.append({
            "timestamp": iso_timestamp,
            "level": level,
            "message": msg,
            "depth": self.depth,
            "context": context or {}
        })

        # Directly use the level variable for CSS class
        css_class = level

        html_line = f'<div class="{css_class}"><span class="ts">[{timestamp}]</span> {prefix} {html.escape(indent + msg + context_str)}</div>'
        self.html_blocks.append(html_line)

        if self.messages:
            if level == "warning" and hasattr(self.messages, "addWarningMessage"):
                self.messages.addWarningMessage(full_msg)
            elif level == "error" and hasattr(self.messages, "addErrorMessage"):
                self.messages.addErrorMessage(full_msg)
            elif hasattr(self.messages, "addMessage"):
                self.messages.addMessage(full_msg)
        else:
            print(full_msg)

        if self.enable_file_output and self.path_manager:
            try:
                log_file = self.path_manager.logs / "process_log.txt"
                log_file.parent.mkdir(parents=True, exist_ok=True)
                with open(log_file, "a", encoding="utf-8") as f:
                    f.write(full_msg + "\n")
            except Exception as e:
                # Use warning method for consistency, but avoid infinite recursion
                # by directly printing if we're already handling a warning
                if level == "warning":
                    print(f"⚠️ Could not write to log file: {e}")
                else:
                    self.warning(f"Could not write to log file: {e}")

        if level == "error":
            if self.pop_on_error:
                self.depth = max(0, self.depth - 1)
                if self._timing_stack:
                    self._timing_stack.pop()
            if error_type:
                raise error_type(full_msg)

    def info(self, msg: str, context: Optional[Dict] = None) -> None: self.log(msg, "info", context=context)
    def warning(self, msg: str, context: Optional[Dict] = None) -> None: self.log(msg, "warning", context=context)
    def error(self, msg: str, error_type: Type[Exception] = RuntimeError, context: Optional[Dict] = None) -> None: self.log(msg, "error", error_type=error_type, context=context)
    def debug(self, msg: str, context: Optional[Dict] = None) -> None: self.log(msg, "debug", context=context)

    def push(self, msg: str) -> None:
        """Start a new indented log section and begin timing it.

        Args:
            msg (str): Header message for the step or section.
        """
        self.info(msg)
        self.depth += 1
        self._timing_stack.append(time.time())
        indent = self.indent_char * (self.depth - 1)
        self.html_blocks.append(f'<details open><summary>{html.escape(indent + msg)}</summary><div class="block">')

    def pop(self, msg: Optional[str] = None) -> None:
        """End the most recent log section, record duration, and log exit message.

        Args:
            msg (str, optional): Optional message to log on exit. Elapsed time is auto-appended.
        """
        self.depth = max(0, self.depth - 1)
        elapsed = None
        if self._timing_stack:
            start_time = self._timing_stack.pop()
            elapsed = time.time() - start_time
        if msg:
            if elapsed is not None:
                elapsed_str = self._format_duration(elapsed)
                msg = f"{msg} (Elapsed: {elapsed_str})"
            self.info(msg)
        self.html_blocks.append("</div></details>")

    @staticmethod
    def _format_duration(seconds: float) -> str:
        mins, secs = divmod(int(seconds), 60)
        return f"{mins}m {secs}s" if mins else f"{secs}s"

    def get_messages(self) -> List[str]:
        return self.entries

    def export_txt(self, filename: str = "process_log.txt") -> None:
        """Export plain text log to .txt file.

        Args:
            filename (str): Output filename for the text log.
        """
        if not self.path_manager:
            self.warning("[LogManager] No PathManager available for export_txt().")
            return
        try:
            txt_path = self.path_manager.logs / filename
            with open(txt_path, "w", encoding="utf-8") as f:
                for msg in self.entries:
                    f.write(msg + "\n")
        except Exception as e:
            self.warning(f"Failed to write TXT log: {e}")

    def export_json(self, filename: str = "process_log.json") -> None:
        """Export log records to a structured JSON file.

        Args:
            filename (str): Filename for the JSON export.
        """
        if not self.path_manager:
            self.warning("[LogManager] No PathManager available for export_json().")
            return
        try:
            json_path = self.path_manager.logs / filename
            with open(json_path, "w", encoding="utf-8") as f:
                json.dump(self.records, f, indent=2)
        except Exception as e:
            self.warning(f"Failed to export JSON log: {e}")

    def export_html(self, filename: Optional[str] = "process_log.html") -> None:
        """Export log output to an HTML file with collapsible blocks.

        Args:
            filename (str): Output filename for the HTML log.
        """
        if not self.path_manager:
            self.warning("[LogManager] No PathManager available for export_html().")
            return
        try:
            html_path = self.path_manager.logs / filename
            html_path.parent.mkdir(parents=True, exist_ok=True)
            with open(html_path, "w", encoding="utf-8") as f:
                f.write(HTML_LOG_TEMPLATE_HEAD)
                for line in self.html_blocks:
                    f.write(line + "\n")
                f.write(HTML_LOG_TEMPLATE_FOOT)
        except Exception as e:
            self.warning(f"Failed to export HTML log: {e}")

    def export_all(self, basename: str = "process_log") -> None:
        """Export log to .txt, .html, and .json using a common base filename."""
        self.export_txt(f"{basename}.txt")
        self.export_json(f"{basename}.json")
        self.export_html(f"{basename}.html")

    def success(self, msg: Optional[str] = None) -> None:
        """Log a celebratory 'success' message with confetti emoji."""
        msg = msg or "🎉 ALL DONE! Time to celebrate."
        self.info(msg)

    def party(self) -> None:
        """Log an ASCII party message to signal celebration."""
        self.info("(>'-')> <('-'<) ^('-')^ v('-')v  🎉 PARTY MODE ACTIVATED!")

    def fireworks(self) -> None:
        """Log celebratory emoji fireworks."""
        self.info("🎆 🎇 🎉 💥 💫 ✨")

    def rickroll(self) -> None:
        """Log a playful rickroll message."""
        self.info("🎵 Never gonna give you up, never gonna let you down! 🎵")

    @contextmanager
    def step(self, title: str, end_msg: Optional[str] = None) -> Generator[None, None, None]:
        """Context manager for structured, indented logging steps.

        Args:
            title (str): The block header or step name.
            end_msg (str, optional): Custom exit message for success.
        """
        self.push(title)
        try:
            yield
        except Exception as e:
            self.pop(f"❌ {title} failed: {e}")
            raise
        else:
            self.pop(end_msg or f"✅ {title} complete")

# --- HTML Log Template Components ---

HTML_LOG_TEMPLATE_HEAD = """
<!DOCTYPE html>
<html><head>
<meta charset="UTF-8">
<title>Process Log</title>
<style>
    body {
        font-family: "Fira Code", Consolas, monospace;
        background-color: #ffffff;
        color: #222;
        padding: 2em;
        line-height: 1.6;
    }
    h1 {
        font-size: 1.8em;
        margin-bottom: 0.5em;
    }
    summary {
        font-weight: bold;
        font-size: 1.05em;
        cursor: pointer;
        margin-top: 1em;
        color: #333;
    }
    .ts {
        color: #888;
        font-size: 0.9em;
        display: inline-block;
        width: 180px;
        margin-right: 1em;
    }
    .info {
        color: #333;
    }
    .warning {
        color: #e65100;
        background-color: #fff8e1;
        padding: 2px 4px;
        border-left: 4px solid #f57c00;
    }
    .error {
        color: #b71c1c;
        background-color: #ffebee;
        padding: 2px 4px;
        border-left: 4px solid #d32f2f;
        font-weight: bold;
    }
    .debug {
        color: #777;
        font-style: italic;
    }
    .block {
        margin-left: 1.5em;
    }
    pre {
        white-space: pre-wrap;
    }
    label {
        font-size: 0.9em;
        display: block;
        margin-bottom: 1em;
        color: #444;
    }
</style>
<script>
function toggleTimestamps() {
    const ts = document.querySelectorAll('.ts');
    ts.forEach(span => span.style.display = span.style.display === 'none' ? 'inline-block' : 'none');
}
</script>
</head>
<body>
<h1>📄 Process Log</h1>
<label><input type="checkbox" onclick="toggleTimestamps()"> Show/Hide Timestamps</label>
<hr>
"""

HTML_LOG_TEMPLATE_FOOT = "</body></html>"
