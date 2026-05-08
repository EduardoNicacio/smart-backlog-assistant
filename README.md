# Smart Backlog Assistant 🧠

A CLI tool that processes meeting notes or requirements documents and generates structured engineering backlog items using AI.

[placeholder]

---

## What It Does

1. **Reads** a meeting notes file (`.txt`) or requirements document (`.pdf`)
2. **Optionally loads** an existing backlog (`.json`) for context
3. **Calls an AI API** (Anthropic Claude or OpenAI GPT - your choice)
4. **Outputs** structured backlog items including:
   - Key requirements identified
   - User stories with acceptance criteria (Given/When/Then)
   - Priority and complexity estimates
   - Flagged duplicates with existing backlog
   - Open questions / ambiguities

---

## Project Structure

```txt
smart-backlog-assistant/
├── main.py                         # Entry point - CLI argument handling
├── src/
│   ├── ai_client.py                # AI provider abstraction (Anthropic + OpenAI)
│   ├── processor.py                # Core logic + PROMPT ENGINEERING lives here
│   ├── document_loader.py          # Loads .txt and .pdf files
│   ├── backlog_loader.py           # Loads existing backlog JSON
│   └── formatter.py                # Formats final output
├── inputs/
│   ├── sample_meeting_notes.txt    # Sample input 1
│   ├── sample_requirements.txt     # Sample input 2
│   └── sample_backlog.json         # Sample existing backlog
├── outputs/                        # Generated results land here
├── tests/
│   └── test_processor.py           # Unit tests (run with pytest)
├── docs/
│   └── CANDIDATE_NOTES.md          # Candidate notes througout the development of this project
├── requirements.txt                # Required Python packages and libraries
└── .env.example                    # Example for the final .env file
```

---

## Quick Start

### 1. Clone and set up

```bash
# Create a virtual environment (recommended)
python -m venv venv
source venv/bin/activate      # macOS/Linux
# venv\Scripts\activate       # Windows

# Install dependencies
pip install -r requirements.txt
```

### 2. Configure your API key

```bash
cp .env.example .env
# Edit .env and add your ANTHROPIC_API_KEY or OPENAI_API_KEY
```

### 3. Run the tool

```bash
# Basic run with sample meeting notes
python main.py --input inputs/sample_meeting_notes.txt

# With existing backlog for context
python main.py --input inputs/sample_meeting_notes.txt \
               --backlog inputs/sample_backlog.json

# Specify output file
python main.py --input inputs/sample_requirements.txt \
               --output outputs/pipeline_backlog.json

# Force a specific AI provider
python main.py --input inputs/sample_meeting_notes.txt --provider openai

# Verbose logging (useful for debugging prompts)
python main.py --input inputs/sample_meeting_notes.txt --verbose
```

### 4. Run the tests

```bash
pytest tests/ -v

# With coverage report
pytest tests/ -v --cov=src
```

---

## Sample Output

```json
{
  "metadata": {
    "generated_at": "2024-01-15T10:30:00Z",
    "version": "1.0.0"
  },
  "summary": "The document describes requirements for replacing a legacy customer portal...",
  "requirements": [
    {
      "id": "REQ-001",
      "description": "Support SSO via Google and Microsoft for enterprise customers",
      "source": "Marcus wants SSO via Google and Microsoft for enterprise customers"
    }
  ],
  "user_stories": [
    {
      "id": "US-001",
      "title": "Enterprise user logs in via SSO",
      "as_a": "enterprise customer",
      "i_want": "to log in using my company Google or Microsoft account",
      "so_that": "I don't need a separate password to manage",
      "acceptance_criteria": [
        "Given I am on the login page, When I click Sign in with Google, Then I am redirected to Google OAuth",
        "Given I complete OAuth, When I am redirected back, Then I am logged in to my account"
      ],
      "priority": "High",
      "category": "Feature",
      "estimated_complexity": "M",
      "notes": "Requires SAML vs OAuth spike - see action items"
    }
  ],
  "open_questions": [
    "Does SSO apply to all tiers or enterprise-only?"
  ]
}
```

---

## Where to Focus Your Energy

The scaffold is intentionally bare in places. Here are the highest-value areas
to improve for the assessment:

### 🔴 High Impact

- **`src/processor.py`** - Improve the prompts. Try chain-of-thought, few-shot
  examples, or breaking the task into multiple AI calls.
- **Prompt iteration** - Document your prompt versions and what changed.

### 🟡 Medium Impact

- **Error handling** - What happens with a corrupted PDF? A 10,000-word doc?
- **Output quality checks** - Validate the AI output before writing it.
- **Retry logic** - If the AI returns malformed JSON, prompt it to try again.

### 🟢 Nice to Have

- **New input formats** - Add `.docx` support, or accept a URL.
- **New output formats** - Generate a Markdown report alongside the JSON.
- **Streaming** - Show output progressively rather than waiting for full response.
- **Integration** - Push stories directly to a Jira/Linear/GitHub project.

---

## Evaluation Checklist

Before submitting, verify:

- [ ] `python main.py --input inputs/sample_meeting_notes.txt` runs successfully
- [ ] `pytest tests/` passes all tests
- [ ] Output JSON contains at least 3 user stories with acceptance criteria
- [ ] Your `.env.example` is committed (never commit your actual `.env`)
- [ ] You've documented your prompt iterations in `docs/CANDIDATE_NOTES.md`
- [ ] Code has comments explaining non-obvious decisions

---

## Notes on AI Usage

This capstone project uses the Anthropic and OpenAI Python SDKs directly.
See `src/ai_client.py` for implementation details.

- **Anthropic docs**: <https://docs.anthropic.com>
- **OpenAI docs**: <https://platform.openai.com/docs>
- **Prompt engineering guide**: <https://docs.anthropic.com/en/docs/build-with-claude/prompt-engineering/overview>
