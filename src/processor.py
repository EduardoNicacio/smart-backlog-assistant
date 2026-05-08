"""
src/processor.py
================
Core logic: sends documents to the AI and parses structured responses.

This is where PROMPT ENGINEERING lives - the most important file
for candidates to study, modify, and improve.

Candidate note: experiment with:
  - System prompt tone and persona
  - Output format instructions (JSON schema, examples)
  - How existing backlog context is injected
  - Breaking the task into multiple smaller prompts (chain-of-thought)
"""

import json
import logging
import re
from typing import Any

from src.ai_client import AIClient

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Prompts - separated from logic so candidates can iterate quickly
# ---------------------------------------------------------------------------

SYSTEM_PROMPT = """You are an experienced agile delivery lead and software architect.
Your job is to analyse meeting notes or requirement documents and produce
structured, actionable engineering backlog items.

You produce clear, developer-friendly outputs that are:
- Specific and testable
- Sized appropriately (not too broad, not too granular)
- Written in plain language a developer can act on immediately

You always respond with valid JSON only - no markdown fences, no prose outside the JSON.
"""

USER_PROMPT_TEMPLATE = """Analyse the following document and produce structured backlog output.

## Input Document
{document_text}

{backlog_context}

## Required Output Format (JSON)
Return a JSON object with exactly these keys:

{{
  "summary": "2-3 sentence summary of the key themes in the document",
  "requirements": [
    {{
      "id": "REQ-001",
      "description": "Clear description of the requirement",
      "source": "Direct quote or paraphrase from the document"
    }}
  ],
  "user_stories": [
    {{
      "id": "US-001",
      "title": "Short title (5-8 words)",
      "as_a": "type of user",
      "i_want": "goal or action",
      "so_that": "business value or outcome",
      "acceptance_criteria": [
        "Given <context>, When <action>, Then <outcome>",
        "..."
      ],
      "priority": "High | Medium | Low",
      "category": "Feature | Bug | Tech Debt | Spike | Improvement",
      "estimated_complexity": "XS | S | M | L | XL",
      "notes": "Optional implementation notes or open questions"
    }}
  ],
  "duplicates_or_conflicts": [
    {{
      "description": "Description of any overlap with existing backlog items",
      "existing_item_id": "ID from existing backlog if applicable"
    }}
  ],
  "open_questions": [
    "Any ambiguities or missing information that should be clarified"
  ]
}}

Guidelines:
- Generate between 3 and 8 user stories depending on document complexity
- Acceptance criteria should be concrete and testable (Given/When/Then format)
- Priority should reflect business value and urgency
- Flag any requirements that overlap with existing backlog items
- Note anything that is unclear or needs stakeholder clarification
"""

BACKLOG_CONTEXT_TEMPLATE = """## Existing Backlog ({count} items)
Review these existing items to avoid duplication and identify conflicts:

{items}
"""


class BacklogProcessor:
    """
    Orchestrates the document → backlog pipeline.

    Candidate note: this is a good place to add:
      - Multi-step processing (extract requirements first, then generate stories)
      - Validation of AI output
      - Retry logic for malformed responses
      - Chunking for large documents
    """

    def __init__(self, ai_client: AIClient):
        self.ai_client = ai_client

    def process(
        self,
        document_text: str,
        existing_backlog: list[dict[str, Any]] | None = None,
    ) -> dict[str, Any]:
        """
        Process a document and return structured backlog data.

        Args:
            document_text:    Raw text content of the input document.
            existing_backlog: List of existing backlog item dicts (optional).

        Returns:
            Parsed dict matching the output schema defined in USER_PROMPT_TEMPLATE.
        """
        existing_backlog = existing_backlog or []

        # Build context block for existing backlog items
        backlog_context = self._build_backlog_context(existing_backlog)

        # Construct the full user prompt
        user_prompt = USER_PROMPT_TEMPLATE.format(
            document_text=document_text.strip(),
            backlog_context=backlog_context,
        )

        logger.debug("System prompt length: %d chars", len(SYSTEM_PROMPT))
        logger.debug("User prompt length: %d chars", len(user_prompt))

        # Call the AI
        raw_response = self.ai_client.complete(
            system_prompt=SYSTEM_PROMPT,
            user_prompt=user_prompt,
        )

        logger.debug(
            "Raw AI response:\n%s",
            raw_response[:500] + "..." if len(raw_response) > 500 else raw_response,
        )

        # Parse and validate the response
        result = self._parse_response(raw_response)

        logger.info(
            "Processed successfully: %d requirements, %d user stories",
            len(result.get("requirements", [])),
            len(result.get("user_stories", [])),
        )

        return result

    # ------------------------------------------------------------------
    # Private helpers
    # ------------------------------------------------------------------

    def _build_backlog_context(self, existing_backlog: list[dict]) -> str:
        """Format existing backlog items for injection into the prompt."""
        if not existing_backlog:
            return ""

        # Summarise each item compactly to avoid bloating the prompt
        items_text = "\n".join(
            f"- [{item.get('id', '?')}] {item.get('title', item.get('summary', str(item)))}"
            for item in existing_backlog[:20]  # cap at 20 to stay within context limits
        )

        return BACKLOG_CONTEXT_TEMPLATE.format(
            count=len(existing_backlog),
            items=items_text,
        )

    def _parse_response(self, raw_response: str) -> dict[str, Any]:
        """
        Parse the AI's JSON response, with graceful fallback.

        Candidate note: this is a common challenge - AI models don't always
        return perfectly valid JSON. Consider improving this parser or
        adding a retry prompt.
        """
        # Strip markdown code fences if the model added them despite instructions
        cleaned = raw_response.strip()
        cleaned = re.sub(r"^```(?:json)?\s*", "", cleaned)
        cleaned = re.sub(r"\s*```$", "", cleaned)

        try:
            result = json.loads(cleaned)
            logger.debug("JSON parsed successfully")
            return result
        except json.JSONDecodeError as e:
            logger.warning(f"Failed to parse AI response as JSON: {e}")
            logger.debug(f"Problematic response: {cleaned[:300]}")

            # Fallback: return a minimal valid structure with the raw text
            # Candidates: replace this with a retry prompt to the AI
            return {
                "summary": "Could not parse structured response.",
                "requirements": [],
                "user_stories": [],
                "duplicates_or_conflicts": [],
                "open_questions": ["AI response could not be parsed. See raw output."],
                "_raw_response": raw_response,
                "_parse_error": str(e),
            }
