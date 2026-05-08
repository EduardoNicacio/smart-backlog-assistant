"""
src/ai_client.py
================
Provider-agnostic AI client abstraction.

This is the layer you'll modify most when experimenting
with different models, parameters, or providers.

Supported providers:
  - Anthropic (Claude)  → set ANTHROPIC_API_KEY
  - OpenAI (GPT)        → set OPENAI_API_KEY

Auto-detection: if both keys are present, Anthropic is preferred.
Override with the --provider CLI flag or by passing provider= to get_ai_client().
"""

import logging
import os
from abc import ABC, abstractmethod
from typing import Optional

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Load .env file if python-dotenv is available (optional convenience)
# ---------------------------------------------------------------------------
try:
    from dotenv import load_dotenv

    load_dotenv()
    logger.debug("Loaded .env file")
except ImportError:
    pass  # dotenv is optional


# ---------------------------------------------------------------------------
# Base class - new providers can be added by subclassing this
# ---------------------------------------------------------------------------
class AIClient(ABC):
    """Abstract base class for AI provider clients."""

    @property
    @abstractmethod
    def provider_name(self) -> str:
        """Human-readable name of the provider."""
        ...

    @abstractmethod
    def complete(self, system_prompt: str, user_prompt: str) -> str:
        """
        Send a prompt to the AI and return the text response.

        Args:
            system_prompt: Instructions / persona for the model.
            user_prompt:   The actual task / content to process.

        Returns:
            The model's text response as a plain string.
        """
        ...


# ---------------------------------------------------------------------------
# Anthropic (Claude) client
# ---------------------------------------------------------------------------
class AnthropicClient(AIClient):
    """
    Thin wrapper around the Anthropic Python SDK.

    Candiate note: adjust MODEL and MAX_TOKENS to experiment.
    Claude docs: https://docs.anthropic.com
    """

    MODEL = os.getenv("ANTHROPIC_BASE_MODEL", "claude-sonnet-4-6")
    MAX_TOKENS = 4096

    def __init__(self, api_key: Optional[str] = None):
        try:
            import anthropic
        except ImportError:
            raise ImportError(
                "anthropic package not installed. Run: pip install anthropic"
            )

        api_key = api_key or os.getenv("ANTHROPIC_API_KEY")
        if not api_key:
            raise EnvironmentError("ANTHROPIC_API_KEY is not set.")

        base_url = os.getenv("ANTHROPIC_BASE_URL", "https://claude.vocareum.com")
        if not base_url:
            raise EnvironmentError("ANTHROPIC_BASE_URL is not set.")

        self._client = anthropic.Anthropic(api_key=api_key, base_url=base_url)
        logger.debug(f"AnthropicClient initialised with model={self.MODEL}")

    @property
    def provider_name(self) -> str:
        return f"Anthropic ({self.MODEL})"

    def complete(self, system_prompt: str, user_prompt: str) -> str:
        logger.debug("Sending request to Anthropic API...")
        message = self._client.messages.create(
            model=self.MODEL,
            max_tokens=self.MAX_TOKENS,
            system=system_prompt,
            messages=[{"role": "user", "content": user_prompt}],
        )
        response_text = message.content[0].text  # type: ignore
        logger.debug(f"Anthropic response received ({len(response_text)} chars)")
        return response_text


# ---------------------------------------------------------------------------
# OpenAI (GPT) client
# ---------------------------------------------------------------------------
class OpenAIClient(AIClient):
    """
    Thin wrapper around the OpenAI Python SDK.

    Candidate note: adjust MODEL and MAX_TOKENS to experiment.
    OpenAI docs: https://platform.openai.com/docs
    """

    MODEL = os.getenv("OPENAI_BASE_MODEL", "gpt-5.4-mini")
    MAX_TOKENS = 4096

    def __init__(self, api_key: Optional[str] = None):
        try:
            from openai import OpenAI
        except ImportError:
            raise ImportError("openai package not installed. Run: pip install openai")

        api_key = api_key or os.getenv("OPENAI_API_KEY")
        if not api_key:
            raise EnvironmentError("OPENAI_API_KEY is not set.")

        base_url = os.getenv("OPENAI_BASE_URL", "https://openai.vocareum.com/v1")
        if not base_url:
            raise EnvironmentError("OPENAI_BASE_URL is not set.")

        self._client = OpenAI(api_key=api_key, base_url=base_url)
        logger.debug(f"OpenAIClient initialised with model={self.MODEL}")

    @property
    def provider_name(self) -> str:
        return f"OpenAI ({self.MODEL})"

    def complete(self, system_prompt: str, user_prompt: str) -> str:
        logger.debug("Sending request to OpenAI API...")
        response = self._client.chat.completions.create(
            model=self.MODEL,
            max_tokens=self.MAX_TOKENS,
            messages=[
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": user_prompt},
            ],
        )
        response_text = response.choices[0].message.content
        logger.debug(f"OpenAI response received ({len(response_text)} chars)")  # type: ignore
        return response_text  # type: ignore


# ---------------------------------------------------------------------------
# Factory function - used by main.py
# ---------------------------------------------------------------------------
def get_ai_client(provider: Optional[str] = None) -> AIClient:
    """
    Return an initialised AI client.

    Resolution order:
      1. Explicit provider argument
      2. ANTHROPIC_API_KEY present  → AnthropicClient
      3. OPENAI_API_KEY present     → OpenAIClient
      4. Neither key found          → raise EnvironmentError
    """
    has_anthropic = bool(os.getenv("ANTHROPIC_API_KEY"))
    has_openai = bool(os.getenv("OPENAI_API_KEY"))

    if provider == "anthropic" or (provider is None and has_anthropic):
        return AnthropicClient()

    if provider == "openai" or (provider is None and has_openai):
        return OpenAIClient()

    raise EnvironmentError(
        "No AI provider API key found."
        "Set ANTHROPIC_API_KEY or OPENAI_API_KEY in your environment."
    )
