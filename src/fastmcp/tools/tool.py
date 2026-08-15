"""fastmcp.tools.tool stub."""

class ToolResult:
    """Minimal ToolResult stub."""""
    def __init__(self, ok: bool, content: str | list | None = None, error: str | None = None) -> None:
        self.ok = ok
        self.content = content
        self.error = error
