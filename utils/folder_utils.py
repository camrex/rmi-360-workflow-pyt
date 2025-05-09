import os
import humanize
from pathlib import Path


def folder_stats(path, extensions=None):
    """
    Calculate statistics for JPG files in a directory.

    Args:
        path (str): Path to the directory to analyze
        extensions (list, optional): List of file extensions to include (default: ['.jpg'])

    Returns:
        tuple: (number_of_files, human_readable_size)
            - number_of_files (int): Count of matching files
            - human_readable_size (str): Total size in human-readable format
    """
    if not path or not os.path.exists(path):
        return 0, "0 B"

    if extensions is None:
        extensions = ['.jpg']
    p = Path(path)
    jpg_files = []
    for ext in extensions:
        jpg_files.extend(list(p.rglob(f"*{ext}")))  # ✅ Recursively find all .jpg files
    total_size = sum(f.stat().st_size for f in jpg_files)
    return len(jpg_files), humanize.naturalsize(total_size, binary=True)
