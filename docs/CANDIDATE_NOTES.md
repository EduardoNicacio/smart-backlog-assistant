# Candidate Notes - Smart Backlog Assistant

```md
## RDE Certification - Capstone Project Documentation
## Candidate: Eduardo Nicacio [eduardo.nicacio@accenture.com]
## Date: May 19th, 2026
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

```txt
"A full development plan for a product is produced in three ordered steps:"
"1. Define user stories from the product specification - ..."
"2. Define features by grouping related stories into ..."
"3. Define development tasks - for each user story, list..."
"IMPORTANT: Extract ONLY the steps that are explicitly requested in the prompt. "
"If the prompt asks only for user stories, return only step 1. "
"If the prompt asks only for features, return only step 2. "
"If the prompt asks for development tasks or a full plan, return all three steps in order."
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
single response, which then failed the evaluation criteria.  Explicit
exclusions proved more reliable than relying on the evaluation loop to
correct mixed output.

### 3.3 KnowledgeAugmentedPromptAgent - knowledge strings

The product spec is embedded in the PM agent's knowledge string:

```python
knowledge_product_manager = (
   "User stories are defined by writing sentences that describe a persona, "
   "an action, and a desired outcome.\n"
   "Every story MUST start with: 'As a'\n"
   "Write stories that cover all the personas who interact with this product.\n"
   "Each story should represent one specific piece of functionality.\n\n"
   f"Product specification:\n{spec}"
)
```

**Why**: Injecting the spec directly into the knowledge string (rather than
the user prompt) ensures it is always present in the system message, not the
user turn. The model respects system-level knowledge more consistently than
user-turn content for grounding purposes.

**The Program Manager and Dev Engineer agents do NOT receive the spec**
because they operate downstream of the PM output. Their inputs are the
step text (which references the stories/features already generated), so
re-injecting the spec would cause redundancy and potential contradiction.

### 3.4 EvaluationAgent - criteria strings

Criteria are written as checklists, not prose:

```python
criteria_pm = (
   "The answer should consist exclusively of user stories that follow this exact structure:\n"
   "  As a [type of user], I want [an action or feature] so that [benefit/value].\n\n"
   "Each story must be:\n"
   "  - Clear and concise\n"
   "  - Focused on a single, specific user need\n"
   "  - Free of technical implementation details\n"
   "  - Written from the user's perspective, not the system's"
)
```

**Why**: The evaluator's `eval_prompt` asks "Does the answer meet this
criteria? Respond Yes or No". A checklist-style criteria string makes
Yes/No assessment unambiguous. Prose criteria produced vague evaluations
like "Mostly yes, but..." which the `evaluation.lower().startswith("yes")`
check failed to parse correctly.

### 3.5 RoutingAgent - description strings

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
| 1 | `"What would the development tasks for this product be?"` | PM → ProgMgr → DevEng | All three artifact types |
| 2 | `"What are the user stories for this product?"` | PM only | Connextra-format stories |
| 3 | `"What features should this product have?"` | ProgMgr only | Feature cards with 4 fields |

---

### Golden prompt results

---

#### Model: Open AI gpt-5.4-mini

---

```bash
# Executes the whole workflow with the default prompt, i.e., "What would the development tasks for this product be?"
python .\main.py --spec .\inputs\sample_requirements.txt
```

Attachment: [outputs/openai/gpt-5.4-mini/backlog_20260522_113715.md](/outputs/openai/gpt-5.4-mini/backlog_20260522_113715.md)

```bash
# Should return user stories only
python .\main.py --spec .\inputs\sample_requirements.txt --prompt "What are the user stories for this product?"
```

Attachment: [outputs/openai/gpt-5.4-mini/backlog_20260522_114018.md](/outputs/openai/gpt-5.4-mini/backlog_20260522_114018.md)

```bash
# Executes the whole workflow with the default prompt, generating only user stories, features and dev tasks that don't exist in the backlog
python .\main.py --spec .\inputs\sample_requirements.txt --backlog .\inputs\sample_backlog.json
```

Attachment: [outputs/openai/gpt-5.4-mini/backlog_20260522_114623.md](/outputs/openai/gpt-5.4-mini/backlog_20260522_114623.md)

---

#### Model: Anthropic claude-sonnet-4-6

---

```bash
# Executes the whole workflow with the default prompt, i.e., "What would the development tasks for this product be?"
python .\main.py --spec .\inputs\sample_requirements.txt
```

Attachment: [outputs/anthropic/claude-sonnet-4-6/backlog_20260519_094334.md](/outputs/anthropic/claude-sonnet-4-6/backlog_20260519_094334.md)

```bash
# Should return user stories only
python .\main.py --spec .\inputs\sample_requirements.txt --prompt "What are the user stories for this product?"
```

Attachment: [outputs/anthropic/claude-sonnet-4-6/backlog_20260519_094742.md](/outputs/anthropic/claude-sonnet-4-6/backlog_20260519_094742.md)

```bash
# Executes the whole workflow with the default prompt, generating only user stories, features and dev tasks that don't exist in the backlog
python .\main.py --spec .\inputs\sample_requirements.txt --backlog .\inputs\sample_backlog.json
```

Attachment: [outputs/anthropic/claude-sonnet-4-6/backlog_20260519_101538.md](/outputs/anthropic/claude-sonnet-4-6/backlog_20260519_101538.md)

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

- **Checklist evaluation criteria** significantly reduced the number of
  evaluation iterations needed. Most outputs pass on iteration 1 or 2.

- **Role-semantic routing descriptions** made the router reliable. Before
  the fix, routing was essentially random; after the fix, routing correctly
  matched the step text in all manual test runs.

- **Negative persona constraints** ("You do not define features or tasks")
  cleanly separated agent concerns without needing complex orchestration logic.

- **Injecting the product spec into knowledge (not the user prompt)** ensured
  the PM agent always had grounding context regardless of how the step was
  phrased.

### What I would improve

1. **RAG over large specs** - For specs longer than ~3,000 tokens, the
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

4. **Anthropic Claude support** - The `ai_client.py` abstraction is in place
   but the agent classes are coupled to the OpenAI SDK. Refactoring agents to
   call through `ai_client.py` would allow switching providers without code
   changes.

5. **Streaming output** - For large specs the user sees nothing until the
   full workflow completes (~2-3 minutes). Streaming intermediate step
   outputs would improve perceived responsiveness.
