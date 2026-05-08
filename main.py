"""
Smart Backlog Assistant - Main Entry Point
==========================================
Run this to process meeting notes or requirement documents
and generate structured backlog items.

Usage:
    python main.py --input inputs/sample_meeting_notes.txt
    python main.py --input inputs/sample_requirements.pdf --backlog inputs/sample_backlog.json
    python main.py --help
"""

import argparse
import json
import logging
import os
import sys
from pathlib import Path

from src.document_loader import load_document
from src.backlog_loader import load_backlog
from src.ai_client import get_ai_client
from src.processor import BacklogProcessor
from src.formatter import format_output

# ---------------------------------------------------------------------------
# Logging setup - adjust level via --verbose flag
# ---------------------------------------------------------------------------
# Ensure logs directory exists
os.makedirs("logs", exist_ok=True)

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - [%(levelname)s] - %(message)s",
    datefmt="%H:%M:%S",
    handlers=[
        logging.FileHandler("logs/smart-backlog-assistant.log"),
        logging.StreamHandler(),
    ],
)
logger = logging.getLogger(__name__)


def parse_args():
    parser = argparse.ArgumentParser(
        description="Smart Backlog Assistant: turn meeting notes into structured backlog items."
    )
    parser.add_argument(
        "--input",
        "-i",
        required=True,
        help="Path to meeting notes (.txt) or requirements document (.pdf)",
    )
    parser.add_argument(
        "--backlog",
        "-b",
        default=None,
        help="(Optional) Path to existing backlog JSON file for context",
    )
    parser.add_argument(
        "--output",
        "-o",
        default=None,
        help="(Optional) Path to write output JSON. Defaults to outputs/result.json",
    )
    parser.add_argument(
        "--provider",
        choices=["anthropic", "openai"],
        default=None,
        help="AI provider to use. Auto-detected from environment if not set.",
    )
    parser.add_argument(
        "--verbose",
        "-v",
        action="store_true",
        help="Enable debug logging",
    )
    return parser.parse_args()


def main():
    args = parse_args()

    if args.verbose:
        logging.getLogger().setLevel(logging.DEBUG)

    # ------------------------------------------------------------------
    # 1. Load input document
    # ------------------------------------------------------------------
    logger.info(f"Loading input document: {args.input}")
    try:
        document_text = load_document(args.input)
        logger.debug(f"Document loaded ({len(document_text)} chars)")
    except FileNotFoundError:
        logger.error(f"Input file not found: {args.input}")
        sys.exit(1)
    except ValueError as e:
        logger.error(f"Unsupported file format: {e}")
        sys.exit(1)

    # ------------------------------------------------------------------
    # 2. Load existing backlog (optional)
    # ------------------------------------------------------------------
    existing_backlog = []
    if args.backlog:
        logger.info(f"Loading existing backlog: {args.backlog}")
        try:
            existing_backlog = load_backlog(args.backlog)
            logger.info(f"Found {len(existing_backlog)} existing backlog items")
        except Exception as e:
            logger.warning(f"Could not load backlog file: {e}. Continuing without it.")

    # ------------------------------------------------------------------
    # 3. Initialise AI client (provider auto-detected or specified)
    # ------------------------------------------------------------------
    logger.info("Initialising AI client...")
    try:
        ai_client = get_ai_client(provider=args.provider)
        logger.info(f"Using provider: {ai_client.provider_name}")
    except EnvironmentError as e:
        logger.error(str(e))
        logger.error(
            "Set ANTHROPIC_API_KEY or OPENAI_API_KEY in your environment, "
            "or copy .env.example to .env and fill in your key."
        )
        sys.exit(1)

    # ------------------------------------------------------------------
    # 4. Process document → structured backlog items
    # ------------------------------------------------------------------
    logger.info("Processing document with AI...")
    processor = BacklogProcessor(ai_client)

    try:
        result = processor.process(
            document_text=document_text,
            existing_backlog=existing_backlog,
        )
    except Exception as e:
        logger.error(f"Processing failed: {e}")
        if args.verbose:
            raise
        sys.exit(1)

    # ------------------------------------------------------------------
    # 5. Format and save output
    # ------------------------------------------------------------------
    output_path = args.output or "outputs/result.json"
    Path(output_path).parent.mkdir(parents=True, exist_ok=True)

    formatted = format_output(result)

    with open(output_path, "w") as f:
        json.dump(formatted, f, indent=2)

    logger.info(f"Output written to: {output_path}")

    # Print a human-readable summary to stdout
    print("\n" + "=" * 60)
    print("SMART BACKLOG ASSISTANT - RESULTS")
    print("=" * 60)
    print(f"\nKey Requirements Identified: {len(result.get('requirements', []))}")
    print(f"User Stories Generated:       {len(result.get('user_stories', []))}")
    print(f"\n--- Summary ---\n{result.get('summary', 'N/A')}")
    print(f"\nFull output saved to: {output_path}")
    print("=" * 60 + "\n")


if __name__ == "__main__":
    main()
