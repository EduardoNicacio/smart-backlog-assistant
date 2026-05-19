"""
tests/test_processor.py
-----------------------
Unit tests for the Smart Backlog Assistant.

Run with:
    pytest tests/ -v

These tests use a mock AIClient so they run without a real API key.
They verify:
    - Agent instantiation and basic response shaping
    - EvaluationAgent correction loop logic (including the key bug fix)
    - BacklogProcessor wiring
    - AIClient provider selection and interface
    - Document and backlog loader error handling
    - Formatter output structure
"""

import json
import sys
import unittest
from pathlib import Path
from unittest.mock import MagicMock, patch

ROOT = Path(__file__).resolve().parent.parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from agents.base_agents import (
    ActionPlanningAgent,
    EvaluationAgent,
    KnowledgeAugmentedPromptAgent,
    RoutingAgent,
)
from src.backlog_loader import format_backlog_for_context, load_backlog
from src.document_loader import load_document
from src.formatter import _build_markdown


# ---------------------------------------------------------------------------
# Shared mock AIClient factory
# ---------------------------------------------------------------------------


def _mock_client(complete_response: str = "mock response", embed_response=None):
    """Return a mock AIClient with configurable complete() and embed() return values."""
    client = MagicMock()
    client.provider = "openai"
    client.chat_model = "gpt-4o-mini"
    client.complete.return_value = complete_response
    client.embed.return_value = embed_response or [0.1] * 10
    return client


# ---------------------------------------------------------------------------
# KnowledgeAugmentedPromptAgent
# ---------------------------------------------------------------------------


class TestKnowledgeAugmentedPromptAgent(unittest.TestCase):

    def test_respond_returns_client_output(self):
        client = _mock_client("As a user, I want X so that Y.")
        agent = KnowledgeAugmentedPromptAgent(
            client=client, persona="PM", knowledge="some knowledge"
        )
        result = agent.respond("write a user story")
        self.assertEqual(result, "As a user, I want X so that Y.")
        # Verify the system prompt contains both persona and knowledge
        call_kwargs = client.complete.call_args.kwargs
        self.assertIn("PM", call_kwargs["system"])
        self.assertIn("some knowledge", call_kwargs["system"])

    def test_respond_returns_empty_string_on_exception(self):
        client = _mock_client()
        client.complete.side_effect = Exception("API down")
        agent = KnowledgeAugmentedPromptAgent(client=client, persona="p", knowledge="k")
        result = agent.respond("any input")
        self.assertEqual(result, "")


# ---------------------------------------------------------------------------
# ActionPlanningAgent
# ---------------------------------------------------------------------------


class TestActionPlanningAgent(unittest.TestCase):

    def test_extracts_steps_as_list(self):
        client = _mock_client("1. Define user stories\n2. Define features\n3. Define tasks")
        agent = ActionPlanningAgent(client=client, knowledge="k")
        steps = agent.extract_steps_from_prompt("What are the dev tasks?")
        self.assertEqual(len(steps), 3)
        self.assertIn("1. Define user stories", steps)

    def test_returns_empty_list_on_exception(self):
        client = _mock_client()
        client.complete.side_effect = Exception("fail")
        agent = ActionPlanningAgent(client=client, knowledge="k")
        self.assertEqual(agent.extract_steps_from_prompt("prompt"), [])

    def test_filters_blank_lines(self):
        client = _mock_client("\n\n1. Step one\n\n2. Step two\n")
        agent = ActionPlanningAgent(client=client, knowledge="k")
        steps = agent.extract_steps_from_prompt("p")
        self.assertEqual(len(steps), 2)

    def test_knowledge_passed_in_system_prompt(self):
        client = _mock_client("1. Step one")
        agent = ActionPlanningAgent(client=client, knowledge="my knowledge base")
        agent.extract_steps_from_prompt("prompt")
        call_kwargs = client.complete.call_args.kwargs
        self.assertIn("my knowledge base", call_kwargs["system"])


# ---------------------------------------------------------------------------
# EvaluationAgent - correction loop
# ---------------------------------------------------------------------------


class TestEvaluationAgent(unittest.TestCase):

    def _worker(self, response: str):
        w = MagicMock()
        w.respond.return_value = response
        return w

    def test_passes_on_first_yes(self):
        """When evaluator says Yes immediately, only 1 iteration is run."""
        client = _mock_client("Yes, the response meets all criteria.")
        worker = self._worker("As a user, I want X so that Y.")
        agent = EvaluationAgent(
            client=client,
            persona="eval",
            evaluation_criteria="must start with As a",
            worker_agent=worker,
            max_interactions=5,
        )
        result = agent.evaluate("write a user story")
        self.assertEqual(result["iterations"], 1)
        self.assertIn("As a user", result["final_response"])

    def test_loops_on_no_then_passes(self):
        """Evaluator says No once, then Yes - 2 iterations expected."""
        call_count = {"n": 0}

        def complete_side_effect(**kwargs):
            call_count["n"] += 1
            return "No, fix formatting." if call_count["n"] <= 2 else "Yes, correct."

        client = _mock_client()
        client.complete.side_effect = complete_side_effect

        worker = self._worker("As a user, I want X so that Y.")
        agent = EvaluationAgent(
            client=client,
            persona="eval",
            evaluation_criteria="criteria",
            worker_agent=worker,
            max_interactions=5,
        )
        result = agent.evaluate("prompt")
        self.assertGreaterEqual(result["iterations"], 2)

    def test_corrected_prompt_fed_back_not_original(self):
        """
        KEY FIX TEST: verify that after a 'No' verdict, the worker is called
        with a prompt that references the previous (bad) response - not the
        original prompt verbatim.
        """
        verdict_calls = {"n": 0}

        def complete_side_effect(**kwargs):
            verdict_calls["n"] += 1
            return "No, needs improvement." if verdict_calls["n"] == 1 else "Yes, correct."

        client = _mock_client()
        client.complete.side_effect = complete_side_effect

        worker = self._worker("bad response")
        agent = EvaluationAgent(
            client=client,
            persona="eval",
            evaluation_criteria="criteria",
            worker_agent=worker,
            max_interactions=5,
        )
        agent.evaluate("original task")

        # The worker should have been called at least twice
        self.assertGreaterEqual(worker.respond.call_count, 2)

        # The SECOND call to the worker should NOT be with the bare original prompt.
        second_call = worker.respond.call_args_list[1]
        second_call_input = second_call.kwargs.get("input_text") or second_call.args[0]

        self.assertNotEqual(second_call_input, "original task")
        self.assertIn("original task", second_call_input)   # original is embedded
        self.assertIn("bad response", second_call_input)    # previous response is embedded

    def test_uses_client_complete_not_sdk_directly(self):
        """Agents must call self.client.complete(), never an SDK directly."""
        client = _mock_client("Yes, correct.")
        worker = self._worker("a response")
        agent = EvaluationAgent(
            client=client,
            persona="eval",
            evaluation_criteria="criteria",
            worker_agent=worker,
            max_interactions=2,
        )
        agent.evaluate("task")
        # client.complete must have been called (not any raw SDK method)
        self.assertTrue(client.complete.called)


# ---------------------------------------------------------------------------
# RoutingAgent
# ---------------------------------------------------------------------------


class TestRoutingAgent(unittest.TestCase):

    def test_routes_to_highest_similarity_agent(self):
        """Agent whose description embedding is most similar to input is selected."""
        import numpy as np

        input_emb = [1.0, 0.0]
        emb_a = [0.0, 1.0]   # orthogonal - low similarity
        emb_b = [1.0, 0.0]   # parallel   - highest similarity

        call_sequence = iter([input_emb, emb_a, emb_b])
        client = _mock_client()
        client.embed.side_effect = lambda text: next(call_sequence)

        func_a = MagicMock(return_value="result-a")
        func_b = MagicMock(return_value="result-b")

        router = RoutingAgent(
            client=client,
            agents=[
                {"name": "A", "description": "agent A", "func": func_a},
                {"name": "B", "description": "agent B", "func": func_b},
            ],
        )
        result = router.route("test input")
        func_b.assert_called_once_with("test input")
        self.assertEqual(result, "result-b")

    def test_returns_error_message_when_embed_fails(self):
        client = _mock_client()
        client.embed.return_value = []  # empty = failure
        router = RoutingAgent(client=client, agents=[])
        result = router.route("test")
        self.assertIn("error", result.lower())


# ---------------------------------------------------------------------------
# AIClient
# ---------------------------------------------------------------------------


class TestAIClient(unittest.TestCase):

    def test_build_client_raises_without_key(self):
        """build_client raises ValueError when no API key is available."""
        from src.ai_client import build_client
        with patch.dict("os.environ", {}, clear=True):
            # Remove both keys from env
            env = {k: v for k, v in __import__("os").environ.items()
                   if k not in ("OPENAI_API_KEY", "ANTHROPIC_API_KEY", "AI_PROVIDER")}
            with patch.dict("os.environ", env, clear=True):
                with self.assertRaises(ValueError):
                    build_client("openai", api_key="")

    def test_build_client_openai(self):
        """build_client returns an AIClient with correct provider."""
        from src.ai_client import AIClient, build_client
        with patch("src.ai_client.AIClient._init_clients"):
            client = build_client("openai", api_key="sk-test-key")
        self.assertEqual(client.provider, "openai")

    def test_aiclient_complete_routes_to_openai(self):
        """AIClient.complete calls _openai_complete for openai provider."""
        from src.ai_client import AIClient
        client = AIClient.__new__(AIClient)
        client.provider = "openai"
        client.chat_model = "gpt-4o-mini"
        client._openai_client = MagicMock()
        mock_choice = MagicMock()
        mock_choice.message.content = "hello"
        client._openai_client.chat.completions.create.return_value = MagicMock(
            choices=[mock_choice]
        )
        result = client.complete([{"role": "user", "content": "hi"}])
        self.assertEqual(result, "hello")

    def test_aiclient_complete_routes_to_anthropic(self):
        """AIClient.complete calls _anthropic_complete for anthropic provider."""
        from src.ai_client import AIClient
        client = AIClient.__new__(AIClient)
        client.provider = "anthropic"
        client.chat_model = "claude-3-haiku-20240307"
        mock_block = MagicMock()
        mock_block.text = "world"
        client._anthropic_client = MagicMock()
        client._anthropic_client.messages.create.return_value = MagicMock(
            content=[mock_block]
        )
        result = client.complete([{"role": "user", "content": "hi"}])
        self.assertEqual(result, "world")

    def test_aiclient_embed_uses_embedding_client(self):
        """AIClient.embed calls the embedding client regardless of chat provider."""
        from src.ai_client import AIClient
        client = AIClient.__new__(AIClient)
        client._embedding_client = MagicMock()
        client._embedding_client.embeddings.create.return_value = MagicMock(
            data=[MagicMock(embedding=[0.5, 0.5])]
        )
        result = client.embed("some text")
        self.assertEqual(result, [0.5, 0.5])

    def test_aiclient_embed_returns_empty_without_embedding_client(self):
        """AIClient.embed returns [] when no embedding client is configured."""
        from src.ai_client import AIClient
        client = AIClient.__new__(AIClient)
        client._embedding_client = None
        result = client.embed("some text")
        self.assertEqual(result, [])


# ---------------------------------------------------------------------------
# Document loader
# ---------------------------------------------------------------------------


class TestDocumentLoader(unittest.TestCase):

    def test_load_txt(self):
        import tempfile
        with tempfile.NamedTemporaryFile(
            mode="w", suffix=".txt", encoding="utf-8", delete=False
        ) as f:
            f.write("Hello, spec!")
            name = f.name
        result = load_document(name)
        self.assertEqual(result, "Hello, spec!")
        Path(name).unlink()

    def test_raises_on_missing_file(self):
        with self.assertRaises(FileNotFoundError):
            load_document("nonexistent_file_xyz.txt")

    def test_raises_on_unsupported_format(self):
        import tempfile
        with tempfile.NamedTemporaryFile(suffix=".docx", delete=False) as f:
            name = f.name
        with self.assertRaises(ValueError):
            load_document(name)
        Path(name).unlink()


# ---------------------------------------------------------------------------
# Backlog loader
# ---------------------------------------------------------------------------


class TestBacklogLoader(unittest.TestCase):

    def test_load_valid_backlog(self):
        import tempfile
        data = {"items": [{"id": "S-1", "type": "user_story", "title": "A story"}]}
        with tempfile.NamedTemporaryFile(
            mode="w", suffix=".json", encoding="utf-8", delete=False
        ) as f:
            json.dump(data, f)
            name = f.name
        items = load_backlog(name)
        self.assertEqual(len(items), 1)
        self.assertEqual(items[0]["id"], "S-1")
        Path(name).unlink()

    def test_returns_empty_list_for_missing_file(self):
        self.assertEqual(load_backlog("does_not_exist.json"), [])

    def test_format_backlog_for_context(self):
        items = [{"id": "S-1", "type": "user_story", "title": "A story", "status": "done"}]
        text = format_backlog_for_context(items)
        self.assertIn("S-1", text)
        self.assertIn("A story", text)

    def test_format_empty_backlog_returns_empty_string(self):
        self.assertEqual(format_backlog_for_context([]), "")


# ---------------------------------------------------------------------------
# Formatter
# ---------------------------------------------------------------------------


class TestFormatter(unittest.TestCase):

    def test_build_markdown_contains_steps(self):
        result = {
            "steps": ["Step one", "Step two"],
            "step_outputs": ["Output one", "Output two"],
            "final_output": "Output two",
            "prompt": "test prompt",
        }
        md = _build_markdown(result, "test prompt")
        self.assertIn("Step one", md)
        self.assertIn("Step two", md)
        self.assertIn("Output one", md)
        self.assertIn("Final Output", md)

    def test_build_markdown_handles_empty_result(self):
        result = {"steps": [], "step_outputs": [], "final_output": "", "prompt": ""}
        md = _build_markdown(result, "empty")
        self.assertIn("Smart Backlog Assistant", md)


# ---------------------------------------------------------------------------
# BacklogProcessor integration (mocked)
# ---------------------------------------------------------------------------


class TestBacklogProcessorIntegration(unittest.TestCase):

    def test_run_returns_expected_keys(self):
        """
        Smoke-test: BacklogProcessor.run() returns a dict with the required keys.
        All LLM + embedding calls are mocked.
        """
        import random

        call_count = {"n": 0}

        def complete_side_effect(**kwargs):
            call_count["n"] += 1
            if call_count["n"] == 1:
                return "1. Define user stories"
            return "Yes, correct.\nAs a user, I want X so that Y."

        def embed_side_effect(text):
            return [random.uniform(-1, 1) for _ in range(10)]

        client = _mock_client()
        client.complete.side_effect = complete_side_effect
        client.embed.side_effect = embed_side_effect

        from src.processor import BacklogProcessor
        processor = BacklogProcessor(
            product_spec="A simple spec.",
            client=client,
            max_eval_iterations=2,
        )
        result = processor.run("What are the dev tasks?")

        self.assertIn("steps", result)
        self.assertIn("step_outputs", result)
        self.assertIn("final_output", result)
        self.assertIn("prompt", result)
        self.assertEqual(result["prompt"], "What are the dev tasks?")

    def test_processor_logs_provider_and_model(self):
        """BacklogProcessor should log the active provider and model."""
        client = _mock_client("1. Define user stories")

        with self.assertLogs("src.processor", level="INFO") as log:
            from src.processor import BacklogProcessor
            BacklogProcessor(product_spec="spec", client=client, max_eval_iterations=1)

        combined = "\n".join(log.output)
        self.assertIn("openai", combined.lower())


# ---------------------------------------------------------------------------
# Run
# ---------------------------------------------------------------------------

if __name__ == "__main__":
    unittest.main()
