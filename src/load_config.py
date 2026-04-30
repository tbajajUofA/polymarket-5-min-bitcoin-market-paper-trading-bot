"""
Configuration loader.

The project uses ``config.yaml`` for API paths, model paths, thresholds, and
collector defaults. This helper centralizes YAML parsing so callers get a clear
exception when the file is missing or malformed.
"""

import yaml

def load_config(path="config.yaml"):
    """Load and validate a YAML config file."""
    try:
        with open(path, "r") as f:
            config = yaml.safe_load(f)
        if config is None:
            raise ValueError("Config file is empty")
        return config
    except FileNotFoundError:
        raise FileNotFoundError(f"{path} not found")
    except yaml.YAMLError as e:
        raise ValueError(f"Error parsing YAML: {e}")
