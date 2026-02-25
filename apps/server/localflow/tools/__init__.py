from .registry import ToolRegistry
from .open_links import OpenLinksTool

def build_registry() -> ToolRegistry:
    r = ToolRegistry()
    r.register(OpenLinksTool())
    return r