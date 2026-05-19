"""
agents/base_agents.py
---------------------
Agent class library for the Smart Backlog Assistant.

Provides six agent classes:
    - DirectPromptAgent            : Bare prompt → response (no persona, no knowledge).
    - AugmentedPromptAgent         : Adds a persona system message.
    - KnowledgeAugmentedPromptAgent: Adds persona + a constrained knowledge base.
    - EvaluationAgent              : Wraps a worker agent with an iterative
                                     evaluate-and-correct loop.
    - RoutingAgent                 : Selects the best agent via embedding cosine
                                     similarity and delegates to it.
    - ActionPlanningAgent          : Extracts ordered steps from a user prompt.
    - RAGKnowledgePromptAgent      : RAG-based agent for large knowledge corpora.

All classes accept an ``AIClient`` instance (from ``src.ai_client``) instead
of a raw API key.  This decouples the agents from any specific SDK - switching
between OpenAI and Anthropic requires no changes here.
"""

import csv
import logging
import os
import re
import uuid
from datetime import datetime
from typing import Optional

import numpy as np
import pandas as pd

# ---------------------------------------------------------------------------
# Logging
# ---------------------------------------------------------------------------

os.makedirs("logs", exist_ok=True)

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - [%(levelname)s] - %(message)s",
    handlers=[
        logging.FileHandler("logs/agentic-workflow.log"),
        logging.StreamHandler(),
    ],
)
logger = logging.getLogger(__name__)

NO_RELEVANT_KNOWLEDGE_FOUND = "No relevant knowledge found."

# ---------------------------------------------------------------------------
# DirectPromptAgent
# ---------------------------------------------------------------------------

class DirectPromptAgent:
    """Sends a prompt directly to the model with no additional context."""

    def __init__(self, client):
        """
        Parameters
        ----------
        client : AIClient
            Configured AI client from ``src.ai_client``.
        """
        self.client = client

    def respond(self, prompt: str) -> str:
        try:
            return self.client.complete(
                messages=[{"role": "user", "content": prompt}]
            ).strip()
        except Exception:
            logger.exception("DirectPromptAgent.respond failed.")
            return ""

# ---------------------------------------------------------------------------
# AugmentedPromptAgent
# ---------------------------------------------------------------------------

class AugmentedPromptAgent:
    """Prepends a persona system message before forwarding the user prompt."""

    def __init__(self, client, persona: str):
        self.client = client
        self.persona = persona

    def respond(self, input_text: str) -> str:
        try:
            return self.client.complete(
                messages=[{"role": "user", "content": input_text}],
                system=f"Forget all previous context. {self.persona}",
            ).strip()
        except Exception:
            logger.exception("AugmentedPromptAgent.respond failed.")
            return ""

# ---------------------------------------------------------------------------
# KnowledgeAugmentedPromptAgent
# ---------------------------------------------------------------------------

class KnowledgeAugmentedPromptAgent:
    """Restricts responses to a supplied knowledge base in addition to a persona."""

    def __init__(self, client, persona: str, knowledge: str):
        self.client = client
        self.persona = persona
        self.knowledge = knowledge

    def respond(self, input_text: str) -> str:
        system = (
            f"{self.persona}. Forget all previous context.\n\n"
            "Use only the following knowledge to answer; "
            f"do not use your own knowledge:\n{self.knowledge}\n\n"
            "Answer the prompt based on this knowledge, not your own."
        )
        try:
            return self.client.complete(
                messages=[{"role": "user", "content": input_text}],
                system=system,
            )
        except Exception:
            logger.exception("KnowledgeAugmentedPromptAgent.respond failed.")
            return ""

# ---------------------------------------------------------------------------
# RAGKnowledgePromptAgent
# ---------------------------------------------------------------------------

class RAGKnowledgePromptAgent:
    """
    Uses Retrieval-Augmented Generation (RAG) to answer prompts from a large
    knowledge corpus.  The corpus is chunked, embedded once (via
    ``build_knowledge``), then the most similar chunk is retrieved at query time.
    """

    def __init__(
        self,
        client,
        persona: str,
        chunk_size: int = 2000,
        chunk_overlap: int = 500,
    ):
        self.client = client
        self.persona = persona
        self.chunk_size = chunk_size
        self.chunk_overlap = chunk_overlap
        self.unique_filename = (
            f"{datetime.now().strftime('%Y%m%d_%H%M%S')}_{uuid.uuid4().hex[:8]}.csv"
        )

    def get_embedding(self, text: str):
        emb = self.client.embed(text)
        return emb if emb else None

    def calculate_similarity(self, v1, v2) -> float:
        try:
            a, b = np.array(v1), np.array(v2)
            na, nb = np.linalg.norm(a), np.linalg.norm(b)
            if na == 0 or nb == 0:
                return 0.0
            return float(np.dot(a, b) / (na * nb))
        except Exception:
            logger.exception("Similarity calculation failed.")
            return 0.0

    def chunk_text(self, text: str) -> list:
        text = re.sub(r"\s+", " ", text).strip()
        if len(text) <= self.chunk_size:
            return [{"chunk_id": 0, "text": text, "chunk_size": len(text)}]

        chunks, start, chunk_id = [], 0, 0
        sep = "\n"

        while start < len(text) - self.chunk_size:
            end = min(start + self.chunk_size, len(text))
            if sep in text[start:end]:
                end = start + text[start:end].rindex(sep) + len(sep)
            chunks.append(
                {
                    "chunk_id": chunk_id,
                    "text": text[start:end],
                    "chunk_size": end - start,
                    "start_char": start,
                    "end_char": end,
                }
            )
            start = end - self.chunk_overlap
            chunk_id += 1

        try:
            with open(
                f"chunks-{self.unique_filename}", "w", newline="", encoding="utf-8"
            ) as f:
                writer = csv.DictWriter(f, fieldnames=["text", "chunk_size"])
                writer.writeheader()
                for c in chunks:
                    writer.writerow({k: c[k] for k in ["text", "chunk_size"]})
        except Exception:
            logger.exception("Failed to write chunks CSV.")

        return chunks

    def calculate_embeddings(self) -> pd.DataFrame:
        try:
            df = pd.read_csv(f"chunks-{self.unique_filename}", encoding="utf-8")
        except Exception:
            logger.exception("Failed to read chunks CSV.")
            return pd.DataFrame(columns=["text", "chunk_size", "embeddings"])

        df["embeddings"] = df["text"].apply(lambda t: self.get_embedding(t))
        df = df.dropna(subset=["embeddings"])

        try:
            df.to_csv(
                f"embeddings-{self.unique_filename}", encoding="utf-8", index=False
            )
        except Exception:
            logger.exception("Failed to write embeddings CSV.")

        return df

    def find_prompt_in_knowledge(self, prompt: str) -> str:
        prompt_emb = self.get_embedding(prompt)
        if prompt_emb is None:
            return NO_RELEVANT_KNOWLEDGE_FOUND

        try:
            df = pd.read_csv(f"embeddings-{self.unique_filename}", encoding="utf-8")
        except Exception:
            logger.exception("Failed to read embeddings CSV.")
            return NO_RELEVANT_KNOWLEDGE_FOUND

        def parse_emb(x):
            try:
                result = np.array(eval(x))
                return result if result is not None else np.array([])
            except Exception:
                return np.array([])

        df["embeddings"] = df["embeddings"].apply(parse_emb) # type: ignore
        df = df[df["embeddings"].apply(lambda e: len(e) > 0)]
        if df.empty:
            return NO_RELEVANT_KNOWLEDGE_FOUND

        df["similarity"] = df["embeddings"].apply(
            lambda emb: self.calculate_similarity(prompt_emb, emb)
        )
        best_chunk = df.loc[df["similarity"].idxmax(), "text"]

        try:
            return self.client.complete(
                messages=[
                    {
                        "role": "user",
                        "content": (
                            f"Answer based only on this information:\n{best_chunk}\n\n"
                            f"Prompt: {prompt}"
                        ),
                    }
                ],
                system=f"You are {self.persona}, a knowledge-based assistant. Forget previous context.",
            )
        except Exception:
            logger.exception("RAG response generation failed.")
            return ""

# ---------------------------------------------------------------------------
# EvaluationAgent
# ---------------------------------------------------------------------------

class EvaluationAgent:
    """
    Orchestrates a worker agent and an evaluator in an iterative
    generate-evaluate-correct loop.

    Fix applied vs. the original code
    -----------------------------------
    The original implementation passed ``initial_prompt`` to the worker on every
    iteration, so corrections were never reflected in subsequent passes.

    This version tracks ``prompt_to_evaluate`` separately.  When the evaluator
    returns a "No", correction instructions are generated and a *new* prompt is
    constructed that includes the previous (bad) response plus targeted fix
    instructions.  That corrected prompt is what the worker receives on the
    next iteration - not the original prompt verbatim.
    """

    def __init__(
        self,
        client,
        persona: str,
        evaluation_criteria: str,
        worker_agent,
        max_interactions: int,
    ):
        self.client = client
        self.persona = persona
        self.evaluation_criteria = evaluation_criteria
        self.worker_agent = worker_agent
        self.max_interactions = max_interactions

    def evaluate(self, initial_prompt: str) -> dict:
        """
        Run the generate-evaluate-correct loop.

        Parameters
        ----------
        initial_prompt : str
            The original task description sent to the worker on the first pass.

        Returns
        -------
        dict with keys:
            final_response : str   - the accepted (or last) worker response
            evaluation     : str   - the last evaluator verdict
            iterations     : int   - number of iterations consumed
        """
        prompt_to_evaluate = initial_prompt
        response_from_worker = ""
        final_response = ""
        evaluation = ""

        for i in range(self.max_interactions):
            logger.info("EvaluationAgent - iteration %d", i + 1)
            print(f"\n--- Iteration {i + 1} ---")

            # ----------------------------------------------------------------
            # Step 1: Worker generates (or corrects) a response
            # ----------------------------------------------------------------
            print(
                f" Step 1: Worker responding to prompt:\n{prompt_to_evaluate[:300]}..."
            )
            try:
                response_from_worker = self.worker_agent.respond(
                    input_text=prompt_to_evaluate
                )
            except Exception:
                logger.exception("Worker agent failed.")
                response_from_worker = ""

            print(f" Worker response (truncated):\n{response_from_worker[:400]}...")

            # ----------------------------------------------------------------
            # Step 2: Evaluator judges the response
            # ----------------------------------------------------------------
            print(" Step 2: Evaluator judging the response")
            eval_prompt = (
                f"Does the following answer:\n{response_from_worker}\n\n"
                f"Meet this criteria:\n{self.evaluation_criteria}\n\n"
                "Respond with 'Yes' or 'No' followed by the reason."
            )
            try:
                evaluation = self.client.complete(
                    messages=[{"role": "user", "content": eval_prompt}]
                ).strip()
            except Exception:
                logger.exception("Evaluator LLM call failed.")
                evaluation = "No evaluation due to error."

            print(f" Evaluator verdict:\n{evaluation[:300]}")

            # ----------------------------------------------------------------
            # Step 3: Accept or loop
            # ----------------------------------------------------------------
            if evaluation.lower().startswith("yes"):
                print(" Evaluation PASSED - accepting response.")
                final_response = response_from_worker
                break

            # ----------------------------------------------------------------
            # Step 4: Generate targeted correction instructions
            # ----------------------------------------------------------------
            print(" Step 4: Generating correction instructions")
            instruction_prompt = (
                f"Provide concise, actionable instructions to fix an answer "
                f"based on these reasons it is incorrect:\n{evaluation}"
            )
            try:
                instructions = self.client.complete(
                    messages=[{"role": "user", "content": instruction_prompt}]
                ).strip()
            except Exception:
                logger.exception("Instruction generation failed.")
                instructions = "Correct the structural formatting of the response."

            print(f" Correction instructions:\n{instructions[:300]}")

            # ----------------------------------------------------------------
            # Step 5: Build corrected prompt for the NEXT worker iteration
            #         (KEY FIX: the corrected prompt - not the original -
            #          is what the worker receives next time)
            # ----------------------------------------------------------------
            prompt_to_evaluate = (
                f"Your task is:\n{initial_prompt}\n\n"
                f"Your previous attempt was:\n{response_from_worker}\n\n"
                f"Rewrite your answer applying ONLY these corrections:\n{instructions}\n\n"
                f"Return ONLY the corrected content. Do not evaluate, explain, or repeat these instructions."
            )

        else:
            logger.warning(
                "EvaluationAgent: max_interactions (%d) reached without passing evaluation.",
                self.max_interactions,
            )
            final_response = response_from_worker

        return {
            "final_response": final_response,
            "evaluation": evaluation,
            "iterations": i + 1,  # type: ignore
        }

# ---------------------------------------------------------------------------
# RoutingAgent
# ---------------------------------------------------------------------------

class RoutingAgent:
    """
    Routes a user prompt to the most semantically similar agent using cosine
    similarity over embeddings.

    The ``agents`` list contains dicts with keys:
        name        : str       - human-readable label
        description : str       - ROLE-SEMANTIC description used for embedding
        func        : callable  - called with the user input string; returns str
    """

    def __init__(self, client, agents: list):
        self.client = client
        self.agents = agents

    def route(self, user_input: str, context: str = "") -> str:
        # Embed only the step text for routing
        input_emb = self.client.embed(user_input)
        if not input_emb:
            logger.error("Failed to embed user input for routing.")
            return "Sorry, an error occurred while processing your request."

        best_agent = None
        best_score = -1.0

        for agent in self.agents:
            agent_emb = self.client.embed(agent["description"])
            if not agent_emb:
                continue
            a, b = np.array(input_emb), np.array(agent_emb)
            score = float(np.dot(a, b) / (np.linalg.norm(a) * np.linalg.norm(b)))
            if score > best_score:
                best_score = score
                best_agent = agent

        if best_agent is None:
            return "Sorry, no suitable agent could be selected."

        print(f"[Router] Selected: {best_agent['name']} (similarity={best_score:.3f})")
        logger.info("Router selected '%s' (score=%.3f)", best_agent["name"], best_score)

        try:
            # But pass step + context to the selected agent's support function
            query = f"{user_input}\n\n{context}".strip() if context else user_input
            return best_agent["func"](query)
        except Exception:
            logger.exception("Agent function failed for '%s'.", best_agent.get("name"))
            return "An error occurred while processing your request."

# ---------------------------------------------------------------------------
# ActionPlanningAgent
# ---------------------------------------------------------------------------

class ActionPlanningAgent:
    """
    Extracts an ordered list of actionable steps from a user prompt using a
    knowledge-grounded system message.
    """

    def __init__(self, client, knowledge: str):
        self.client = client
        self.knowledge = knowledge

    def extract_steps_from_prompt(self, prompt: str) -> list:
        system = (
            "You are an action planning agent. Using your knowledge, "
            "extract from the user prompt the ordered steps required to "
            "complete the requested action. Return ONLY the steps as a "
            "numbered list - one step per line. Do not include steps "
            "that are not in your knowledge base. "
            f"Forget any previous context.\n\nKnowledge:\n{self.knowledge}"
        )
        try:
            text = self.client.complete(
                messages=[{"role": "user", "content": prompt}],
                system=system,
            )
            steps = [s.strip() for s in text.splitlines() if s.strip()]
            logger.info("ActionPlanningAgent extracted %d steps.", len(steps))
            return steps
        except Exception:
            logger.exception("ActionPlanningAgent.extract_steps_from_prompt failed.")
            return []
