"""fastmcp middleware stub."""

class Middleware:
    """Minimal Middleware stub."""
    def __init__(self, handler, *, actor: str | None = None) -> None:
        self.handler = handler
        self.actor = actor

    def __call__(self, *args, **kwargs) -> dict:
        return self.handler(*args, **kwargs)


class MiddlewareContext:
    """Minimal MiddlewareContext stub."""""
    def __init__(self, *, actor: str | None = None, message: dict | None = None) -> None:
        self.actor = actor
        self.message = message
