"""
src/processor.py
----------------
Core orchestration layer for the Smart Backlog Assistant.

ALL prompt engineering lives here: persona strings, knowledge strings,
evaluation criteria, and routing descriptions are defined and documented in
this module. The agent classes in ``agents/base_agents.py`` are intentionally
prompt-agnostic - they provide the execution machinery; this file provides the
domain knowledge.

Workflow
--------
1. ``BacklogProcessor`` is instantiated with a product spec string and an
   ``AIClient`` (from ``src.ai_client``).
2. ``_build()`` assembles and wires all agents, passing the client to each one.
3. ``run(prompt)`` feeds the prompt through:
       ActionPlanningAgent → steps
       RoutingAgent        → dispatches each step to the right support function
       Support function    → calls KnowledgeAugmentedPromptAgent + EvaluationAgent
4. The final validated output (last completed step) is returned.

Provider switching
------------------
BacklogProcessor is fully provider-agnostic. Pass any AIClient instance:

    from src.ai_client import build_client
    from src.processor import BacklogProcessor

    # OpenAI
    processor = BacklogProcessor(spec, build_client("openai"))

    # Anthropic (chat) + OpenAI (embeddings for routing)
    processor = BacklogProcessor(spec, build_client("anthropic"))
"""

import logging

from agents.base_agents import (
    ActionPlanningAgent,
    EvaluationAgent,
    KnowledgeAugmentedPromptAgent,
    RoutingAgent,
)

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# BacklogProcessor
# ---------------------------------------------------------------------------

class BacklogProcessor:
    """
    Orchestrates the full multi-agent backlog generation workflow.

    Parameters
    ----------
    product_spec : str
        Raw text of the product specification document.
    client : AIClient
        Configured AI client from ``src.ai_client.build_client()``.
    max_eval_iterations : int
        Maximum correction loops the EvaluationAgent may run per step.
        Default 3 keeps costs reasonable while allowing meaningful refinement.
    """

    def __init__(self, product_spec: str, client, max_eval_iterations: int = 3):
        self.product_spec = product_spec
        self.client = client
        self.max_eval_iterations = max_eval_iterations

        self._agents_built = False
        self._build()

    # -----------------------------------------------------------------------
    # Agent assembly - all prompt engineering is here
    # -----------------------------------------------------------------------

    def _build(self):
        """Instantiate and wire all agents. Called once during __init__."""

        client = self.client
        spec = self.product_spec
        max_it = self.max_eval_iterations

        # ===================================================================
        # ACTION PLANNING AGENT
        # ===================================================================
        # WHY: The knowledge string explicitly lists the three deliverable
        # types (stories, features, tasks) and their relationships. This
        # constrains the planner so it never invents steps outside the
        # workflow (e.g. "deploy to production") that would confuse the router.
        # ===================================================================
        knowledge_action_planning = (
            "A full development plan for a product is produced in three ordered steps:\n"
            "1. Define user stories from the product specification - sentences in the form 'As a `persona`, I want `action` so that `outcome`'. Each story maps to one specific product functionality.\n"
            "2. Define features by grouping related stories into named capabilities that describe what the product does at a higher level.\n"
            "3. Define development tasks - for each user story, list the engineering work required: what must be built, acceptance criteria, effort, and dependencies.\n\n"
            "IMPORTANT: Extract ONLY the steps that are explicitly requested in the prompt. "
            "If the prompt asks only for user stories, return only step 1. "
            "If the prompt asks only for features, return only step 2. "
            "If the prompt asks for development tasks or a full plan, return all three steps in order."
        )

        self.action_planning_agent = ActionPlanningAgent(
            client=client,
            knowledge=knowledge_action_planning,
        )

        # ===================================================================
        # PRODUCT MANAGER - knowledge agent
        # ===================================================================
        # WHY persona: Naming the role ("Product Manager") and responsibility
        # ("defining user stories") focuses the model on story format and
        # prevents it from generating features or tasks unprompted.
        #
        # WHY knowledge: The product spec is embedded directly so the agent
        # generates stories grounded in THIS product, not generic examples.
        # The format reminder ("sentences always start with 'As a'") is
        # placed inside the knowledge string so it is active whenever the
        # spec is in context.
        # ===================================================================
        persona_product_manager = (
            "You are a Product Manager. Your sole responsibility is to define "
            "user stories for a product. You do not define features or tasks."
        )
        knowledge_product_manager = (
            "User stories are defined by writing sentences that describe a persona, "
            "an action, and a desired outcome.\n"
            "Every story MUST start with: 'As a'...\n"
            "Write ONE story per product functionality - do not combine multiple "
            "functionalities into a single story.\n"
            "Cover ALL personas and ALL capabilities mentioned in the specification. "
            "Do not omit features. If the spec mentions multiple variants of a "
            "capability (e.g. IMAP/SMTP AND Microsoft 365 AND Google Workspace), "
            "write a separate story for each.\n\n"
            f"Product specification:\n{spec}"
        )

        self._pm_knowledge_agent = KnowledgeAugmentedPromptAgent(
            client=client,
            persona=persona_product_manager,
            knowledge=knowledge_product_manager,
        )

        # ===================================================================
        # PRODUCT MANAGER - evaluation agent
        # ===================================================================
        # WHY criteria: The canonical Connextra format is spelled out
        # explicitly so the evaluator has an unambiguous pass/fail test.
        # ===================================================================
        criteria_pm = (
            "The answer should consist exclusively of user stories that follow "
            "this exact structure:\n"
            "  As a [type of user], I want [an action or feature] so that [benefit/value].\n\n"
            "Each story must be:\n"
            "  - Clear and concise\n"
            "  - Focused on a single, specific user need\n"
            "  - Free of technical implementation details\n"
            "  - Written from the user's perspective, not the system's"
        )

        self._pm_eval_agent = EvaluationAgent(
            client=client,
            persona=(
                "You are a quality-assurance agent that evaluates the output of a "
                "Product Manager. You check whether user stories follow correct format "
                "and content standards."
            ),
            evaluation_criteria=criteria_pm,
            worker_agent=self._pm_knowledge_agent,
            max_interactions=max_it,
        )

        # ===================================================================
        # PROGRAM MANAGER - knowledge agent
        # ===================================================================
        persona_program_manager = (
            "You are a Program Manager. Your sole responsibility is to define "
            "product features by grouping related user stories. You do not "
            "write individual user stories or define engineering tasks."
        )
        knowledge_program_manager = (
            "Product features are defined by organizing related user stories into "
            "cohesive, named groups.\n"
            "Each feature must include:\n"
            "  Feature Name      : A clear, concise title that identifies the capability\n"
            "  Description       : What the feature does and its purpose\n"
            "  Key Functionality : The specific capabilities the feature provides\n"
            "  User Benefit      : How this feature creates value for the user\n\n"
            "Group stories by the common outcome or persona they serve.\n"
            "A feature should contain at least two related stories."
        )

        self._prog_knowledge_agent = KnowledgeAugmentedPromptAgent(
            client=client,
            persona=persona_program_manager,
            knowledge=knowledge_program_manager,
        )

        # ===================================================================
        # PROGRAM MANAGER - evaluation agent
        # ===================================================================
        criteria_prog = (
            "The answer should consist of product features that each follow "
            "this exact structure:\n"
            "  Feature Name      : A clear, concise title that identifies the capability\n"
            "  Description       : A brief explanation of what the feature does and its purpose\n"
            "  Key Functionality : The specific capabilities or actions the feature provides\n"
            "  User Benefit      : How this feature creates value for the user\n\n"
            "Each feature must group at least two related user stories. "
            "Features must not contain individual task-level implementation details."
        )

        self._prog_eval_agent = EvaluationAgent(
            client=client,
            persona=(
                "You are a quality-assurance agent that evaluates the output of a "
                "Program Manager. You check whether product features follow correct "
                "format and have been properly grouped from user stories."
            ),
            evaluation_criteria=criteria_prog,
            worker_agent=self._prog_knowledge_agent,
            max_interactions=max_it,
        )

        # ===================================================================
        # DEVELOPMENT ENGINEER - knowledge agent
        # ===================================================================
        persona_dev_engineer = (
            "You are a Development Engineer. Your sole responsibility is to define "
            "engineering development tasks for each user story. You do not write "
            "user stories or group features."
        )
        knowledge_dev_engineer = (
            "Development tasks are defined by identifying what must be built to "
            "implement each user story.\n"
            "Each task must include:\n"
            "  Task ID            : A unique identifier (e.g. TASK-001)\n"
            "  Task Title         : A brief description of the specific work\n"
            "  Related User Story : Reference to the parent user story\n"
            "  Description        : Detailed explanation of the technical work required\n"
            "  Acceptance Criteria: Specific, testable requirements for completion\n"
            "  Estimated Effort   : Time or complexity estimate (e.g. 2h, 3 story points)\n"
            "  Dependencies       : Any tasks that must be completed first (or 'None')\n\n"
            "Write at least one task per user story. Tasks should be small enough "
            "to be completed in one sprint."
        )

        self._dev_knowledge_agent = KnowledgeAugmentedPromptAgent(
            client=client,
            persona=persona_dev_engineer,
            knowledge=knowledge_dev_engineer,
        )

        # ===================================================================
        # DEVELOPMENT ENGINEER - evaluation agent
        # ===================================================================
        criteria_dev = (
            "The answer should consist of development tasks that each follow "
            "this exact structure:\n"
            "  Task ID            : A unique identifier for tracking purposes\n"
            "  Task Title         : Brief description of the specific development work\n"
            "  Related User Story : Reference to the parent user story\n"
            "  Description        : Detailed explanation of the technical work required\n"
            "  Acceptance Criteria: Specific requirements that must be met for completion\n"
            "  Estimated Effort   : Time and/or complexity estimation\n"
            "  Dependencies       : Any tasks that must be completed first\n\n"
            "Every user story referenced in the input must have at least one task. "
            "Acceptance criteria must be specific and testable with measurable conditions "
            "(e.g. 'emails are routed within 5 seconds', 'returns HTTP 400 when input is invalid'). "
            "Vague criteria such as 'works correctly' or 'is displayed accurately' are not acceptable.\n"
        )

        self._dev_eval_agent = EvaluationAgent(
            client=client,
            persona=(
                "You are a quality-assurance agent that evaluates the output of a "
                "Development Engineer. You check whether development tasks follow "
                "correct structure and are sufficiently detailed."
            ),
            evaluation_criteria=criteria_dev,
            worker_agent=self._dev_knowledge_agent,
            max_interactions=max_it,
        )

        # ===================================================================
        # ROUTING AGENT
        # ===================================================================
        # WHY descriptions: Role-semantic vocabulary ("user stories",
        # "Connextra format", "As a … I want … so that") produces embeddings
        # close to the actual step text, making routing reliable.
        # Infrastructure language ("Routes to the … support function") embeds
        # in a completely different semantic space and causes mis-routing. This
        # has been improved as per Claude's suggestion over my Udacity Agentic AI
        # P2 implementation.
        # ===================================================================
        self.routing_agent = RoutingAgent(
            client=client,
            agents=[
                {
                    "name": "Product Manager",
                    "description": (
                        "Responsible for defining product personas and user stories only. "
                        "A user story follows the Connextra format: "
                        "'As a `persona`, I want `action` so that `outcome`'. "
                        "Does not define features, group stories, or create technical tasks."
                    ),
                    "func": self._pm_support,
                },
                {
                    "name": "Program Manager",
                    "description": (
                        "Responsible for grouping related user stories into named product "
                        "features. A feature describes a capability with name, description, "
                        "key functionality, and user benefit. Does not write individual "
                        "user stories and does not define engineering or development tasks."
                    ),
                    "func": self._prog_support,
                },
                {
                    "name": "Development Engineer",
                    "description": (
                        "Responsible for writing engineering development tasks, sprint tickets, "
                        "and technical work items for each user story. Each task has a Task ID, "
                        "Task Title, effort estimate in story points or hours, technical acceptance "
                        "criteria, and dependencies. Does not write user stories or define features. "
                        "Output is a structured list of implementation tasks ready for a sprint backlog."
                    ),
                    "func": self._dev_support,
                },
            ],
        )

        self._agents_built = True
        logger.info(
            "BacklogProcessor: all agents built (provider=%s, model=%s).",
            client.provider,
            client.chat_model,
        )

    # -----------------------------------------------------------------------
    # Support functions
    # -----------------------------------------------------------------------
    # Each support function passes the query DIRECTLY to evaluate().
    # The EvaluationAgent handles the first worker call internally, so there
    # is no redundant respond() call here.
    # -----------------------------------------------------------------------

    def _pm_support(self, query: str) -> str:
        logger.info("PM support function invoked: %s", query[:80])
        try:
            result = self._pm_eval_agent.evaluate(query)
            return result.get("final_response", "")
        except Exception:
            logger.exception("PM support function failed.")
            return f"[ERROR] Failed to generate user stories for: {query}"

    def _prog_support(self, query: str) -> str:
        logger.info("Program Manager support function invoked: %s", query[:80])
        try:
            result = self._prog_eval_agent.evaluate(query)
            return result.get("final_response", "")
        except Exception:
            logger.exception("Program Manager support function failed.")
            return f"[ERROR] Failed to generate features for: {query}"

    def _dev_support(self, query: str) -> str:
        logger.info("Dev Engineer support function invoked: %s", query[:80])
        try:
            result = self._dev_eval_agent.evaluate(query)
            return result.get("final_response", "")
        except Exception:
            logger.exception("Dev Engineer support function failed.")
            return f"[ERROR] Failed to generate tasks for: {query}"

    # -----------------------------------------------------------------------
    # Public API
    # -----------------------------------------------------------------------

    def run(self, prompt: str) -> dict:
        """
        Execute the full agentic workflow for *prompt*.

        Parameters
        ----------
        prompt : str
            A natural-language request such as
            "What would the development tasks for this product be?"

        Returns
        -------
        dict with keys:
            steps           : list[str]  - steps extracted by the planner
            step_outputs    : list[str]  - output of each routed step
            final_output    : str        - output of the last completed step
            prompt          : str        - the original prompt
        """
        if not self._agents_built:
            raise RuntimeError("Agents have not been built. Call _build() first.")

        logger.info("BacklogProcessor.run() - prompt: %s", prompt)
        print(f"\n{'='*80}")
        print(f"Workflow prompt: {prompt}")
        print(f"Provider: {self.client.provider}\nModel: {self.client.chat_model}")
        print(f"\n{'='*80}\n")

        print("Extracting workflow steps via ActionPlanningAgent...")
        workflow_steps = self.action_planning_agent.extract_steps_from_prompt(prompt)

        if not workflow_steps:
            logger.warning("No workflow steps extracted for prompt: %s", prompt)
            return {
                "steps": [],
                "step_outputs": [],
                "final_output": "",
                "prompt": prompt,
            }

        print(f"Steps extracted ({len(workflow_steps)}):")
        for i, s in enumerate(workflow_steps, 1):
            print(f"  {i}. {s}")

        completed_outputs = []
        accumulated_context = ""

        for step in workflow_steps:
            print(f"\n--- Executing step: {step} ---")
            try:
                # Inject all previous step outputs as context
                query = f"{step}\n\n{accumulated_context}".strip() if accumulated_context else step
                result = self.routing_agent.route(query)
            except Exception:
                logger.exception("Routing failed for step: %s", step)
                result = f"[ERROR] Routing failed for step: {step}"

            completed_outputs.append(result)
            # Append this step's output to the running context for subsequent steps
            accumulated_context += f"\nOutput from previous step:\n{result}\n"
            print(f"Step output (truncated):\n{result[:400]}...\n")

        final_output = completed_outputs[-1] if completed_outputs else ""

        print(f"\n{'='*80}")
        print("Workflow complete.")
        print(f"{'='*80}\n")

        return {
            "steps": workflow_steps,
            "step_outputs": completed_outputs,
            "final_output": final_output,
            "prompt": prompt,
        }
