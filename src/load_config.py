import yaml

def load_config(path="config.yaml"):
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