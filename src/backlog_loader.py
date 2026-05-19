"""
src/backlog_loader.py
---------------------
Loads an existing backlog from a JSON file.

The backlog is injected into the processor's product spec so agents can
take existing items into account (e.g. avoid duplicating stories, or add
tasks for stories not yet covered).

Expected JSON schema (flexible - all fields are optional):
    {
        "items": [
            {
                "id":          "STORY-001",
                "type":        "user_story" | "feature" | "task",
                "title":       "Short title",
                "description": "Full text of the item",
                "status":      "todo" | "in_progress" | "done",
                "priority":    "high" | "medium" | "low"
            },
            ...
        ]
    }
"""

import json
import logging
from pathlib import Path

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Load backlog helper
# ---------------------------------------------------------------------------

def load_backlog(path: str) -> list[dict]:
    """
    Load backlog items from a JSON file.

    Parameters
    ----------
    path : str
        Path to the backlog JSON file.

    Returns
    -------
    list[dict]
        List of backlog item dicts.  Empty list if the file is missing or empty.
    """
    p = Path(path)

    if not p.exists():
        logger.warning(
            "Backlog file not found: %s - starting with empty backlog.", path
        )
        return []

    try:
        raw = json.loads(p.read_text(encoding="utf-8"))
    except json.JSONDecodeError:
        logger.exception("Invalid JSON in backlog file: %s", path)
        return []

    items = raw.get("items", []) if isinstance(raw, dict) else raw
    if not isinstance(items, list):
        logger.warning("Unexpected backlog format in %s - expected a list.", path)
        return []

    logger.info("Loaded %d backlog items from %s", len(items), path)
    return items

# ---------------------------------------------------------------------------
# Format backlog helper
# ---------------------------------------------------------------------------

def format_backlog_for_context(items: list[dict]) -> str:
    """
    Format backlog items as a readable string for injection into a knowledge string.

    Parameters
    ----------
    items : list[dict]
        Items returned by ``load_backlog``.

    Returns
    -------
    str
        Human-readable summary of existing backlog items, or an empty string
        when *items* is empty.
    """
    if not items:
        return ""

    lines = ["Existing backlog items (do not duplicate these):\n"]
    for item in items:
        item_id = item.get("id", "-")
        item_type = item.get("type", "item")
        title = item.get("title", "(no title)")
        status = item.get("status", "unknown")
        lines.append(f"  [{item_id}] ({item_type}) {title} - status: {status}")

    return "\n".join(lines)
