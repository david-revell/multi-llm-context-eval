# Design Decisions (Eval-First)

This project intentionally prioritizes evaluation signal over engineering complexity.

## Core Principle

Measure **context-grounded generation behavior** across providers, not retrieval system quality.

## Decisions

1. Injected context, no retrieval pipeline
- Context is provided directly in the prompt.
- Rationale: isolate generation faithfulness and failure modes (negation dropout, numerical drift, abstention failure, knowledge override, over-inference).

2. Single canonical context file per run
- Runtime context comes from `artifacts/velutrex_product_information.md`.
- Rationale: avoid duplicated context text in CSV rows and ensure one source of truth.

3. Question-level CSV only
- `data/eval_set.csv` and `data/eval_set_smoke.csv` contain:
  - `item_id`, `failure_mode`, `question`, `ground_truth`
- Rationale: keep dataset focused on test cases, not document storage.

4. Two dataset tiers
- `data/eval_set.csv`: full operational set (28 items).
- `data/eval_set_smoke.csv`: 3-row smoke set for cheap/fast sanity checks.
- Rationale: quick checks before paid runs, while preserving full eval coverage.

5. Smoke and full runs share the same context behavior
- Both datasets still use the same `--context-file` mechanism.
- Rationale: smoke should validate the same prompt/context path, only with fewer questions.

6. Minimal scoring for now
- Current scoring is exact match plus `NOT_IN_CONTEXT` abstention flag.
- Rationale: lightweight baseline to run comparisons now; judge-based semantic scoring can be added later.

7. Judge-input de-identification requirement (for LLM-as-judge stage)
- Judge prompts must include only: `question`, `ground_truth`, `answer`.
- Judge prompts must not include provider/model identifiers (for example `provider`, `model`, `openai`, `anthropic`, `gemini`, `llama`).
- Rationale: prevent provider leakage/bias in judging and keep cross-provider comparison fair.

8. Progress logging during long runs
- The runner emits per-call progress: overall count, question index, provider, and item_id.
- Rationale: the full run is long and expensive; incremental feedback reduces anxiety and makes it clear the job is advancing.

9. Sequential judge scoring by default (no batch API)
- Judge scoring is executed once per answer (up to 28 x 4 = 112 calls), either inline during generation or in a separate `--judge-only` pass.
- Rationale: the sequential approach is simplest, most reliable across environments, and keeps the code transparent.
- What was not done: batch/bulk judge submission (e.g., provider batch APIs) was intentionally deferred because it adds operational complexity, asynchronous job handling, and more failure modes for a one-off evaluation.

10. Separation of generation and judging
- The runner supports a `--judge-only` mode that takes an existing JSONL of raw answers and produces judged outputs.
- Rationale: keeps generation and scoring decoupled, allowing a single paid run to be judged later without re-running providers.

11. Provider-scoped throttling for rate limits
- A `--sleep-seconds` throttle is supported, defaulting to **Gemini-only** unless `--sleep-providers` is explicitly set.
- Rationale: Gemini free-tier RPM/RPD limits are tight and caused partial failures in a full run; throttling Gemini reduces 429s without slowing all providers. RPM = requests per minute; a 12s sleep yields ~5 RPM (60 / 12).
- What was not done: a full adaptive retry/backoff layer across all providers (overkill for this eval-first scaffold).

## Explicit Non-Goals (Current Phase)

- Building a retrieval stack (chunking, embeddings, vector DB, reranking).
- Optimizing infra, orchestration, or advanced pipelines.
- Expanding framework complexity before producing analysis outputs.

## Future Extension Points (If Needed)

1. Multi-context experiments
- Add `context_id` to CSV and map IDs to files.
- Not implemented now because current eval uses one context.

2. Semantic scoring layer
- Add judge model scoring/rubric to reduce exact-match brittleness.

3. Analysis artifacts
- Add notebook/report focused on cross-provider failure-mode patterns.
