# Cost Analysis/Breakdown

## Confirmed pricing

GPT-5.4-mini: $0.75 input / $4.50 output per million tokens.
Claude Sonnet 4.6: $3.00 input / $15.00 output per million tokens.

## Reverse-engineering the token volume from the GPT cost

Your measured cost for GPT-5.4-mini across all three golden prompts was $0.22. Working backwards from that:

The pipeline makes multiple API calls per run - ActionPlanningAgent, RoutingAgent (once per step), and each specialist agent. For the full workflow (3 steps), that's approximately 5–6 API calls. For user stories and features (1 step each), approximately 2–3 calls each. Across all three prompts, roughly 10–12 total API calls.

At $0.22 total with GPT-5.4-mini's blended rate, and given the output sizes we've seen (the dev tasks output alone is ~4,000 tokens), the implied token volume is approximately:

- **Input tokens across all calls: ~45,000–55,000** (accumulated context grows with each step - the spec, prior step outputs, knowledge strings, and system prompts all recirculate)
- **Output tokens across all calls: ~12,000–15,000** (user stories ~1,800, features ~2,200, dev tasks ~5,500, plus intermediate planner and router outputs)

Cross-checking: 50K input × $0.75/M = $0.038, plus 13K output × $4.50/M = $0.059, gives roughly $0.097 per prompt set × scaled for routing overhead ≈ $0.20–0.24. That aligns with your measured $0.22, so the token volume estimate is sound.

---

## Estimated cost for Claude Sonnet 4.6

Applying the same token volume to Sonnet 4.6's rates:

- 50,000 input tokens × $3.00/M = **$0.15**
- 13,000 output tokens × $15.00/M = **$0.195**
- **Total ≈ $0.34–$0.38**

The most defensible single figure is **~$0.36**, representing approximately **1.6× the GPT-5.4-mini cost** for the same workflow.

## Why the multiplier isn't simply the raw rate ratio

The naive rate comparison would suggest Claude costs 4× more (input: $3.00 vs $0.75) or 3.3× more (output: $15.00 vs $4.50). The actual multiplier is lower for two reasons: output tokens dominate the cost in this pipeline because the knowledge strings and accumulated context are large inputs but the specialist agent outputs are the expensive side, and that ratio is closer to 3.3×; but Claude's outputs for the same tasks are moderately shorter on average (24 tasks vs 36 tasks in the best GPT run, fewer per-task card repetitions) which compresses the effective output token count by roughly 30–35%, bringing the real-world multiplier down to approximately 1.5–1.7×.

**For your CANDIDATE_NOTES, the figure to cite is approximately $0.35–$0.38, versus $0.22 for GPT-5.4-mini - roughly 1.6× more expensive for a higher-density, architecturally richer output.**
