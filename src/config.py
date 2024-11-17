import os
from pathlib import Path
import yaml
from dotenv import load_dotenv

def load_config():
    """Load and process configuration from yaml and env vars."""
    load_dotenv()
    
    config_path = Path("config/config.yaml")
    if not config_path.exists():
        raise FileNotFoundError(
            "config.yaml not found. Please copy config.yaml.example to config.yaml and configure it."
        )
    
    with open(config_path, "r") as f:
        config = yaml.safe_load(f)
    
    def replace_env_vars(obj):
        if isinstance(obj, dict):
            return {k: replace_env_vars(v) for k, v in obj.items()}
        elif isinstance(obj, str) and obj.startswith("${") and obj.endswith("}"):
            env_var = obj[2:-1]
            return os.getenv(env_var, obj)
        return obj
    
    config = replace_env_vars(config)
    
    # Override with env vars if present
    if "SERVER_PORT" in os.environ:
        config["server"]["port"] = int(os.getenv("SERVER_PORT"))
    
    return config