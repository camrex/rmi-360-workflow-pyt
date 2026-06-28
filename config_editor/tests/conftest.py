import sys
from pathlib import Path

# Ensure the toolbox root (which contains the `config_editor` package) is importable.
TOOLBOX_ROOT = Path(__file__).resolve().parents[2]
if str(TOOLBOX_ROOT) not in sys.path:
    sys.path.insert(0, str(TOOLBOX_ROOT))
