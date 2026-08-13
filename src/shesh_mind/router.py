"""Role-to-model routing for the local LLM stack.

The laptop has an RTX 4050 / 6 GB VRAM, so model choices are constrained.
The router maps abstract roles (planner, coder, vision) to concrete installed
models, with sensible fallbacks and user overrides.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from enum import StrEnum


class Role(StrEnum):
    PRIMARY = "primary"
    PLANNER = "planner"
    CODER = "coder"
    RESEARCHER = "researcher"
    VISION = "vision"
    CRITIC = "critic"
    EMBEDDING = "embedding"


# Models known to fit 6 GB. Values are Ollama model tags.
DEFAULT_MODELS: dict[Role, str] = {
    Role.PRIMARY: "phi4-mini:latest",
    Role.PLANNER: "phi4-mini:latest",
    Role.CODER: "qwen2.5-coder:3b",
    Role.RESEARCHER: "phi4-mini:latest",
    Role.VISION: "moondream2:latest",
    Role.CRITIC: "phi4-mini:latest",
    Role.EMBEDDING: "nomic-embed-text:latest",
}

# Rough VRAM footprint in GB; used to refuse loading two large models at once.
MODEL_VRAM_GB: dict[str, float] = {
    "phi4-mini:latest": 2.5,
    "qwen2.5-coder:3b": 2.8,
    "gemma2:2b": 2.0,
    "moondream2:latest": 2.2,
    "nomic-embed-text:latest": 0.6,
}


@dataclass
class RoutingDecision:
    role: Role
    model: str
    reason: str
    vram_gb: float


@dataclass
class RouterConfig:
    """User-tunable routing config."""
    models: dict[Role, str] = field(default_factory=lambda: dict(DEFAULT_MODELS))
    max_vram_gb: float = 5.5
    prefer_code_model: bool = True
    fallback_chain: dict[Role, list[Role]] = field(default_factory=lambda: {
        Role.CODER: [Role.PRIMARY],
        Role.VISION: [],          # no text fallback for vision
        Role.EMBEDDING: [],
    })


class ModelRouter:
    def __init__(self, config: RouterConfig | None = None) -> None:
        self.config = config or RouterConfig()

    def select(self, role: Role, *, loaded: set[str] | None = None,
               allow_vision: bool = True) -> RoutingDecision:
        """Pick a model for a role, considering what's already loaded."""
        loaded = loaded or set()
        model = self.config.models[role]

        # Vision is special: refuse silently if disabled (caller can fall back).
        if role == Role.VISION and not allow_vision:
            primary = self.config.models[Role.PRIMARY]
            return RoutingDecision(Role.PRIMARY, primary,
                                   "vision disabled; using primary model",
                                   self._vram(primary))

        # If the chosen model would exceed remaining VRAM, prefer a loaded one
        # or walk the fallback chain.
        used = sum(self._vram(m) for m in loaded)
        if used + self._vram(model) > self.config.max_vram_gb:
            for fb_role in self.config.fallback_chain.get(role, []):
                fb_model = self.config.models[fb_role]
                if used + self._vram(fb_model) <= self.config.max_vram_gb:
                    return RoutingDecision(fb_role, fb_model,
                                           f"{role.value} model exceeds VRAM; fallback",
                                           self._vram(fb_model))
            # If a suitable model is already loaded, reuse it.
            for m in loaded:
                if self._vram(m) <= self.config.max_vram_gb - used:
                    return RoutingDecision(role, m,
                                           "reusing already-loaded model",
                                           self._vram(m))
            return RoutingDecision(role, model,
                                   "warning: would exceed VRAM budget",
                                   self._vram(model))

        return RoutingDecision(role, model, "default mapping", self._vram(model))

    def _vram(self, model: str) -> float:
        return MODEL_VRAM_GB.get(model, 3.0)

    def override(self, role: Role, model: str) -> None:
        self.config.models[role] = model

    def plan_session(self, roles: list[Role]) -> list[RoutingDecision]:
        """Plan models for a whole session, loading the fewest distinct models."""
        decided: list[RoutingDecision] = []
        loaded: set[str] = set()
        for role in roles:
            d = self.select(role, loaded=loaded)
            decided.append(d)
            loaded.add(d.model)
        return decided
