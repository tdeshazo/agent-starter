"""Expose the local clock as a Strands tool."""

from datetime import datetime
from zoneinfo import ZoneInfo

from strands import tool


@tool
def current_time(timezone: str = "UTC") -> str:
    """Return the current time in an IANA timezone, such as America/New_York.

    Use this tool to answer questions about the current time.

    Args:
        timezone: IANA timezone name.
    """
    return datetime.now(ZoneInfo(timezone)).isoformat()
