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
        Default 5 keeps costs reasonable while allowing meaningful refinement.
    """

    def __init__(self, product_spec: str, client, max_eval_iterations: int = 5):
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
            "1. Define user stories from the product specification in the form "
            "'As a `persona`, I want `action` so that `outcome`.'\n"
            "2. Define features by grouping related stories into named capabilities "
            "that describe what the product does at a higher level.\n"
            "3. Define development tasks for each user story, including what must be "
            "built, acceptance criteria, effort, and dependencies.\n\n"
            "IMPORTANT: Extract ONLY the steps that are explicitly requested in the prompt.\n"
            "- If the prompt asks only for user stories, return only step 1.\n"
            "- If the prompt asks only for features, return only step 2.\n"
            "- If the prompt asks for development tasks or a full plan, return steps 1, 2, "
            "and 3 in order - always include all three steps even if user stories or features "
            "could be inferred from the product specification. Each step must be executed "
            "explicitly; do not collapse or skip steps.\n"
            "- Never infer that a step has already been completed. If the prompt requests "
            "a full plan or development tasks, all three steps must appear in the output."
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
            "- Clear and concise\n"
            "- Focused on a single, specific user need\n"
            "- Free of technical implementation details\n"
            "- Written from the user's perspective, not the system's"
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
            "-  Feature Name      : A clear, concise title that identifies the capability\n"
            "-  Description       : What the feature does and its purpose\n"
            "-  Key Functionality : The specific capabilities the feature provides\n"
            "-  User Benefit      : How this feature creates value for the user\n\n"
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
            "-  Feature Name      : A clear, concise title that identifies the capability\n"
            "-  Description       : A brief explanation of what the feature does and its purpose\n"
            "-  Key Functionality : The specific capabilities or actions the feature provides\n"
            "-  User Benefit      : How this feature creates value for the user\n\n"
            "Each feature must group at least two related user stories. \n"
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
            "You are a Development Engineer writing a sprint-ready engineering backlog. "
            "Your sole responsibility is to produce structured task cards - one per engineering "
            "concern - for each user story you are given. "
            "You do not write user stories, group features, explain your reasoning, or add commentary. "
            "If context is missing, infer reasonable assumptions silently and proceed. "
            "Never output a refusal or a disclaimer - output task cards only."
        )
        knowledge_dev_engineer = (
            "A development task card documents one atomic unit of engineering work required "
            "to implement a user story. Each card must contain exactly these fields:\n\n"
            "- Task ID             : Sequential identifier in the format TASK-NNN (e.g. TASK-001)\n"
            "- Task Title          : ≤10 words. Action verb + subject (e.g. 'Implement JWT login endpoint')\n"
            "- Related User Story  : The full user story this task implements\n"
            "- Description         : 2–4 sentences describing the technical work: what to build, "
            "  how it fits the story, and any key implementation detail\n"
            "- Acceptance Criteria : 3–5 bullet points, each independently testable and starting "
            "  with a condition (e.g. '- Endpoint returns HTTP 201 when...')\n"
            "- Estimated Effort    : Story points only, using the Fibonacci scale: 1, 2, 3, 5, or 8. "
            "  Use the full range — not all backend tasks are equivalent in complexity. "
            "  Tasks that consolidate multiple user stories, span multiple technical concerns "
            "  (e.g. rule evaluation engine, NLP pipeline, multi-metric aggregation), or require "
            "  significant design work should be estimated at 8 points and flagged as candidates "
            "  for splitting. Simple CRUD, schema, or UI counterpart tasks should be estimated "
            "  at 1, 2, or 3 points accordingly.\n"
            "- Dependencies        : Comma-separated Task IDs that must complete first, or 'None'\n\n"
            "Rules:\n"
            "- Split front-end and back-end work into separate tasks.\n"
            "- Split database schema changes into their own task.\n"
            "- Each task must be completable within a single sprint.\n"
            "- If multiple user stories require the same technical implementation "
            "  (e.g. adding values to a shared registry or enum), combine them into "
            "  one task and list all related stories in the Related User Story field.\n"
            "- Every feature that an administrator or manager interacts with directly "
            "  requires both a backend task and a separate frontend UI task. "
            "  Do not create a backend task without a corresponding UI task unless the "
            "  feature is purely infrastructure or has no user-facing component.\n"
            "- Any task estimated at 8 story points must include a Note field stating "
            "  'Candidate for splitting' and suggesting how it could be divided "
            "  (e.g. by provider, by pipeline stage, or by layer). "
            "  Tasks estimated at fewer than 8 points must not include a Note field.\n"
            "- Non-functional requirements (availability, latency, security, scalability) "
            "  must each produce at least one dedicated task if they appear in the product "
            "  specification. Treat each NFR as a separate concern — do not merge availability "
            "  into scalability or latency into routing performance.\n"
            "- When any task depends on sending data to or receiving data from an external "
            "  system (messaging, CRM, ticketing), the integration connector task must be "
            "  completed first. Always list the connector as a dependency of the consuming "
            "  task, never the reverse.\n"
            "- SLA escalation tasks that trigger notifications must depend on the "
            "  messaging connector task, since notifications are delivered through it.\n"
            "- Every task card must include all fields in the output format template. "
            "  Never omit the Task ID field regardless of card length or content.\n"
            "- End with a summary table: Task ID | Task Title | User Story | Effort | Dependencies\n"
            "- In the summary table, the User Story column must contain the full text of "
            "  the related user story, exactly as it appears in the task card. "
            "  Do not substitute shorthand labels or summaries.\n\n"
            "Output format - use this exact markdown structure for every card:\n\n"
            "### TASK-NNN\n\n"
            "| Field | Detail |\n"
            "| :--- | :--- |\n"
            "| **Task ID** | TASK-NNN |\n"
            "| **Task Title** | ... |\n"
            "| **Related User Story** | ... |\n"
            "| **Description** | ... |\n"
            "| **Acceptance Criteria** | - criterion one<br>- criterion two<br>- criterion three |\n"
            "| **Estimated Effort** | N story points |\n"
            "| **Dependencies** | TASK-NNN, TASK-NNN or None |\n"
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
            "-  Task ID            : A unique identifier for tracking purposes\n"
            "-  Task Title         : Brief description of the specific development work\n"
            "-  Related User Story : Reference to the parent user story\n"
            "-  Description        : Detailed explanation of the technical work required\n"
            "-  Acceptance Criteria: Specific requirements that must be met for completion\n"
            "-  Estimated Effort   : Time and/or complexity estimation\n"
            "-  Dependencies       : Any tasks that must be completed first\n\n"
            "Every user story referenced in the input must have at least one task. \n"
            "Acceptance criteria must be specific and testable with measurable conditions \n"
            "(e.g. 'emails are routed within 5 seconds', 'returns HTTP 400 when input is invalid'). \n"
            "Vague criteria such as 'works correctly' or 'is displayed accurately' are not acceptable."
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
                        "Responsible for defining development tasks for each user story, "
                        "including what must be built, acceptance criteria, effort, and dependencies. "
                        "Each task has a Task ID, Task Title, effort in story points (Fibonacci scale), "
                        "technical acceptance criteria, and a dependency list. "
                        "Does not write user stories or define features. "
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
            print(f"{s}")

        completed_outputs = []
        context_sections = []

        # Anchor the spec as the first named context section
        if self.product_spec:
            context_sections.append(f"Product specification:\n{self.product_spec}")

        for step in workflow_steps:
            print(f"\n--- Executing step: {step} ---")

            # Build structured context from everything gathered so far
            accumulated_context = "\n\n".join(context_sections)

            try:
                result = self.routing_agent.route(
                    user_input=step,
                    context=accumulated_context,
                )
            except Exception:
                logger.exception("Routing failed for step: %s", step)
                result = f"[ERROR] Routing failed for step: {step}"

            completed_outputs.append(result)

            # Label each section so downstream steps have clear grounding
            step_label = step.split(".")[0].strip() if "." in step else step[:80]
            context_sections.append(f"Output from step '{step_label}':\n{result}")

            print(f"Step output (truncated):\n{result[:400]}...\n")

        # Take the last successful result, not just the last result
        final_output = next(
            (r for r in reversed(completed_outputs) if not r.startswith("[ERROR]")),
            completed_outputs[-1] if completed_outputs else "",
        )

        print(f"\n{'='*80}")
        print("Workflow complete.")
        print(f"{'='*80}\n")

        return {
            "steps": workflow_steps,
            "step_outputs": completed_outputs,
            "final_output": final_output,
            "prompt": prompt,
        }
