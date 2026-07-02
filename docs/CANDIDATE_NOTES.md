# Candidate Notes - Smart Backlog Assistant

```md
## Accenture RDE Certification - Capstone Project Documentation
## Candidate: Eduardo Nicacio [eduardo.nicacio@accenture.com]
## Date: June 5th, 2026
```

## 1. Problem Definition

### What problem does this solve?

Technical Program Managers and Product Owners spend significant time manually
converting product specifications into structured development artifacts (user
stories, features, and tasks). This process is repetitive, prone to
inconsistency across contributors, and often a bottleneck before engineering
work can begin.

### Specific use cases

1. **New product discovery** - A TPM uploads a product spec document and
   instantly receives a full first-draft backlog (stories → features → tasks)
   ready for review and grooming.

2. **Meeting notes to backlog** - Engineering kick-off notes are loaded and
   the assistant extracts actionable stories and tasks, saving 60-90 minutes of
   manual transcription.

3. **Incremental backlog enrichment** - An existing backlog JSON is provided
   alongside a new requirements document; the assistant generates only the
   missing stories and tasks without duplicating existing items.

### AI tools used to refine the problem statement

Claude Sonnet was used to critique early drafts of the problem statement.
Specifically: "Is this problem specific enough for a certification project?
What are the boundaries?" - this surfaced the need to constrain scope to
three artifact types (stories, features, tasks) rather than attempting a
full project management suite.

---

## 2. Solution Design

### Architecture

```txt
┌──────────────────────────────────────────────────────────┐
│  main.py  (CLI entry point)                              │
│   │                                                      │
│   ├── src/document_loader.py   → loads .txt / .pdf spec  │
│   ├── src/backlog_loader.py    → loads existing backlog  │
│   │                                                      │
│   └── src/processor.py  (BacklogProcessor)               │
│         │                                                │
│         ├── ActionPlanningAgent ──────────────────────►  │
│         │      extracts ordered steps from prompt        │
│         │                                                │
│         └── RoutingAgent                                 │
│               │  (cosine similarity over embeddings)     │
│               │                                          │
│               ├──► _pm_support()                         │
│               │       └── KnowledgeAugmentedPromptAgent  │
│               │           + EvaluationAgent (loop)       │
│               │                                          │
│               ├──► _prog_support()                       │
│               │       └── KnowledgeAugmentedPromptAgent  │
│               │           + EvaluationAgent (loop)       │
│               │                                          │
│               └──► _dev_support()                        │
│                       └── KnowledgeAugmentedPromptAgent  │
│                           + EvaluationAgent (loop)       │
│                                                          │
│         │                                                │
│   src/formatter.py  → writes Markdown to outputs/        │
└──────────────────────────────────────────────────────────┘
```

**Data flow**:

1. User provides a product spec file and (optionally) an existing backlog.
2. `document_loader` reads the spec; `backlog_loader` reads existing items.
3. `BacklogProcessor` is initialized: all six agents are wired with their
   personas, knowledge strings, and evaluation criteria.
4. The workflow prompt is fed to `ActionPlanningAgent`, which returns an
   ordered list of steps (e.g. ["1. Define user stories", "2. Define
   features", "3. Define development tasks"]).
5. Each step is passed to `RoutingAgent`.  The router computes cosine
   similarity between the step text and each agent's role-semantic
   description, then calls the best-matching support function.
6. Each support function passes the step query to its `EvaluationAgent`,
   which runs the generate-evaluate-correct loop.
7. The validated output of the last step is the primary deliverable.
8. `formatter` writes all step outputs to a timestamped Markdown file in
   `outputs/`.

### Where AI is used

| Component | AI usage |
| :--- | :--- |
| `ActionPlanningAgent` | Chat completion - extracts steps from the prompt |
| `KnowledgeAugmentedPromptAgent` | Chat completion - generates stories/features/tasks |
| `EvaluationAgent` (evaluator call) | Chat completion - judges the worker output |
| `EvaluationAgent` (instruction call) | Chat completion - generates correction instructions |
| `RoutingAgent` | Embeddings - cosine similarity for semantic routing |

---

## 3. Prompt Engineering Decisions

All prompt engineering is centralized in `src/processor.py`. Each decision
is explained below.

### 3.1 ActionPlanningAgent - knowledge string

```python
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
```

**Why**: Explicitly naming the three deliverables and their order constrains
the planner. Without this, gpt-5.4-mini often generates additional steps
("deploy to staging", "run user acceptance tests") that have no matching agent
in the router, causing routing failures.

**Iteration 1**: Early drafts used a single paragraph. Switching to a numbered
list with inline definitions improved step extraction accuracy from ~60% to
~95% in manual testing.

**Iteration 2**: The prompt above changed slightly since its initial version
due to some issues identified in the output files from both OpenAI `gpt-5.4-mini`
and Anthropic `claude-sonnet-4-6`, i.e., both models ran the full workflow (user
stories, features and tasks) even when requested to identify and generate only
user stories or features for a given product.

### 3.2 KnowledgeAugmentedPromptAgent - persona strings

Each agent's persona string names both the role AND the boundary:

```python
persona_product_manager = (
   "You are a Product Manager. Your sole responsibility is to define "
   "user stories for a product. You do not define features or tasks."
)
```

**Why**: Without the negative constraint ("You **do not**..."), the PM agent often generated a mix of stories AND features in a
single response, which then failed the evaluation criteria. Explicit
exclusions proved more reliable than relying on the evaluation loop to
correct mixed output.

### 3.3 KnowledgeAugmentedPromptAgent - knowledge strings

The product spec is embedded in the PM agent's knowledge string:

```python
knowledge_product_manager = (
   "User stories are defined by writing sentences that describe a persona, "
   "an action, and a desired outcome.\n"
   "Every story MUST start with: 'As a'...\n"
   "Write ONE story per product functionality - do not combine multiple "
   "functionalities into a single story.\n"
   "Cover ALL personas listed in the specification, including passive ones "
   "(e.g. End Customers who interact with the system indirectly). "
   "Write at least one story per persona even if their interaction is limited.\n"
   "Do not omit features. If the spec mentions multiple variants of a "
   "capability (e.g. IMAP/SMTP AND Microsoft 365 AND Google Workspace), "
   "write a separate story for each.\n\n"
   f"Product specification:\n\n{spec}"
)
```

**Why**: Injecting the spec directly into the knowledge string (rather than
the user prompt) ensures it is always present in the system message, not the
user turn. The models appear to respect system-level knowledge more consistently than
user-turn content for grounding purposes.

### 3.4 KnowledgeAugmentedPromptAgent - Dev Engineer knowledge string

The dev engineer knowledge string went through the most iteration of any agent.
Key decisions:

- **Output format template**: A literal markdown table template at the bottom of the
  knowledge string was the single highest-impact change. Both models mirror it
  faithfully; without it, gpt-5.4-mini produced feature summaries and Claude
  produced inconsistently structured cards.

- **Fibonacci calibration with examples**: Specifying "not all backend tasks are
  equivalent" with concrete examples (rule evaluation engine → 8pts, simple CRUD → 3pts)
  eliminated the all-5s compression seen in early runs.

- **Schema split rule**: Explicitly requiring database schema changes as their own task
  produced the schema → API → UI layering that makes the final backlog sprint-ready.

- **Dependency direction rule**: Two separate rules were required - a general connector
  dependency rule and a specific SLA escalation rule - because the model consistently
  inverted the Slack/SLA dependency without the explicit override.

### 3.5 EvaluationAgent - criteria strings

Criteria are written as checklists, not prose:

```python
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
```

**Why**: The evaluator's `eval_prompt` asks "Does the answer meet this
criteria? Respond Yes or No". A checklist-style criteria string makes
Yes/No assessment unambiguous. Prose criteria produced vague evaluations
like "Mostly yes, but..." which the `evaluation.lower().startswith("yes")`
check failed to parse correctly.

### 3.6 RoutingAgent - description strings

```python
...
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
...
```

**Why**: The routing agent embeds both the step text and each agent
description, then selects the highest cosine similarity. Using
system/infrastructure language ("Routes to the Product Manager support
function") embeds in a completely different semantic space from the step
text ("Define user stories for the email router"), causing consistent
mis-routing.

Role-semantic descriptions that include domain vocabulary ("user stories",
"Connextra format", "As a … I want … so that") produce embeddings close to
the actual step text, making routing reliable.

This was the single biggest fix from the original `agentic_workflow.py`.
Before the fix, all three steps were consistently routed to the same agent
(whichever happened to have the best generic-text similarity).

---

## 4. Bug Fixes vs. Original Code

### Bug 1 - EvaluationAgent correction loop (base_agents.py)

**Original behavior**: After a "No" verdict, the evaluator generated
correction instructions, but then called `worker_agent.respond()` again with
the **original prompt** - not the corrected prompt. The corrections were
computed and immediately discarded.

**Fix**: The corrected prompt (embedding the original task + previous bad
response + correction instructions) is stored in `prompt_to_evaluate` and
passed to the worker on the next iteration.

```python
# BEFORE (broken - original prompt passed every time)
response_from_worker = self.worker_agent.respond(input_text=initial_prompt)

# AFTER (fixed - corrected prompt on subsequent iterations)
response_from_worker = self.worker_agent.respond(input_text=prompt_to_evaluate)
# ...
prompt_to_evaluate = (
   f"Your task is:\n{initial_prompt}\n\n"
   f"Your previous attempt was:\n{response_from_worker}\n\n"
   f"Rewrite your answer applying ONLY these corrections:\n{instructions}\n\n"
   f"Return ONLY the corrected content. Do not evaluate, explain, or repeat these instructions."
)
```

**Test coverage**: `TestEvaluationAgent.test_corrected_prompt_fed_back_not_original`

### Bug 2 - Redundant respond() call in support functions (processor.py)

**Original behavior**: Each support function called `knowledge_agent.respond()`
then passed the result to `evaluation_agent.evaluate()`. However,
`evaluate()` also calls `worker_agent.respond()` internally on iteration 1.
This meant the first worker call was wasted - it generated a response that
was immediately discarded, and the evaluation loop generated a fresh one.

**Fix**: Support functions pass the query directly to `evaluate()`, which
handles all worker calls.

```python
# BEFORE (redundant call)
agent_response = product_manager_knowledge_agent.respond(input_text=query)
model_evaluation = product_manager_evaluation_agent.evaluate(agent_response)

# AFTER (single path through evaluate)
result = self._pm_eval_agent.evaluate(query)
```

### Bug 3 - Router description language (processor.py)

**Original descriptions**:
> "Routes to the Product Manager support function for user story extraction."

**Fixed descriptions**:
> "Responsible for defining product personas and user stories only. A user
> story follows the Connextra format: 'As a `persona`, I want `action` so that
> `outcome`'. Does not define features, group stories, or create technical
> tasks."

**Why it matters**: See Section 3.5 above.

---

## 5. Testing Approach

### Golden prompts

Three prompts were used to validate the end-to-end workflow:

| # | Prompt | Expected routing | Expected output shape |
| :--- | :--- | :--- | :--- |
| 1 | `"What would the development tasks for this product be?"` | PM → ProgMgr → DevEng | Dev tasks |
| 2 | `"What are the user stories for this product?"` | PM only | Connextra-format stories |
| 3 | `"What features should this product have?"` | ProgMgr only | Feature cards with 4 fields |

---

### Golden prompt results

---

#### Model: Open AI gpt-5.4-mini - sample outputs from June 2nd, 2026 run

---

```bash
# Executes the whole workflow with the default prompt, i.e., "What would the development tasks for this product be?", and produce only the dev tasks
python .\main.py --spec .\inputs\sample_requirements.txt --prompt "What would the development tasks for this product be?"
```

Attachment: [outputs/openai/gpt-5.4-mini/backlog_20260602_132342.md](/outputs/openai/gpt-5.4-mini/backlog_20260602_132342.md)

```bash
# Should return user stories only
python .\main.py --spec .\inputs\sample_requirements.txt --prompt "What are the user stories for this product?"
```

Attachment: [outputs/openai/gpt-5.4-mini/backlog_20260602_134756.md](/outputs/openai/gpt-5.4-mini/backlog_20260602_134756.md)

```bash
# Should return feature cards with 4 or 5 fields only
python .\main.py --spec .\inputs\sample_requirements.txt --prompt "What features should this product have?"
```

Attachment: [outputs/openai/gpt-5.4-mini/backlog_20260602_132942.md](/outputs/openai/gpt-5.4-mini/backlog_20260602_132942.md)

---

#### Model: Anthropic claude-sonnet-4-6 - sample outputs from June 4th, 2026 run (via Claude Web UI)

---

```bash
# Executes the whole workflow with the default prompt, i.e., "What would the development tasks for this product be?", and produce only the dev tasks
python .\main.py --spec .\inputs\sample_requirements.txt --prompt "What would the development tasks for this product be?"
```

Attachment: [outputs/anthropic/claude-sonnet-4-6/backlog_20260604_164019.md](/outputs/anthropic/claude-sonnet-4-6/backlog_20260604_164019.md)

```bash
# Should return user stories only
python .\main.py --spec .\inputs\sample_requirements.txt --prompt "What are the user stories for this product?"
```

Attachment: [outputs/anthropic/claude-sonnet-4-6/backlog_20260604_164500.md](/outputs/anthropic/claude-sonnet-4-6/backlog_20260604_164500.md)

```bash
# Should return feature cards with 4 or 5 fields only
python .\main.py --spec .\inputs\sample_requirements.txt --prompt "What features should this product have?"
```

Attachment: [outputs/anthropic/claude-sonnet-4-6/backlog_20260604_165000.md](/outputs/anthropic/claude-sonnet-4-6/backlog_20260604_165000.md)

---

## LLM as a Judge

Once I've got everything working the way I wanted, I then decided to have Claude Sonnet 4.6 as a judge of the outputs from the models I've interacted with the most: OpenAI Gpt 5.4 mini and Anthropic Claude Sonnet 4.6 itself. Here's what it came out after analyzing the main python scripts - `agents/base_agents.py` and `src/processor.py` -, the sample requirements - `input/sample_requirements.txt`-, and the output from both models (check the `outputs` folder for them):

### OpenAI gpt-5.4-mini outputs - latest deliverables from June 2nd, 2026

---

**13:23:42 - Full workflow ("What would the development tasks for this product be?")**

This is a clean, production-quality output and the strongest full-workflow run to date. 27 tasks, correct schema → backend → UI layering throughout, all four NFRs as dedicated tasks, full user story text in the summary table, and the dependency graph is architecturally sound. The messaging connector dependency inversion is fully resolved - TASK-012 has no dependencies and TASK-013 correctly lists TASK-010 and TASK-012. No missing Task ID fields. The Fibonacci spread is well-calibrated: 3-point schema tasks, 5-point mid-complexity backends and UIs, 8-point engines with split notes.

One small observation: TASK-015 (analytics events schema) is estimated at 5 points while TASK-001, TASK-006, and TASK-009 (other schema tasks) are all 3 points. The analytics schema is genuinely more complex given it needs to support real-time queries, historical aggregation, and export generation simultaneously, so 5 is defensible - but worth flagging if a team challenges it in grooming.

**13:29:42 - Features only ("What features should this product have?")**

Single workflow step, correct routing to the `Program Manager` agent. Six feature cards covering all spec capabilities. Content is accurate and well-structured. This is exactly the expected output for this prompt - no issues.

**13:47:56 - User stories only ("What are the user stories for this product?")**

Single workflow step, correct routing to the Product Manager agent, and 45 well-formed Connextra-format stories covering the full spec. A few observations:

**What's working well**

Every capability in the spec has corresponding stories, including all four NFRs as explicit user stories (uptime, 5-second latency, encryption, SOC 2, 50k volume). The IMAP/SMTP, M365, and Google Workspace connections are correctly split into separate stories rather than collapsed into one. The analytics section is the most granular it's been - individual stories for inbox volume, routing decisions, SLA status, volume by category, average response time, escalation rate, CSV export, and PDF export. That level of specificity will produce accurate task cards in the full workflow run.

**One persona inconsistency worth noting**

The spec defines the persona as "Team Leads / Managers" but the stories use "Team Lead or Manager" as a single compound persona. The full workflow run (13:23:42) used "Team Lead" consistently throughout. This inconsistency is harmless at the story level but could cause a subtle routing or matching issue if any downstream agent compares persona names between the story output and the task output. It's worth standardizing - either "Team Lead" or "Team Lead / Manager" throughout, matching whatever the PM agent's knowledge string specifies.

**One missing persona - End Customer**

The spec explicitly lists End Customers as a user who sends emails that are ingested by the system. The 13:23:42 full workflow run generated the story "As an End Customer, I want to send emails with attachments so that I can include supporting information in my message" which contributed to TASK-002's acceptance criteria. That story is absent here. It's a minor gap since End Customers have limited direct interaction with the system, but if the PM agent's knowledge string explicitly lists all spec personas, it should cover this one too. You could add a rule:

   "Cover ALL personas listed in the specification, including passive ones "
   "(e.g. End Customers who interact with the system indirectly). "
   "Write at least one story per persona even if their interaction is limited.\n"

**Overall** - three golden prompts all producing correct output with the right workflow steps and correct agent routing. The suite is validated.

---

### Anthropic Claude Sonnet 4.6 output - latest deliverables from May 19th, 2026

---

### Evaluation context

These three outputs were produced as simulated pipeline runs after all prompt engineering fixes documented in this project were applied. They represent Claude Sonnet 4.6's expected output quality under the corrected pipeline, using the same `sample_requirements.txt` spec used throughout GPT-5.4-mini evaluation.

---

### Output 1 - Development Tasks (`backlog_20260604_164019.md`)

**Workflow steps:** 3 (correct - all three steps extracted, no spec-request step, no collapse)

**Task count:** 24 tasks, 118 story points

**Structural correctness:** All 24 Task ID fields present. Consistent markdown table format throughout. Note field appears on all five 8-point tasks (TASK-004, TASK-006, TASK-008, TASK-009, TASK-013) and is absent on all others. Summary table contains full user story text without shorthand substitution. No content duplication.

**Effort distribution:** Schema tasks uniformly 3 points. Backend tasks range 5–8 points calibrated to complexity - TASK-006 (NLP classification engine, 4 consolidated stories) at 8 points, TASK-011 (SLA monitoring backend) at 5 points, TASK-002 (mailbox API) at 5 points. UI tasks range 3–8 points - TASK-009 (no-code rule builder) correctly at 8 points given drag-and-drop complexity, simpler inline-edit UIs at 3 points. The full Fibonacci range is used, not compressed to a single value.

**Dependency graph:** Fully acyclic. TASK-024 (messaging connectors) has no dependencies and is correctly listed as a dependency of TASK-011 (SLA escalation), resolving the inversion that persisted through multiple GPT runs. TASK-019 (integrations UI) depends on TASK-017, TASK-018, and TASK-024, correctly requiring all three connector types before the unified configuration UI is built.

**Spec coverage:** All six spec capabilities covered. All four NFRs produce dedicated tasks: TASK-020 (availability/uptime), TASK-021 (latency instrumentation), TASK-022 (encryption/SOC 2), TASK-023 (scalability/load testing). NFRs are treated as separate concerns - availability and scalability are not merged.

**Schema layering:** Consistent schema → backend → UI pattern across all five feature areas. Six schema tasks (TASK-001, 005, 007, 010, 013, 016) each correctly positioned as the dependency root for their respective backend tasks. This is the pattern the GPT runs took multiple iterations to produce consistently.

**Acceptance criteria quality:** Quantified against spec values throughout - HTTP status codes, 5-second latency SLO, 25 MB attachment limit, 50,000 emails/day, TLS 1.2+, AES-256, SOC 2 control categories (CC6, CC7, CC9), p95 latency buckets, WCAG 2.1 AA. No generic or untestable criteria present.

**Observations worth noting:** The analytics schema task (TASK-013) introduces materialised views with a 200ms query performance acceptance criterion - this goes beyond what the spec requires and reflects genuine architectural reasoning about query performance at 50,000 emails/day. The load testing task (TASK-023) derives the per-minute throughput (35 emails/minute) from the daily volume spec value and adds a 3× burst scenario - both absent from the spec, both correct engineering practice.

---

### Output 2 - User Stories (`backlog_20260604_164500.md`)

**Workflow steps:** 1 (correct - spec-request step suppressed, single step extracted)

**Story count:** 43 stories across 7 thematic sections

**Format:** All stories follow the Connextra format without exception. Thematic section headers (Email Ingestion, Classification Engine, Routing Rules, Escalation and SLA Management, Analytics Dashboard, Integrations, Non-Functional Requirements, End Customer Experience) provide navigational structure absent from the GPT flat-list output.

**Persona coverage:** All five spec personas covered - IT Administrator, Customer Support Agent, Sales Representative, Team Lead / Manager, End Customer. End Customer stories appear twice: story 6 (attachments, in the Email Ingestion section where it contextually belongs) and story 43 (routing experience, in a dedicated End Customer section). This is the complete persona coverage that was flagged as a gap in the GPT 13:47:56 run.

**NFR stories:** Five dedicated stories (38–42) - one per NFR in the spec - placed in a dedicated Non-Functional Requirements section. This structural decision makes the NFR detection rule in the dev engineer knowledge more reliable because the section label provides an explicit signal.

**Provider granularity:** M365 and Google Workspace split into separate stories (2 and 3) rather than combined. This produces cleaner task card mapping downstream and is consistent with the schema task (TASK-001) which explicitly models them as separate protocol enum values.

**Story quality:** Outcome clauses are outcome-oriented, not feature-descriptive. "So that I can balance ingestion frequency against system resource usage" (story 5) is a genuine business outcome. "So that my CRM stays current without manual data entry" (story 32) directly names the pain being eliminated. No story uses "so that the system does X" - all outcomes are user-valued.

**Comparison to GPT 13:47:56:** 43 stories versus 45. The two GPT stories absent here are the IT Administrator variants of CSV/PDF export - these are correctly assigned to Team Lead only in the Claude output, matching the spec's definition of Team Lead / Manager as the analytics consumer. The Claude output is more persona-accurate on this dimension.

---

### Output 3 - Features (`backlog_20260604_165000.md`)

**Workflow steps:** 1 (correct - spec-request step suppressed, step 2 extracted only)

**Feature count:** 7 features versus GPT's 6

**The seventh feature - Secure and Scalable Platform Foundation** - is the primary structural difference. The GPT features run omitted the NFRs entirely. This feature groups all five NFR user stories (availability, latency, encryption, SOC 2, scalability) into a single named capability with a key functionality list that includes quantified values directly from the spec (99.9% uptime, 5 seconds, AES-256, TLS 1.2+, 50,000 emails/day). This gives a decision-maker or architect reading the features document a complete picture of the product's non-functional commitments at a glance.

**Related user stories included per feature:** Each feature card contains the full Connextra-format stories that belong to it. The GPT features run listed stories as brief bullet labels. The Claude output is self-contained - a product manager can use this document as the sole input to a user story mapping session without cross-referencing a separate stories document.

**Feature descriptions:** Written at two levels simultaneously - what the feature does and why it matters to the user. "Reduces misrouting and manual triage by ensuring every email is categorised accurately before it reaches a team, with a safety net for uncertain cases that prevents classification errors from becoming routing errors" (Intelligent Email Classification user benefit) is more precise than the GPT equivalent and directly addresses the problem the feature solves.

**Feature naming:** More technically specific than GPT - "Configurable Routing Rules Engine" versus GPT's "Rule-Based Email Routing"; "Multi-Source Email Ingestion" versus GPT's "Email Ingestion and Mailbox Connectivity". The Claude naming reflects the architecture more accurately and is more useful as a capability label in a roadmap or release note.

---

### Summary comparison - Claude Sonnet 4.6 vs GPT-5.4-mini (final runs)

| Dimension | Claude Sonnet 4.6 | GPT-5.4-mini (27 May, best run) |
| :--- | :--- | :--- |
| Development tasks | 24 tasks / 118 pts | 36 tasks / 163 pts |
| Schema layering | Consistent across all features | Consistent across all features |
| NFR task coverage | 4 dedicated tasks | 4 dedicated tasks |
| Dependency graph accuracy | Fully correct, no inversions | One forward reference (TASK-032→TASK-013) |
| Effort calibration | Full Fibonacci range used | Full Fibonacci range used |
| User stories | 43, thematic sections, all personas | 45, flat list, all personas |
| NFR stories | Dedicated section | Embedded in general persona group |
| Features | 7 (includes NFR feature) | 6 (NFRs omitted) |
| Related stories in features | Full Connextra format per feature | Brief bullet labels |
| Workflow step accuracy | Correct across all three prompts | Correct across all three prompts |
| Content duplication | None | None |

**Key qualitative differences:** Claude produces fewer tasks but at higher description density - each task card contains more architectural reasoning, more quantified acceptance criteria, and more explicit schema field definitions than the GPT equivalents. GPT produces more tasks through finer story-level granularity (e.g. separate Salesforce and HubSpot connector tasks vs Claude's combined CRM connector task). Neither approach is objectively better - finer granularity is preferable for large teams with dedicated engineers per integration; higher density is preferable for smaller teams where one engineer owns an entire connector layer. Both outputs are production-quality sprint backlogs for the spec provided.

---

> Candidate note: unfortunately, I ran out of credits on the Anthropic API used along this project, and to execute the latest full cycle of golden prompts with Claude Sonnet 4.6 (June 4th, 2026) I needed to rely on its Web UI "simulating" the pipeline/workflow. I'll get back to this as soon as I add some credits to my personal account and will get the output artifacts and project documentation updated accordingly.

---

### Running the tests

```bash
pytest tests/ -v
```

Tests use `unittest.mock.patch` to replace all OpenAI API calls, so they run
without a live API key. The key behavioral tests are:

- `test_corrected_prompt_fed_back_not_original` - verifies Bug 1 is fixed
- `test_routes_to_highest_similarity_agent` - verifies router logic
- `test_run_returns_expected_keys` - integration smoke test

The test results can be seen below:

```bash
(.venv) PS C:\accenture\smart-backlog-assistant> pytest .\tests\ -v
=================================================== test session starts ====================================================
platform win32 -- Python 3.14.4, pytest-9.0.3, pluggy-1.6.0 -- C:\accenture\3\smart-backlog-assistant\.venv\Scripts\python.exe
cachedir: .pytest_cache
rootdir: C:\accenture\smart-backlog-assistant
plugins: anyio-4.13.0
collected 29 items                                                                                                          

tests/test_processor.py::TestKnowledgeAugmentedPromptAgent::test_respond_returns_client_output PASSED                 [  3%]
tests/test_processor.py::TestKnowledgeAugmentedPromptAgent::test_respond_returns_empty_string_on_exception PASSED     [  6%]
tests/test_processor.py::TestActionPlanningAgent::test_extracts_steps_as_list PASSED                                  [ 10%]
tests/test_processor.py::TestActionPlanningAgent::test_filters_blank_lines PASSED                                     [ 13%]
tests/test_processor.py::TestActionPlanningAgent::test_knowledge_passed_in_system_prompt PASSED                       [ 17%]
tests/test_processor.py::TestActionPlanningAgent::test_returns_empty_list_on_exception PASSED                         [ 20%]
tests/test_processor.py::TestEvaluationAgent::test_corrected_prompt_fed_back_not_original PASSED                      [ 24%]
tests/test_processor.py::TestEvaluationAgent::test_loops_on_no_then_passes PASSED                                     [ 27%]
tests/test_processor.py::TestEvaluationAgent::test_passes_on_first_yes PASSED                                         [ 31%]
tests/test_processor.py::TestEvaluationAgent::test_uses_client_complete_not_sdk_directly PASSED                       [ 34%]
tests/test_processor.py::TestRoutingAgent::test_returns_error_message_when_embed_fails PASSED                         [ 37%]
tests/test_processor.py::TestRoutingAgent::test_routes_to_highest_similarity_agent PASSED                             [ 41%]
tests/test_processor.py::TestAIClient::test_aiclient_complete_routes_to_anthropic PASSED                              [ 44%]
tests/test_processor.py::TestAIClient::test_aiclient_complete_routes_to_openai PASSED                                 [ 48%]
tests/test_processor.py::TestAIClient::test_aiclient_embed_returns_empty_without_embedding_client PASSED              [ 51%]
tests/test_processor.py::TestAIClient::test_aiclient_embed_uses_embedding_client PASSED                               [ 55%]
tests/test_processor.py::TestAIClient::test_build_client_openai PASSED                                                [ 58%]
tests/test_processor.py::TestAIClient::test_build_client_raises_without_key PASSED                                    [ 62%]
tests/test_processor.py::TestDocumentLoader::test_load_txt PASSED                                                     [ 65%]
tests/test_processor.py::TestDocumentLoader::test_raises_on_missing_file PASSED                                       [ 68%]
tests/test_processor.py::TestDocumentLoader::test_raises_on_unsupported_format PASSED                                 [ 72%]
tests/test_processor.py::TestBacklogLoader::test_format_backlog_for_context PASSED                                    [ 75%]
tests/test_processor.py::TestBacklogLoader::test_format_empty_backlog_returns_empty_string PASSED                     [ 79%]
tests/test_processor.py::TestBacklogLoader::test_load_valid_backlog PASSED                                            [ 82%]
tests/test_processor.py::TestBacklogLoader::test_returns_empty_list_for_missing_file PASSED                           [ 86%]
tests/test_processor.py::TestFormatter::test_build_markdown_contains_steps PASSED                                     [ 89%]
tests/test_processor.py::TestFormatter::test_build_markdown_handles_empty_result PASSED                               [ 93%]
tests/test_processor.py::TestBacklogProcessorIntegration::test_processor_logs_provider_and_model PASSED               [ 96%]
tests/test_processor.py::TestBacklogProcessorIntegration::test_run_returns_expected_keys PASSED                       [100%]

==================================================== 29 passed in 0.65s ====================================================
(.venv) PS C:\accenture\smart-backlog-assistant> 
```

---

## 6. Setup and Running

### Prerequisites

- Python 3.13+
- An OpenAI and/or an Anthropic API key (or Vocareum key starting with "voc")

> Note: An OpenAI key is still required even when the provider is set as `anthropic`. The reason for it is that Anthropic doesn't provide an embedding model for cosine similarity analysis.

### Installation

```bash
python -m venv .venv
source .venv/bin/activate     # Windows: .venv\Scripts\activate
pip install -r requirements.txt
cp .env.example .env
# Edit .env and add your OPENAI_API_KEY
```

### Usage

```bash
# Full workflow (stories → features → tasks)
python main.py --spec inputs/sample_requirements.txt

# Ask only for user stories
python main.py --spec inputs/sample_requirements.txt \
               --prompt "What are the user stories for this product?"

# Include existing backlog for context
python main.py --spec inputs/sample_requirements.txt \
               --backlog inputs/sample_backlog.json

# Use meeting notes as the spec
python main.py --spec inputs/sample_meeting_notes.txt
```

Output is written to `outputs/backlog_<timestamp>.md`.

---

## 7. Reflection

### What worked well

- **Checklist evaluation criteria** significantly reduced the number ofg
  evaluation iterations needed. Most outputs pass on iteration 2 or 3.

- **Role-semantic routing descriptions** made the router reliable. Before
  the fix, routing was essentially random; after the fix, routing correctly
  matched the step text in all manual test runs.

- **Negative persona constraints** ("You do not define features or tasks")
  cleanly separated agent concerns without needing complex orchestration logic.

- **Injecting the product spec into knowledge (not the user prompt)** ensured
  the the agents always had grounding context regardless of how the step was
  phrased.

### What I would improve

1. **RAG over large specs** - For specs longer than ~3,000 words/tokens, the
   `KnowledgeAugmentedPromptAgent` injects the entire spec into the context,
   which is expensive and may exceed the model's context window. A
   `RAGKnowledgePromptAgent` that retrieves only the relevant spec sections
   would be more scalable.

2. **Parallel step execution** - Steps are currently executed sequentially.
   The PM and ProgMgr agents could potentially run in parallel since the
   ProgMgr can generate features independently of PM stories (it receives the
   step text, not the PM output directly).

3. **Structured output (JSON mode)** - Using OpenAI's `response_format:
   json_object` instead of free-text criteria checking would make evaluation
   deterministic and eliminate most false "No" verdicts caused by cosmetic
   formatting differences.

4. **Anthropic Claude output quality** - While provider switching works correctly,
   output quality between providers differs. Claude Sonnet 4.6's initial runs
   showed session state contamination from `session.db` causing refusal text to
   surface as section headings. Prompt-level fixes (suppressing refusals in the
   persona, adding deduplication guards) partially addressed this, but the Claude
   output hasn't been iterated to the same level as `gpt-5.4-mini`. A dedicated
   iteration pass on the Claude outputs will be the next step.

5. **Streaming output** - For large specs the user sees nothing until the
   full workflow completes (~2-3 minutes). Streaming intermediate step
   outputs would improve perceived responsiveness. Ideally, there would be
   a Web ChatBot interface that users could interact with.

### API costs

Below is a breakdown of the whole cost of this project - for both the development and fine-tunning/testing phases - based on the API keys used:

| Provider | Development phase | Testing Phase | Total |
| :--- | :--- | :--- | :--- |
| Open AI | US$ 5.00 | US$ 0.22 | US$ 5.22 |
| Anthropic | US$ 15.00 | US$ 0.38* | US$ 15.00 |

> A full golden prompt testing cycle wasn't possible for Claude Sonnet 4.6 due to the lack of balance for the API key I've been using throughout this project.

The cost to run a full cycle (features + user stories + development tasks) for a product specification with a length of ~2,600 words/tokens has been **measured** at **US$ 0.22** for OpenAI [gpt-5.4-mini](https://developers.openai.com/api/docs/models/gpt-5.4-mini) and **estimated** at **US$ 0.36** for Anthropic [claude-sonnet-4-6](https://www.anthropic.com/news/claude-sonnet-4-6), roughly 1.6× more expensive for a higher-density, architecturally richer output.

Claude's **cost** analysis/breakdown can be found in the [Cost Analysis](/docs/COST_ANALYSIS.md) document.

### Savings

Claude also helped me drafting a **savings** analysis that can be found in the [Savings Analysis](/docs/SAVINGS_ANALYSIS.md) document. Below is the summary table; the full details can be found in the aformentioned document.

#### Summary table

| Metric | Value |
| :--- | :--- |
| Manual hours per week | ~39.0 hrs |
| AI-assisted hours per week | ~2.2 hrs |
| Hours saved per week | ~36.8 hrs |
| Hours saved per year (48 weeks) | **~1,767 hrs** |
| Gross annual saving (@ $135/hr) | **$238,545** |
| Annual API cost (GPT-5.4-mini) | $63 |
| Annual API cost (Claude Sonnet 4.6) | $104 |
| **Net annual saving** | **~$238,480** |
| ROI on API spend | **~3,770×** |
