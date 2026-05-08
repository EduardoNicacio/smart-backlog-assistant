"""
src/formatter.py
================
Formats the raw AI output into the final output structure.

Candidate note: this is a good place to:
  - Add metadata (timestamp, model used, input file name)
  - Transform user stories into a specific ticketing system format
  - Add validation / quality checks on the output
  - Generate a Markdown or HTML report in addition to JSON
"""

import logging
from datetime import datetime, timezone
from typing import Any

logger = logging.getLogger(__name__)


def format_output(result: dict[str, Any]) -> dict[str, Any]:
    """
    Wrap the AI result in a standardised output envelope.

    Args:
        result: The parsed dict returned by BacklogProcessor.process()

    Returns:
        Final output dict ready to be serialised to JSON.
    """
    # Add metadata wrapper
    output = {
        "metadata": {
            "generated_at": datetime.now(timezone.utc).isoformat(),
            "version": "1.0.0",
        },
        "summary": result.get("summary", ""),
        "requirements": result.get("requirements", []),
        "user_stories": result.get("user_stories", []),
        "duplicates_or_conflicts": result.get("duplicates_or_conflicts", []),
        "open_questions": result.get("open_questions", []),
    }

    # Preserve any debug/error fields if present
    if "_raw_response" in result:
        output["_debug"] = {
            "raw_response": result["_raw_response"],
            "parse_error": result.get("_parse_error"),
        }

    _log_quality_warnings(output)

    return output


def _log_quality_warnings(output: dict[str, Any]) -> None:
    """Log warnings if the output looks suspicious."""
    stories = output.get("user_stories", [])
    requirements = output.get("requirements", [])

    if not stories:
        logger.warning("No user stories were generated - check the input document")

    if not requirements:
        logger.warning("No requirements were extracted - check the input document")

    for story in stories:
        if not story.get("acceptance_criteria"):
            logger.warning(
                f"User story {story.get('id', '?')} has no acceptance criteria"
            )

    if output.get("open_questions"):
        logger.info(
            f"{len(output['open_questions'])} open question(s) flagged by the AI"
        )
