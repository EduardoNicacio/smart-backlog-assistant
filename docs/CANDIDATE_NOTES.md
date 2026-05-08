# Candidate Notes - Smart Backlog Assistant

Use this file to document your work as you go.
Assessors will read this alongside your code.

---

## 1. Problem Statement

> Describe the problem you are solving in your own words.
> What makes this hard? What does "good" look like?

_[Your response here]_

**Use cases I'm targeting:**

1. _[Use case 1, e.g. "Engineering lead processes weekly planning meeting notes"]_
2. _[Use case 2, e.g. "PM uploads a requirements doc and shares backlog output with team"]_
3. _[Use case 3, optional]_

---

## 2. Architecture & Design

> Describe how your solution is structured. What are the main components
> and how does data flow through them?

_[Your response here]_

**Architecture diagram:**
_(A simple ASCII diagram or description is fine)_

```txt
[Input Document] → [Document Loader] → [Processor + AI] → [Formatter] → [Output JSON]
                                           ↑
                                   [Existing Backlog]
```

**Key design decisions I made:**

- _[e.g. "I used a single-prompt approach rather than chaining because..."]_
- _[e.g. "I chose JSON output format because..."]_

---

## 3. Prompt Engineering Log

> Document your prompt iterations here. This is one of the most important
> sections for assessors - show your thinking process.

### Version 1 (initial)

**Prompt:**

```txt
[Paste your initial prompt here]
```

**What worked:**

- _..._

**What didn't work:**

- _..._

### Version 2

**What I changed:**

- _..._

**Why:**

- _..._

**Prompt:**

```txt
[Paste updated prompt here]
```

### Final version

**What I settled on and why:**
_..._

---

## 4. Testing

### Sample Input 1: `inputs/sample_meeting_notes.txt`

**What I expected:**

- 5–7 user stories covering SSO, invoices, live chat, and notifications
- Priority "High" for SSO and invoice stories
- At least one open question about mobile app vs responsive web

**What I got:**
_[Paste or summarise actual output]_

**Assessment:**
_[Did it match expectations? What surprised you?]_

---

### Sample Input 2: `inputs/sample_requirements.txt`

**What I expected:**
_..._

**What I got:**
_..._

---

### Sample Input 3 (your own)

> Create a third sample input that tests an edge case or a different scenario.

**Input file:** `inputs/your_sample_3.txt`

**Scenario:** _..._

**What I expected:** _..._

**What I got:** _..._

---

## 5. AI Tools Used During Development

> Describe how you used AI tools (including this tool itself) during the project.
> This is optional but encouraged and viewed positively by assessors.

| Stage | Tool Used | How I Used It |
| :---: | :---: | :---: |
| Problem definition | | |
| Architecture design | | |
| Prompt engineering | | |
| Code writing | | |
| Testing / debugging | | |

---

## 6. Reflection

### What worked well

_..._

### What I'd improve with more time

_..._

### What I learned

_..._

---

## 7. How to Run My Solution

> If you've changed anything from the base scaffold, document it here.

```bash
# Setup
pip install -r requirements.txt
cp .env.example .env
# Add your API key to .env

# Run
python main.py --input inputs/sample_meeting_notes.txt

# Test
pytest tests/ -v
```

Any non-obvious setup steps:
_..._
