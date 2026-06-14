"""Runtime configuration: filesystem locations, resolved from env with defaults."""

from __future__ import annotations

import os
from pathlib import Path

ENV_PROFILE      = "GOOGLE_MCP_PROFILE"
ENV_DOWNLOAD_DIR = "GOOGLE_MCP_DOWNLOAD_DIR"


def _local_app_data() -> Path:
    if os.name == "nt":
        base = os.environ.get("LOCALAPPDATA")
        if base:
            return Path(base)
    base = os.environ.get("XDG_DATA_HOME")
    if base:
        return Path(base)
    return Path.home() / ".local" / "share"


def _downloads_root() -> Path:
    if os.name == "nt":
        user = os.environ.get("USERPROFILE")
        if user:
            return Path(user) / "Downloads"
    return Path.home() / "Downloads"


def profile_dir() -> Path:
    """Persistent Playwright profile dir (the reusable session jar)."""
    override = os.environ.get(ENV_PROFILE)
    if override:
        return Path(override).expanduser()
    return _local_app_data() / "google-session-mcp" / "profile"


def download_dir() -> Path:
    """Default destination for fetched Drive files."""
    override = os.environ.get(ENV_DOWNLOAD_DIR)
    if override:
        return Path(override).expanduser()
    return _downloads_root() / "google-session-mcp"
