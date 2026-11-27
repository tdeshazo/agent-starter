"""Shared configuration for the model launcher and client."""

from collections.abc import Mapping


MODEL_HOST = "127.0.0.1"
MODEL_ID = "gemma-4-e4b"
DEFAULT_MODEL_PORT = "8088"


def model_port(env: Mapping[str, str]) -> str:
    return env.get("AGENT_PORT") or DEFAULT_MODEL_PORT
