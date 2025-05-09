import os
from typing import Optional
from utils.expression_utils import resolve_expression


def get_log_path(log_key: str, config: dict) -> str:
    """
    Constructs and returns the full file path for a log file based on the given log key and configuration.
    
    Retrieves the log directory and filename from the configuration, optionally prepending a dynamically resolved
    prefix to the filename. Ensures the log directory exists before returning the complete path.
    
    Args:
        log_key: The key identifying the log file in the configuration.
        config: The configuration dictionary containing log settings.
    
    Returns:
        The absolute path to the log file, with an optional prefix if specified in the configuration.
    
    Raises:
        ValueError: If the log filename is not a string, if the prefix resolves to an unsupported type, or if prefix
        resolution fails.
    """
    logs_cfg = config.get("logs", {})
    log_dir = os.path.join(config.get("__project_root__", "."), logs_cfg.get("path", "logs"))

    log_file = logs_cfg.get(log_key)
    if log_file is None:
        raise ValueError(f"logs.{log_key} is not defined in the configuration")
    if not isinstance(log_file, str):
        raise ValueError(f"logs.{log_key} must be a string filename, got {type(log_file).__name__}")

    # Get and resolve prefix (if any)
    prefix_expr = logs_cfg.get("prefix")
    prefix_str: Optional[str] = None
    if prefix_expr:
        try:
            prefix_str = resolve_expression(prefix_expr, config=config)
            if not isinstance(prefix_str, (str, int, float)):
                raise ValueError(f"logs.prefix resolved to unsupported type: {type(prefix_str).__name__}")
            prefix_str = str(prefix_str)
        except Exception as e:
            raise ValueError(f"Failed to resolve logs.prefix expression '{prefix_expr}': {str(e)}") from e

    # Insert prefix into filename if available
    if prefix_str and prefix_str.strip():
        base, ext = os.path.splitext(log_file)
        log_file = f"{prefix_str}_{base}{ext}"

    try:
        os.makedirs(log_dir, exist_ok=True)
    except OSError as e:
        raise ValueError(f"Failed to create log directory '{log_dir}'. {e}") from e

    return os.path.join(log_dir, log_file)
