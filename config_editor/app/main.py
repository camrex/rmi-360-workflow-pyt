# =============================================================================
# 🚀 Editor entry point (config_editor/app/main.py)
# -----------------------------------------------------------------------------
# Launches the native window (pywebview) hosting the web UI and wiring it to the
# ConfigEditorAPI. Run from the toolbox root:
#     python -m config_editor.app.main
# =============================================================================

from __future__ import annotations

from pathlib import Path


def main() -> None:
    import webview  # imported here so the headless core/tests never require it

    from config_editor.app.api import ConfigEditorAPI

    api = ConfigEditorAPI()
    web_dir = Path(__file__).resolve().parent / "web"
    window = webview.create_window(
        "RMI 360 Config Editor",
        str(web_dir / "index.html"),
        js_api=api,
        width=1180,
        height=800,
        min_size=(960, 640),
    )
    api.window = window
    webview.start()


if __name__ == "__main__":
    main()
