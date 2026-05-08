"""
tests/test_processor.py
=======================
Unit tests for the BacklogProcessor.

Candidate note: expand these tests and add your own.
Run with: pytest tests/

These tests use a MockAIClient so they run without a real API key.
"""

import json
import pytest
from unittest.mock import MagicMock

from src.processor import BacklogProcessor
from src.ai_client import AIClient
from src.formatter import format_output

# ---------------------------------------------------------------------------
# Mock AI client - returns predictable responses without hitting the API
# ---------------------------------------------------------------------------


class MockAIClient(AIClient):
    """Fake AI client for testing. Returns canned responses."""

    def __init__(self, response: str):
        self._response = response

    @property
    def provider_name(self) -> str:
        return "Mock"

    def complete(self, system_prompt: str, user_prompt: str) -> str:
        return self._response


VALID_MOCK_RESPONSE = json.dumps(
    {
        "summary": "The document describes requirements for a new customer portal.",
        "requirements": [
            {
                "id": "REQ-001",
                "description": "Support SSO via Google and Microsoft",
                "source": "Marcus wants SSO via Google and Microsoft",
            }
        ],
        "user_stories": [
            {
                "id": "US-001",
                "title": "Enterprise user logs in via SSO",
                "as_a": "enterprise customer",
                "i_want": "to log in using my company's Google or Microsoft account",
                "so_that": "I don't need to manage a separate password",
                "acceptance_criteria": [
                    "Given I am on the login page, When I click 'Sign in with Google', Then I am redirected to Google OAuth",
                    "Given I complete Google auth, When redirected back, Then I am logged in and see my dashboard",
                ],
                "priority": "High",
                "category": "Feature",
                "estimated_complexity": "M",
                "notes": "Requires SAML or OAuth spike first",
            }
        ],
        "duplicates_or_conflicts": [],
        "open_questions": ["Does this apply to all users or enterprise tier only?"],
    }
)


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------


class TestBacklogProcessor:

    def test_process_returns_expected_keys(self):
        """Output must always contain the required top-level keys."""
        client = MockAIClient(VALID_MOCK_RESPONSE)
        processor = BacklogProcessor(client)

        result = processor.process(document_text="Some meeting notes here.")

        assert "summary" in result
        assert "requirements" in result
        assert "user_stories" in result
        assert "duplicates_or_conflicts" in result
        assert "open_questions" in result

    def test_process_parses_user_stories(self):
        """User stories should be correctly parsed from AI response."""
        client = MockAIClient(VALID_MOCK_RESPONSE)
        processor = BacklogProcessor(client)

        result = processor.process(document_text="Meeting notes about SSO.")

        assert len(result["user_stories"]) == 1
        story = result["user_stories"][0]
        assert story["id"] == "US-001"
        assert story["priority"] == "High"
        assert len(story["acceptance_criteria"]) == 2

    def test_handles_malformed_json_gracefully(self):
        """Should not crash when AI returns non-JSON; falls back gracefully."""
        client = MockAIClient("Sorry, I cannot process this right now.")
        processor = BacklogProcessor(client)

        result = processor.process(document_text="Some text.")

        # Should return a fallback structure, not raise an exception
        assert "summary" in result
        assert "_raw_response" in result or "open_questions" in result

    def test_strips_markdown_fences_from_response(self):
        """Should handle AI responses wrapped in ```json ... ``` fences."""
        fenced_response = f"```json\n{VALID_MOCK_RESPONSE}\n```"
        client = MockAIClient(fenced_response)
        processor = BacklogProcessor(client)

        result = processor.process(document_text="Notes.")

        assert len(result["user_stories"]) == 1  # parsed correctly despite fences

    def test_process_with_existing_backlog(self):
        """Existing backlog items should not cause errors."""
        client = MockAIClient(VALID_MOCK_RESPONSE)
        processor = BacklogProcessor(client)

        existing = [{"id": "US-001", "title": "Existing feature", "status": "Done"}]

        result = processor.process(
            document_text="Meeting notes.",
            existing_backlog=existing,
        )

        assert result is not None

    def test_empty_document_still_processes(self):
        """An empty document should not crash the processor."""
        client = MockAIClient(VALID_MOCK_RESPONSE)
        processor = BacklogProcessor(client)

        result = processor.process(document_text="")
        assert result is not None


class TestFormatter:

    def test_format_output_adds_metadata(self):
        """Formatted output should include a metadata block."""
        raw = json.loads(VALID_MOCK_RESPONSE)
        output = format_output(raw)

        assert "metadata" in output
        assert "generated_at" in output["metadata"]

    def test_format_output_preserves_stories(self):
        """User stories should pass through the formatter unchanged."""
        raw = json.loads(VALID_MOCK_RESPONSE)
        output = format_output(raw)

        assert output["user_stories"] == raw["user_stories"]

    def test_format_handles_missing_keys(self):
        """Formatter should handle partial AI output without crashing."""
        partial = {"summary": "Partial output only."}
        output = format_output(partial)

        assert output["user_stories"] == []
        assert output["requirements"] == []
