"""
main.py
-------
Entry point for the Smart Backlog Assistant.

Usage
-----
    # OpenAI (default):
    python main.py --spec inputs/sample_requirements.txt

    # Anthropic Claude:
    AI_PROVIDER=anthropic python main.py --spec inputs/sample_requirements.txt

    # Or set AI_PROVIDER in your .env file and run normally.

    # Single-step prompts:
    python main.py --spec inputs/sample_requirements.txt \
                   --prompt "What are the user stories for this product?"

    # Include an existing backlog for context:
    python main.py --spec inputs/sample_requirements.txt \
                   --backlog inputs/sample_backlog.json

Run ``python main.py --help`` for all options.
"""

import argparse
import logging
import os
import sys

from dotenv import load_dotenv

from src.ai_client import build_client
from src.backlog_loader import format_backlog_for_context, load_backlog
from src.document_loader import load_document
from src.formatter import format_and_save, print_summary
from src.processor import BacklogProcessor

# ---------------------------------------------------------------------------
# Logging
# ---------------------------------------------------------------------------

os.makedirs("logs", exist_ok=True)

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(levelname)s - %(message)s",
    handlers=[
        logging.FileHandler("logs/agentic-workflow.log"),
        logging.StreamHandler(),
    ],
)
logger = logging.getLogger(__name__)

DEFAULT_PROMPT = "What would the development tasks for this product be?"


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="smart-backlog-assistant",
        description=(
            "Smart Backlog Assistant - AI-powered tool that converts a product "
            "specification into user stories, features, and development tasks."
        ),
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
            Examples:
            python main.py --spec inputs/sample_requirements.txt
            python main.py --spec inputs/sample_requirements.txt --provider anthropic
            python main.py --spec inputs/sample_meeting_notes.txt --prompt "What are the user stories?"
            python main.py --spec inputs/sample_requirements.txt --backlog inputs/sample_backlog.json
        """,
    )
    parser.add_argument(
        "--spec",
        required=True,
        help="Path to the product specification file (.txt or .pdf).",
    )
    parser.add_argument(
        "--prompt",
        default=DEFAULT_PROMPT,
        help=f'Workflow prompt. Default: "{DEFAULT_PROMPT}"',
    )
    parser.add_argument(
        "--provider",
        default=None,
        choices=["openai", "anthropic"],
        help=(
            "AI provider to use. Overrides the AI_PROVIDER env var. "
            "Default: openai. When using 'anthropic', set ANTHROPIC_API_KEY "
            "and OPENAI_API_KEY (for embeddings) in your .env file."
        ),
    )
    parser.add_argument(
        "--model",
        default=None,
        help=(
            "Chat model override. E.g. 'gpt-5.4-mini' for OpenAI or "
            "'claude-sonnet-4-6' for Anthropic. "
            "Overrides the OPENAI_BASE_MODEL or ANTHROPIC_BASE_MODEL env var."
        ),
    )
    parser.add_argument(
        "--backlog",
        default=None,
        help="Path to an existing backlog JSON file (optional).",
    )
    parser.add_argument(
        "--output",
        default=None,
        help="Output file path. Defaults to outputs/backlog_<timestamp>.md",
    )
    parser.add_argument(
        "--max-iterations",
        type=int,
        default=5,
        help="Max evaluation/correction loops per step (default: 5).",
    )
    return parser


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------


def main() -> int:
    load_dotenv()

    parser = build_parser()
    args = parser.parse_args()

    # --- Build AI client ---
    try:
        client = build_client(provider=args.provider, chat_model=args.model)
    except ValueError as e:
        logger.exception("AI client configuration error: %s", e)
        print(f"\nERROR: {e}\n")
        return 1

    print(f"\nProvider : {client.provider}")
    print(f"\nModel : {client.chat_model}")

    # --- Load spec ---
    try:
        product_spec = load_document(args.spec)
    except FileNotFoundError:
        logger.error("Spec file not found: %s", args.spec)
        print(f"\nERROR: Spec file not found: {args.spec}\n")
        return 1
    except ValueError as e:
        logger.exception("Unsupported spec format: %s", e)
        print(f"\nERROR: {e}\n")
        return 1

    # --- Load backlog (optional) ---
    if args.backlog:
        backlog_items = load_backlog(args.backlog)
        backlog_context = format_backlog_for_context(backlog_items)
        if backlog_context:
            product_spec = f"{product_spec}\n\n{backlog_context}"
            logger.info("Backlog context appended to product spec.")

    # --- Build processor ---
    logger.info("Initializing BacklogProcessor...")
    print("\nInitializing agents...")
    try:
        processor = BacklogProcessor(
            product_spec=product_spec,
            client=client,
            max_eval_iterations=args.max_iterations,
        )
    except Exception:
        logger.exception("Failed to initialize BacklogProcessor.")
        print("\nERROR: Failed to initialize agents. Check logs/main.log for details.\n")
        return 1

    # --- Run workflow ---
    try:
        result = processor.run(args.prompt)
    except Exception:
        logger.exception("Workflow execution failed.")
        print("\nERROR: Workflow failed. Check logs/main.log for details.\n")
        return 1

    # --- Format and save ---
    try:
        output_path = format_and_save(result, prompt=args.prompt)
        print(f"\nOutput saved to: {output_path}")
    except Exception:
        logger.exception("Failed to save output.")
        print("\nWARNING: Could not save output file.")

    print_summary(result)
    return 0


if __name__ == "__main__":
    sys.exit(main())
