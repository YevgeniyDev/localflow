from .browser_automation import BrowserAutomationTool
from .open_links import OpenLinksTool
from .registry import ToolRegistry
from .search_web import SearchWebTool


def build_registry() -> ToolRegistry:
    r = ToolRegistry()
    r.register(OpenLinksTool())
    r.register(SearchWebTool())
    r.register(BrowserAutomationTool())
    return r
