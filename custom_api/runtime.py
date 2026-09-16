import os
from pathlib import Path

from .engine import Engine
from .store import ConfigStore


def config_directory():
    if os.environ.get("COMFYUI_CUSTOM_API_DIR"):
        return Path(os.environ["COMFYUI_CUSTOM_API_DIR"]).resolve()
    try:
        import folder_paths
    except ImportError:
        return Path(__file__).resolve().parents[1] / "data"
    return Path(folder_paths.get_system_user_directory("custom_api"))


store = ConfigStore(config_directory())
engine = Engine(store)
