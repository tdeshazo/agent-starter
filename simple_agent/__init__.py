"""Local Gemma agent setup."""

from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from .agent import create_agent as create_agent

__all__ = ["create_agent"]


def __getattr__(name: str):
    # The standalone model launcher only needs package configuration.
    if name == "create_agent":
        from .agent import create_agent

        return create_agent
    raise AttributeError(f"module {__name__!r} has no attribute {name!r}")
