# =============================================================================
# 🧊 PyInstaller entry point (config_editor/packaging/launch.py)
# -----------------------------------------------------------------------------
# Thin launcher the exe boots from. The real entry point stays in
# config_editor.app.main so `python -m config_editor.app.main` keeps working.
# Build: see config_editor/packaging/config_editor.spec header.
# =============================================================================

from config_editor.app.main import main

if __name__ == "__main__":
    main()
