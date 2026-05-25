# Smart Backlog Assistant

An AI-powered tool that converts a product specification document into a
structured development backlog - user stories, product features, and
engineering tasks - using a multi-agent workflow built on OpenAI's
and Anthropic's API.

---

## Project Structure

```txt
smart-backlog-assistant/
├── main.py                         # Entry point - CLI argument handling
├── agents/
│   ├── __init__.py
│   └── base_agents.py              # Agent class library (DirectPromptAgent,
│                                   # KnowledgeAugmentedPromptAgent,
│                                   # EvaluationAgent, RoutingAgent,
│                                   # ActionPlanningAgent, RAGKnowledgePromptAgent)
├── src/
│   ├── __init__.py
│   ├── ai_client.py                # AI provider abstraction (OpenAI + Anthropic)
│   ├── processor.py                # Multi-agent orchestration + ALL prompt engineering
│   ├── document_loader.py          # Loads .txt, .md and .pdf files
│   ├── backlog_loader.py           # Loads existing backlog in JSON format for context
│   └── formatter.py                # Formats and saves Markdown output
├── inputs/
│   ├── sample_requirements.txt     # Golden test input 1 - Email Router Service spec
│   ├── sample_meeting_notes.txt    # Golden test input 2 - Knowledge Base Assistant notes
│   └── sample_backlog.json         # Existing backlog for incremental enrichment test
├── outputs/                        # Generated backlog Markdown files land here
├── tests/
│   └── test_processor.py           # Unit tests (run with pytest, no API key needed)
├── docs/
│   └── CANDIDATE_NOTES.md          # Architecture, prompt engineering decisions, bug fixes
├── requirements.txt
└── .env.example
```

---

## Quick Start

In a terminal, clone this repository from GitHub:

```bash
git clone --recursive https://github.com/EduardoNicacio/smart-backlog-assistant.git
cd smart-backlog-assistant/
```

### Prerequisites

- Python 3.13

```bash
python -m venv .venv
source .venv/bin/activate       # Windows: .venv\Scripts\activate
```

### Install dependencies

```bash
pip install -r requirements.txt
```

### Configure environment variables

```bash
cp .env.example .env
```

### Open .env and set your API key(s)

```txt
...
AI_PROVIDER=openai
...
OPENAI_API_KEY="voc-00000000000000000000000000000000abcd.12345678"
OPENAI_BASE_MODEL="gpt-5.4-mini"
OPENAI_EMBEDDING_MODEL="text-embedding-3-small"
OPENAI_BASE_URL="https://openai.vocareum.com/v1"
...
ANTHROPIC_API_KEY="voc-00000000000000000000000000000000abcd.12345678"
ANTHROPIC_BASE_MODEL="claude-sonnet-4-6"
ANTHROPIC_BASE_URL="https://claude.vocareum.com"
...
```

### Run

```bash
# Full workflow - user stories → features → development tasks
python main.py --spec inputs/sample_requirements.txt

# Ask only for user stories
python main.py --spec inputs/sample_requirements.txt --prompt "What are the user stories for this product?"

# Use meeting notes as input
python main.py --spec inputs/sample_meeting_notes.txt

# Include an existing backlog to avoid duplicates
python main.py --spec inputs/sample_requirements.txt --backlog inputs/sample_backlog.json

# All options
python main.py --help
```

Output is written to `outputs/backlog_<timestamp>.md`.

### Run the tests

```bash
pytest tests/ -v
```

Tests mock all API calls - no API key required.

---

## How It Works

### Workflow overview

```txt
User prompt
    │
    ▼
ActionPlanningAgent ──── extracts ordered steps (stories → features → tasks)
    │
    ▼
RoutingAgent ──── cosine-similarity routing over step embeddings
    │
    ├──► PM support     ──► KnowledgeAugmentedPromptAgent + EvaluationAgent
    ├──► ProgMgr support──► KnowledgeAugmentedPromptAgent + EvaluationAgent
    └──► DevEng support ──► KnowledgeAugmentedPromptAgent + EvaluationAgent
                                          │
                                          ▼
                               Validated output → formatter → outputs/
```

### Agent roles

| Agent | Responsibility |
| :--- | :--- |
| `ActionPlanningAgent` | Parses the workflow prompt into an ordered step list |
| `RoutingAgent` | Selects the right agent for each step via embedding similarity |
| `KnowledgeAugmentedPromptAgent` (PM) | Generates Connextra-format user stories grounded in the product spec |
| `KnowledgeAugmentedPromptAgent` (ProgMgr) | Groups stories into named feature cards |
| `KnowledgeAugmentedPromptAgent` (DevEng) | Generates Jira-style development tasks |
| `EvaluationAgent` (×3) | Runs a generate-evaluate-correct loop on each agent's output |

---

## Architecture Diagram

```txt
┌─────────────────────────────────────────────────────────────────┐
│  main.py                                                        │
│   ├── document_loader  →  reads .txt / .pdf spec                │
│   ├── backlog_loader   →  reads existing backlog JSON           │
│   └── BacklogProcessor (src/processor.py)                       │
│         ├── ActionPlanningAgent                                 │
│         │     └── gpt-5.4-mini: extract steps from prompt       │
│         │                                                       │
│         └── RoutingAgent                                        │
│               │  text-embedding-3-small: cosine similarity      │
│               │                                                 │
│               ├── _pm_support → EvaluationAgent                 │
│               │     ├── KnowledgeAugmentedPromptAgent (PM)      │
│               │     │     gpt-5.4-mini: write user stories      │
│               │     └── gpt-5.4-mini: evaluate + correct        │
│               │                                                 │
│               ├── _prog_support → EvaluationAgent               │
│               │     ├── KnowledgeAugmentedPromptAgent (Prog)    │
│               │     └── gpt-5.4-mini: evaluate + correct        │
│               │                                                 │
│               └── _dev_support → EvaluationAgent                │
│                     ├── KnowledgeAugmentedPromptAgent (Dev)     │
│                     └── gpt-5.4-mini: evaluate + correct        │
│                                                                 │
│   └── formatter  →  writes Markdown to outputs/                 │
└─────────────────────────────────────────────────────────────────┘
```

---

## Prompt Engineering

All prompt engineering is in `src/processor.py`.  Key decisions:

**Persona strings** name the role and its explicit boundary:
> *"You are a Product Manager. Your sole responsibility is to define user
> stories for a product. You do not define features or tasks."*

Negative constraints ("You do not define…") prevent agents from generating
mixed output that fails evaluation.

**Knowledge strings** embed the product spec in the system message (not the
user turn) for grounding, and include the exact output format required:
> *"Every story MUST start with: 'As a'"*

**Evaluation criteria** are written as checklists rather than prose, making
Yes/No assessment unambiguous for the evaluator model.

**Routing descriptions** use role-semantic vocabulary matching the step text
("Connextra format", "user stories", "As a … I want … so that") rather than
infrastructure language ("Routes to the support function"), which embeds in a
completely different semantic space and causes mis-routing.

Full rationale for every prompt decision is in `docs/CANDIDATE_NOTES.md`.

---

## Test Inputs and Expected Outputs

### Golden prompt 1 - Full workflow

```bash
python main.py --spec inputs/sample_requirements.txt
# Prompt: "What would the development tasks for this product be?"
```

**Expected output:** Three sections - user stories in Connextra format,
feature cards with Name/Description/Key Functionality/User Benefit, and
development tasks with Task ID/Title/Story/Description/AC/Effort/Dependencies.

### Golden prompt 2 - User stories only

```bash
python main.py --spec inputs/sample_requirements.txt --prompt "What are the user stories for this product?"
```

**Expected output:** Only user stories section; RoutingAgent routes the
single step to the Product Manager agent.

### Golden prompt 3 - With existing backlog

```bash
python main.py --spec inputs/sample_requirements.txt --backlog inputs/sample_backlog.json
```

**Expected output:** Full workflow output; existing items from
`sample_backlog.json` are noted in the spec context so agents can avoid
duplicating already-completed work.

---

## Bug Fixes vs. Original Code

Two bugs were identified and fixed in `agents/base_agents.py` and the
orchestration layer.  See `docs/CANDIDATE_NOTES.md` Section 4 for details.

**Bug 1 - EvaluationAgent correction loop:** The original code passed the
original prompt to the worker on every iteration, so corrections were
generated but never applied.  Fixed by tracking `prompt_to_evaluate`
separately and feeding the corrected prompt back into the worker.

**Bug 2 - Redundant `respond()` call:** Support functions called the
knowledge agent directly, then `evaluate()` called it again - the first
response was wasted.  Fixed by passing the query directly to `evaluate()`.

**Bug 3 - Router description language:** Infrastructure-style descriptions
("Routes to the … support function") embed poorly against domain step text.
Fixed by using role-semantic vocabulary.

---

## AI Usage Throughout Development

- Problem scoping - Claude Sonnet used to critique the problem statement and
  identify the right scope boundary.
- Prompt iteration - gpt-5.4-mini outputs were manually reviewed across 5+
  runs; evaluation criteria were tightened based on failure modes observed.
- Test case generation - Claude Sonnet helped draft the unit test structure
  and identify the key behavioral assertions.

---

## Requirements

See `requirements.txt`. Core dependencies:

| Package | Purpose |
| :--- | :--- |
| `openai` | OpenAI API client (chat completions + embeddings) |
| `anthropic` | Anthropic API client (chat completions) |
| `python-dotenv` | Load `.env` file |
| `numpy` | Cosine similarity computation |
| `pandas` | RAG chunk/embedding storage |
| `pypdf` | PDF text extraction |
| `pytest` | Test runner |

---

> **Candidate note**: [Anthropic](https://platform.claude.com/docs/en/build-with-claude/embeddings) does not have its own native embeddings model. Instead of developing first-party embeddings, Anthropic officially partners with and recommends Voyage AI.

### Recommended Alternatives

While Voyage AI is the preferred partner, developers commonly use a few different options for generating text embeddings to feed into Anthropic-powered retrieval-augmented generation (RAG) pipelines:

- **Voyage AI**: Anthropic’s official partner. They offer state-of-the-art, customizable embeddings for general use, as well as domain-specific models for finance and healthcare.
- **OpenAI**: Widely used and highly accessible (e.g., text-embedding-3-large or text-embedding-3-small).
- **Cohere**: Another popular industry standard for high-quality semantic search.
