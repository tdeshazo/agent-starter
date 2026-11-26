"""Read session metadata for the terminal header and status line."""
import os
from contextlib import contextmanager
from importlib.metadata import PackageNotFoundError, version
from urllib.parse import urlsplit


@contextmanager
def conversation_turn(messages: list):
    """Restore the conversation history when a turn fails or is interrupted."""
    history = messages.copy()
    try:
        yield
    except BaseException:
        messages[:] = history
        raise


def session_model_id(agent) -> str | None:
    """Read the model ID reported by the active model."""
    try:
        return agent.model.get_config().get("model_id")
    except Exception:
        return None


def session_info(agent) -> dict:
    """Describe the agent's model and endpoint for the header box."""
    model = getattr(agent, "model", None)
    base_url = (getattr(model, "client_args", None) or {}).get("base_url")
    endpoint = None
    if base_url:
        try:
            parts = urlsplit(base_url)
        except ValueError:
            pass
        else:
            host = parts.netloc.rsplit("@", 1)[-1]
            endpoint = host + parts.path.rstrip("/")
    directory = os.getcwd()
    home = os.path.expanduser("~")
    if directory == home or directory.startswith(home + os.sep):
        directory = "~" + directory[len(home) :]
    try:
        app_version = version("simple-agent")
    except PackageNotFoundError:
        app_version = None
    return {"model": session_model_id(agent), "endpoint": endpoint, "directory": directory, "app_version": app_version}


def total_tokens(agent) -> int:
    try:
        return int(agent.event_loop_metrics.accumulated_usage.get("totalTokens", 0))
    except Exception:
        return 0
