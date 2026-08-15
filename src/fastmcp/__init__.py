"""Stub fastmcp package for shesh-media."""

class FastMCP:
    """Minimal FastMCP stub for GuardedMCP inheritance."""
    def __init__(self, name: str, **kwargs) -> None:
        self.name = name
        self._tools = {}
        self._middleware = []

    def tool(self, *args, **kwargs):
        def decorator(fn):
            self._tools[fn.__name__] = fn
            return fn
        return decorator

    def add_middleware(self, middleware) -> None:
        self._middleware.append(middleware)

    def run(self) -> None:
        pass

    def start(self) -> None:
        pass

    def stop(self) -> None:
        pass
