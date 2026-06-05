# Savings analysis

## Constraints

- Resource: Business Analyst (BA)
- 2 requirements/meeting notes processed per week
- 48 weeks of work per year
- 5 minutes, on average, to run the full workflow (user stories, features, and dev tasks)
- 2 hours spent, per week, reviewing the workflow outputs and making the necessary adjustments
- Hourly rate estimated at US$ 135.00

## Step 1 - Baseline: how long would a BA spend doing this manually?

Industry benchmarks for BA documentation work put structured requirement writing at roughly 30–45 minutes per user story when starting from raw meeting notes or a requirements document - that includes interpreting the source, writing the story, defining acceptance criteria, and reviewing. Features and dev tasks take proportionally longer due to grouping and technical decomposition.

A realistic manual time breakdown per 3,000-word requirements document:

- User stories: ~8–12 stories × 35 min average = **~6.5 hours**
- Features: grouping and writing 5–7 feature cards = **~2.5 hours**
- Dev tasks: 20–30 tasks × 25 min average = **~10.5 hours**
- **Total per document: ~19.5 hours**
- **Two documents per week: ~39 hours/week**

That figure is high because this is the full BA output for both documents combined - but it reflects reality for a BA producing sprint-ready backlogs with acceptance criteria, effort estimates, and dependency mapping, not just rough story lists.

## Step 2 - Time with the agentic workflow

Per week:

- Running the workflow: 2 documents × 5 min = **10 minutes**
- Reviewing and adjusting outputs: **2 hours**
- **Total per week with AI: ~2 hours 10 minutes**

---

## Step 3 - Weekly time saved

39 hours (manual) − 2.17 hours (AI-assisted) = **~36.8 hours saved per week**

---

## Step 4 - Annual hours saved

36.8 hours × 48 weeks = **~1,767 hours per year**

---

## Step 5 - Annual cost saving

1,767 hours × $135.00/hr = **$238,545 per year**

## Step 6 - Net saving after workflow running costs

Three golden prompts per document × 2 documents × 48 weeks = 288 full workflow runs per year.

At $0.22 per run (GPT-5.4-mini): 288 × $0.22 = **$63.36/year**
At $0.36 per run (Claude Sonnet 4.6): 288 × $0.36 = **$103.68/year**

Both figures are negligible against the labour saving - less than 0.05% of the total.

**Net annual saving: ~$238,480 (GPT) / ~$238,440 (Claude)**

## Summary table

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

---

The 39 hours/week manual baseline assumes the BA is producing the same output quality as the workflow - sprint-ready task cards with quantified acceptance criteria, Fibonacci effort estimates, and a validated dependency graph. If the BA's current output is rougher (story titles only, no ACs, no effort), the manual baseline is lower and the saving estimate should be adjusted downward accordingly. The more accurate framing for the notes is probably: **the workflow doesn't just save time, it raises the floor of output quality** - a Junior BA using it produces output closer to what a Senior BA would write manually, which has value independent of the time saving.
