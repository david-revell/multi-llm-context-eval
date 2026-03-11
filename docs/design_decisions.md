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
