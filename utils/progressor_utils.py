import arcpy
import sys
from typing import Optional
from utils.arcpy_utils import log_message


class Progressor:
    def __init__(self, total: int, label: str = "Processing...", step: int = 1, messages: Optional[list] = None):
        """
        Initializes a Progressor instance for tracking and reporting progress.
        
        Args:
            total: The total number of steps to track.
            label: The label to display for the progressor.
            step: The increment value for each progress update.
            messages: Optional list to collect log messages.
        """
        self.total = total
        self.label = label
        self.step = step
        self.messages = messages or []
        self.use_progressor = False
        self.completed = 0

    def __enter__(self):
        """
        Initializes the ArcGIS Pro progressor if possible when entering the context.
        
        If initialization fails or the total is not positive, disables ArcGIS progressor usage and falls back to CLI
        output.
        
        Returns:
            The Progressor instance.
        """
        if self.total > 0:
            try:
                arcpy.SetProgressor("step", self.label, 0, self.total, self.step)
                self.use_progressor = True
            except Exception as e:
                log_message(f"[WARNING] Could not initialize ArcGIS Pro progressor: {e}", self.messages)
        return self

    def update(self, pos: int, label: Optional[str] = None):
        """
        Updates the progress display to the specified position, optionally updating the label.
        
        If the ArcGIS progressor is active, updates its label and position; otherwise, prints progress to the console
        as a percentage.
        """
        self.completed = pos
        if self.use_progressor:
            try:
                if label:
                    arcpy.SetProgressorLabel(label)
                arcpy.SetProgressorPosition(pos)
            except Exception as e:
                log_message(f"[WARNING] Progressor update failed: {e}", self.messages)
                self.use_progressor = False

        if not self.use_progressor:
            percent = (pos / self.total) * 100 if self.total > 0 else 0
            label_str = label or f"Progress: {pos}/{self.total}"
            sys.stdout.write(f"\r{label_str} ({percent:.1f}%)")
            sys.stdout.flush()

    def __exit__(self, exc_type, exc_val, exc_tb):
        """
        Cleans up progress reporting resources when exiting the context.
        
        If the ArcGIS progressor was used, attempts to reset it; otherwise, ensures CLI output formatting by printing
        a newline.
        """
        if self.use_progressor:
            try:
                arcpy.ResetProgressor()
            except Exception as e:
                log_message(f"[WARNING] Could not reset progressor: {e}", self.messages)
        else:
            print()  # Ensure newline after CLI progress
