"""
src/ai_client.py
----------------
Unified AI provider abstraction for the Smart Backlog Assistant.

All agent classes in ``agents/base_agents.py`` call through this interface -
they never import an SDK directly.  Switching providers requires only a change
to the ``AI_PROVIDER`` environment variable (and the corresponding API key).

Supported providers
-------------------
  openai     - standard OpenAI endpoint, or Vocareum proxy (key starts with "voc")
  anthropic  - Anthropic Claude via the ``anthropic`` SDK

Unified interface
-----------------
Both providers are wrapped in ``AIClient``, which exposes two methods:

    complete(messages, system=None) -> str
        Send a list of {"role": ..., "content": ...} messages and return the
        model's text reply.  An optional ``system`` string is prepended as a
        system prompt (handled natively by both APIs).

    embed(text) -> list[float]
        Return a dense embedding vector for ``text``.
        NOTE: Anthropic does not provide a first-party embedding endpoint.
        When provider is "anthropic", embeddings fall back to OpenAI's
        text-embedding-3-large model. Set OPENAI_API_KEY alongside
        ANTHROPIC_API_KEY to enable this.

Factory
-------
    from src.ai_client import AIClient, build_client

    client = build_client()          # reads AI_PROVIDER + API keys from env
    client = build_client("openai")  # explicit provider
"""

import logging
import os
from typing import Optional
from dotenv import load_dotenv

# ---------------------------------------------------------------------------
# Logging setup
# ---------------------------------------------------------------------------

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Model constants
# ---------------------------------------------------------------------------

load_dotenv()

OPENAI_API_KEY = os.getenv("OPENAI_API_KEY")
OPENAI_BASE_URL = os.getenv("OPENAI_BASE_URL")
OPENAI_BASE_MODEL = os.getenv("OPENAI_BASE_MODEL")
OPENAI_EMBEDDING_MODEL = os.getenv("OPENAI_EMBEDDING_MODEL")

ANTHROPIC_API_KEY = os.getenv("ANTHROPIC_API_KEY")
ANTHROPIC_BASE_URL = os.getenv("ANTHROPIC_BASE_URL")
ANTHROPIC_BASE_MODEL = os.getenv("ANTHROPIC_BASE_MODEL")

# ---------------------------------------------------------------------------
# AIClient
# ---------------------------------------------------------------------------

class AIClient:
    """
    Provider-agnostic AI client.

    Parameters
    ----------
    provider : str
        "openai" or "anthropic".
    api_key : str
        Primary API key for the chosen provider.
    embedding_api_key : str, optional
        OpenAI key used for embeddings when provider is "anthropic".
        Falls back to ``api_key`` if not supplied (only works if that key is
        an OpenAI key).
    chat_model : str, optional
        Override the default chat model for the provider.
    """

    def __init__(
        self,
        provider: str,
        api_key: str,
        embedding_api_key: Optional[str] = None,
        chat_model: Optional[str] = None,
    ):
        self.provider = provider.lower()
        self.api_key = api_key
        self.chat_model = chat_model or (
            OPENAI_BASE_MODEL if self.provider == "openai" else ANTHROPIC_BASE_MODEL
        )

        # Embeddings always go through OpenAI (Anthropic has no embedding API)
        self._embedding_api_key = embedding_api_key or (
            api_key if self.provider == "openai" else os.getenv("OPENAI_API_KEY", "")
        )

        self._openai_client = None
        self._anthropic_client = None
        self._embedding_client = None

        self._init_clients()

    # -----------------------------------------------------------------------
    # Client initialisation
    # -----------------------------------------------------------------------

    def _init_clients(self):
        if self.provider == "openai":
            self._openai_client = self._make_openai_client(self.api_key)
            self._embedding_client = self._openai_client

        elif self.provider == "anthropic":
            try:
                import anthropic as _anthropic
                base_url = ANTHROPIC_BASE_URL if self.api_key.lower().startswith("voc") else None
                self._anthropic_client = _anthropic.Anthropic(api_key=self.api_key, base_url=base_url)
            except ImportError as exc:
                raise ImportError(
                    "The 'anthropic' package is required for Anthropic support. "
                    "Install it with: pip install anthropic"
                ) from exc

            # Embeddings fall back to OpenAI - warn if no key available
            if self._embedding_api_key:
                self._embedding_client = self._make_openai_client(
                    self._embedding_api_key
                )
            else:
                logger.warning(
                    "No OPENAI_API_KEY found for embeddings while using Anthropic provider. "
                    "Routing (which requires embeddings) will not work."
                )
        else:
            raise ValueError(
                f"Unknown provider '{self.provider}'. Choose 'openai' or 'anthropic'."
            )

    @staticmethod
    def _make_openai_client(api_key: str):
        from openai import OpenAI

        base_url = OPENAI_BASE_URL if api_key.lower().startswith("voc") else None
        return OpenAI(api_key=api_key, base_url=base_url)

    # -----------------------------------------------------------------------
    # Public interface
    # -----------------------------------------------------------------------

    def complete(self, messages: list, system: Optional[str] = None) -> str:
        """
        Send *messages* to the chat model and return the reply text.

        Parameters
        ----------
        messages : list[dict]
            List of {"role": "user"|"assistant", "content": str} dicts.
            Do not include system messages here - pass them via ``system``
            for cross-provider compatibility.
        system : str, optional
            System prompt.  Prepended for OpenAI; passed as the top-level
            ``system`` parameter for Anthropic.
        """
        try:
            if self.provider == "openai":
                return self._openai_complete(messages, system)
            else:
                return self._anthropic_complete(messages, system)
        except Exception:
            logger.exception("AIClient.complete failed (provider=%s).", self.provider)
            return ""

    def embed(self, text: str) -> list:
        """
        Return a dense embedding vector for *text*.

        Always uses the OpenAI embedding endpoint regardless of the chat
        provider (Anthropic has no first-party embedding API).
        """
        if self._embedding_client is None:
            logger.error(
                "No embedding client available. "
                "Set OPENAI_API_KEY to enable embeddings when using the Anthropic provider."
            )
            return []
        try:
            response = self._embedding_client.embeddings.create(
                model=str(OPENAI_EMBEDDING_MODEL),
                input=text,
                encoding_format="float",
            )
            return response.data[0].embedding
        except Exception:
            logger.exception("AIClient.embed failed.")
            return []

    # -----------------------------------------------------------------------
    # Provider-specific completion implementations
    # -----------------------------------------------------------------------

    def _openai_complete(self, messages: list, system: Optional[str]) -> str:
        full_messages = []
        if system:
            full_messages.append({"role": "system", "content": system})
        full_messages.extend(messages)

        response = self._openai_client.chat.completions.create(  # type: ignore
            model=str(self.chat_model),
            messages=full_messages,
            temperature=0,
        )
        return response.choices[0].message.content or ""

    def _anthropic_complete(self, messages: list, system: Optional[str]) -> str:
        # Anthropic's API takes system as a top-level param, not a message role
        kwargs = dict(
            model=self.chat_model,
            max_tokens=16384,
            messages=messages,
        )
        if system:
            kwargs["system"] = system

        response = self._anthropic_client.messages.create(**kwargs)  # type: ignore
        # response.content is a list of ContentBlock objects
        return "".join(
            block.text for block in response.content if hasattr(block, "text")
        )

# ---------------------------------------------------------------------------
# Factory
# ---------------------------------------------------------------------------

def build_client(
    provider: Optional[str] = None,
    api_key: Optional[str] = None,
    embedding_api_key: Optional[str] = None,
    chat_model: Optional[str] = None,
) -> AIClient:
    """
    Build and return an ``AIClient`` from environment variables.

    Environment variables
    ---------------------
    AI_PROVIDER       : "openai" (default) or "anthropic"
    OPENAI_API_KEY    : required when provider is "openai", or for embeddings
    ANTHROPIC_API_KEY : required when provider is "anthropic"
    AI_CHAT_MODEL     : optional model name override

    Parameters
    ----------
    provider : str, optional
        Override ``AI_PROVIDER`` env var.
    api_key : str, optional
        Override the primary API key.
    embedding_api_key : str, optional
        OpenAI key for embeddings (only needed when provider is "anthropic").
    chat_model : str, optional
        Override ``AI_CHAT_MODEL`` env var.
    """
    resolved_provider = (provider or os.getenv("AI_PROVIDER", "openai")).lower()

    if resolved_provider == "openai":
        resolved_key = api_key or os.getenv("OPENAI_API_KEY", "")
        if not resolved_key:
            raise ValueError("OPENAI_API_KEY is not set. Add it to your .env file.")

        resolved_model = chat_model or os.getenv("OPENAI_BASE_MODEL", "gpt-5.4-mini")
        if not resolved_model:
            raise ValueError("OPENAI_BASE_MODEL is not set. Add it to your .env file.")

    elif resolved_provider == "anthropic":
        resolved_key = api_key or os.getenv("ANTHROPIC_API_KEY", "")
        if not resolved_key:
            raise ValueError("ANTHROPIC_API_KEY is not set. Add it to your .env file.")

        resolved_model = chat_model or os.getenv(
            "ANTHROPIC_BASE_MODEL", "claude-sonnet-4-6"
        )
        if not resolved_model:
            raise ValueError(
                "ANTHROPIC_BASE_MODEL is not set. Add it to your .env file."
            )

    else:
        raise ValueError(
            f"Unknown AI_PROVIDER '{resolved_provider}'. Choose 'openai' or 'anthropic'."
        )

    resolved_emb_key = embedding_api_key or os.getenv("OPENAI_API_KEY", "")
    if not resolved_emb_key:
        raise ValueError("OPENAI_API_KEY is required for embeddings. Add it to your .env file.")

    logger.info(
        "Building AIClient - provider=%s, model=%s",
        resolved_provider,
        resolved_model or "(default)",
    )

    return AIClient(
        provider=resolved_provider,
        api_key=resolved_key,
        embedding_api_key=resolved_emb_key,
        chat_model=resolved_model,
    )
