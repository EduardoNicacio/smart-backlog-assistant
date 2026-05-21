"""
src/formatter.py
----------------
Formats the workflow output into clean Markdown and writes it to
the ``outputs/`` directory.

Usage
-----
    from src.formatter import format_and_save

    output_path = format_and_save(result, prompt="What are the dev tasks?")
"""

import logging
import re
from datetime import datetime
from pathlib import Path

logger = logging.getLogger(__name__)

OUTPUTS_DIR = Path("outputs")

# ---------------------------------------------------------------------------
# Format and save helper
# ---------------------------------------------------------------------------

def format_and_save(result: dict, prompt: str = "") -> Path:
    """
    Format a workflow result dict as Markdown and write it to ``outputs/``.

    Parameters
    ----------
    result : dict
        Dict returned by ``BacklogProcessor.run()``.  Expected keys:
        ``steps``, ``step_outputs``, ``final_output``, ``prompt``.
    prompt : str, optional
        The original workflow prompt (used as the document title).

    Returns
    -------
    Path
        Path to the written output file.
    """
    OUTPUTS_DIR.mkdir(parents=True, exist_ok=True)

    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    filename = OUTPUTS_DIR / f"backlog_{timestamp}.md"

    md = _build_markdown(result, prompt or result.get("prompt", "Backlog generation"))

    try:
        filename.write_text(md, encoding="utf-8")
        logger.info("Output written to %s", filename)
    except Exception:
        logger.exception("Failed to write output file: %s", filename)
        raise

    return filename

# ---------------------------------------------------------------------------
# Build markdown helper
# ---------------------------------------------------------------------------

def _build_markdown(result: dict, title: str) -> str:
    """Build the full Markdown document from a result dict."""
    steps: list = result.get("steps", [])
    outputs: list = result.get("step_outputs", [])
    final: str = result.get("final_output", "")
    timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")

    lines = [
        "# Smart Backlog Assistant - Output",
        "",
        f"- **Generated**: {timestamp}",
        f"- **Prompt**: {title}",
        "- **Model**: [to be filled by the candidate]",
        "",
        "---",
        "",
    ]

    # Workflow steps summary
    if steps:
        lines += ["## Workflow Steps", ""]
        for i, step in enumerate(steps, 1):
            lines.append(f"{step}")
        lines.append("")
        lines.append("---")
        lines.append("")

    # Per-step output
    for i, (step, output) in enumerate(zip(steps, outputs), 1):
        lines += [
            f"## Step {step}: ",
            "",
            output.strip() if output else "_No output generated._",
            "",
            "---",
            "",
        ]

    # Final output highlight
    if final:
        lines += [
            "## Final Output",
            "",
            "> This is the output of the last workflow step and represents the primary deliverable.",
            "",
            final.strip(),
            "",
        ]

    return "\n".join(lines)

# ---------------------------------------------------------------------------
# Print summary helper
# ---------------------------------------------------------------------------

def print_summary(result: dict) -> None:
    """Print a concise summary of the workflow result to stdout."""
    steps = result.get("steps", [])
    outputs = result.get("step_outputs", [])
    final = result.get("final_output", "")

    print("\n" + "=" * 80)
    print("WORKFLOW SUMMARY")
    print("=" * 80)

    if steps:
        print(f"\n{len(steps)} step(s) executed:")
        for i, (step, output) in enumerate(zip(steps, outputs), 1):
            status = "[ERROR]" if output.startswith("[ERROR]") else "[OK]"
            print(f"  {i}. {status} {step}")

    if final:
        print("\n--- Final Output (truncated to 800 chars) ---")
        print(final[:800])
        if len(final) > 800:
            print("... (see output file for full content)")
    else:
        print("\n[No output was generated]")

    print("=" * 80 + "\n")
