"""Collect terminal header context and format its session details."""

import os
from importlib.metadata import PackageNotFoundError, version

from ..conversation import SessionDetails


def header_context() -> dict[str, str | None]:
    directory = os.getcwd()
    home = os.path.expanduser("~")
    if directory == home or directory.startswith(home + os.sep):
        directory = "~" + directory[len(home) :]
    try:
        app_version = version("simple-agent")
    except PackageNotFoundError:
        app_version = None
    return {"directory": directory, "app_version": app_version}


def session_info(
    details: SessionDetails, context: dict[str, str | None] | None = None
) -> dict[str, str | None]:
    return {
        **(header_context() if context is None else context),
        "model": details.model,
        "endpoint": details.endpoint,
        "agent_name": details.name,
    }
