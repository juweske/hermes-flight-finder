"""Local configuration paths for Hermes Flight Finder."""

from __future__ import annotations

import os
from pathlib import Path

DATA_DIR_ENV_VAR = "HERMES_FLIGHT_FINDER_DATA_DIR"


def get_data_dir() -> Path:
    """Return the configured local state directory without creating it."""
    configured = os.environ.get(DATA_DIR_ENV_VAR)
    if configured:
        return Path(configured).expanduser()
    return Path.home() / ".hermes-flight-finder"
