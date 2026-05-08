"""
src/backlog_loader.py
=====================
Loads existing backlog items from a JSON file.

Expected JSON format (flexible):
  - Array of objects, each with at minimum an "id" and "title" or "summary"
  - Additional fields (status, priority, etc.) are passed through as-is

Candidate note: extend this to support:
  - Jira REST API
  - Linear API
  - GitHub Issues API
  - CSV export from project management tools
"""

import json
import logging
from pathlib import Path
from typing import Any

logger = logging.getLogger(__name__)


def load_backlog(path: str) -> list[dict[str, Any]]:
    """
    Load existing backlog items from a JSON file.

    Args:
        path: Path to a JSON file containing backlog items.

    Returns:
        List of backlog item dicts.

    Raises:
        FileNotFoundError: If the file does not exist.
        ValueError: If the file is not valid JSON or not a list.
    """
    file_path = Path(path)

    if not file_path.exists():
        raise FileNotFoundError(f"Backlog file not found: {path}")

    logger.debug(f"Loading backlog from: {path}")

    try:
        with open(file_path, encoding="utf-8") as f:
            data = json.load(f)
    except json.JSONDecodeError as e:
        raise ValueError(f"Invalid JSON in backlog file: {e}")

    # Support both top-level array and {"items": [...]} wrapper
    if isinstance(data, list):
        items = data
    elif isinstance(data, dict) and "items" in data:
        items = data["items"]
    else:
        raise ValueError(
            "Backlog JSON must be an array of items, "
            "or an object with an 'items' array."
        )

    logger.info(f"Loaded {len(items)} backlog items")
    return items
