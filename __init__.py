from importlib import import_module

_package = f"{__package__}.custom_api" if __package__ else "custom_api"
_nodes = import_module(f"{_package}.nodes")
NODE_CLASS_MAPPINGS = _nodes.NODE_CLASS_MAPPINGS
NODE_DISPLAY_NAME_MAPPINGS = _nodes.NODE_DISPLAY_NAME_MAPPINGS

WEB_DIRECTORY = "./web"
__version__ = "0.2.2"
__all__ = ["NODE_CLASS_MAPPINGS", "NODE_DISPLAY_NAME_MAPPINGS", "WEB_DIRECTORY"]

# The core package can be imported in tests without a running ComfyUI server.
try:
    from server import PromptServer
except ModuleNotFoundError as exc:
    if exc.name != "server":
        raise
else:
    _runtime = import_module(f"{_package}.runtime")
    import_module(f"{_package}.routes").register_routes(PromptServer.instance.routes, _runtime.store, _runtime.engine)
