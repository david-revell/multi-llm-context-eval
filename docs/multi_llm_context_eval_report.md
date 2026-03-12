# Multi-LLM Context Evaluation Report

Version: v1

## Problem Statement

Evaluate how faithfully multiple LLM providers answer questions when given a shared context document. The goal is not to rank models by general capability, but to surface and compare known failure modes in context-grounded generation such as negation dropout, numerical drift, hallucination on silence, and knowledge override.

## Summary of Approach

The evaluation uses a single, fixed context document injected directly into prompts and a CSV of question-level test cases. The same prompt template is sent to each provider. Responses are stored in JSONL for later analysis. Scoring includes a deterministic exact-match flag and a planned LLM-as-judge rubric (0 to 2) for semantic faithfulness.

## Corpus Design

The corpus is a synthetic clinical drug summary for a fictional drug (Velutrex / velutraline hydrochloride) authored in .docx and converted to markdown for runtime use. A clinical document was chosen because it is dense with numbers, caveats, and negations, creating natural traps for LLMs. The document is entirely fictional, reducing memorization risk and ensuring answers must come from the injected context rather than prior knowledge.

## Trap Taxonomy

Each question is tagged with one of nine failure modes, designed before writing the questions:

- EASY: baseline retrieval of stated facts.
- NEGATION: negation dropout (reversing meaning).
- NUMERICAL: numerical drift or substitution.
- ABSTENTION: hallucination when the answer is not present.
- KNOWLEDGE: overriding context with prior knowledge.
- INFERENCE: over-inference beyond stated facts.
- CONFIRMATION: accepting a false premise in the question.
- RED HERRING: speculating on a related but unsupported topic.
- COHERENCE: producing a confident summary where caution is required.

This taxonomy makes the analysis interpretable by grouping errors into known, explainable failure categories rather than treating all mistakes as equal.

## Evaluation Setup

Key design choices:

- Context is injected directly into the prompt for all providers for cross-provider fairness.
- The context is stored once in `artifacts/velutrex_product_information.md` and loaded once per run.
- The CSV contains only question-level fields: `item_id`, `failure_mode`, `question`, `ground_truth`.
- Inference and judging are decoupled so the expensive generation run happens once, and judging can be re-run without re-calling providers.

Providers under test:

- OpenAI
- Anthropic
- Gemini
- Llama (via Groq OpenAI-compatible endpoint)

## Scoring Rationale

Exact match was used as a scaffold to validate the pipeline but is known to be too strict for this dataset due to paraphrasing and punctuation variance. The primary scoring approach is LLM-as-judge, which reads the question, ground truth, and model answer and assigns a 0 to 2 score:

- 0: wrong or unfaithful.
- 1: partially correct, missing a key caveat.
- 2: correct and faithful to the ground truth.

This scale captures partial correctness, which is common in failure modes like CONFIRMATION and COHERENCE.

## Run Status (As of 2026-03-12)

Inference-only full run completed with partial provider failure:

- OpenAI: 28/28 complete.
- Anthropic: 28/28 complete.
- Llama: 28/28 complete.
- Gemini: 21/28 complete, 7 errors due to free-tier quota limits.

Planned remediation:

- Re-run Gemini for the missing item_ids with throttling to respect RPM limits.
- Merge the corrected Gemini rows into the original JSONL.
- Run judge-only scoring on the merged JSONL.

## Results (Pending Judge Pass)

TODO: Insert summary table of judge scores by provider and failure mode after judge pass.

TODO: Insert key qualitative findings (e.g., dominant failure modes per provider).

## Limitations

- Gemini results are currently incomplete due to free-tier quota limits.
- Judge scoring has not been executed yet; analysis is pending.
- Exact match is retained for reference but is not a meaningful metric for this dataset.

## Next Steps

1. Re-run Gemini for missing rows using `--item-ids` and `--sleep-seconds`.
2. Merge Gemini retry results into the full JSONL.
3. Run judge-only scoring on the merged JSONL.
4. Produce final analysis with per-provider failure mode patterns.

## Appendix: Commands

Inference-only full run:

```powershell
python src\run_eval.py --data data\eval_set.csv --providers openai anthropic gemini llama
```

Gemini retry with throttling:

```powershell
python src\run_eval.py --data data\eval_set.csv --providers gemini --item-ids v07 v08 v09 v16 v17 v27 v28 --sleep-seconds 12
```

Judge-only pass:

```powershell
python src\run_eval.py --judge-only --judge-mode openai --input-jsonl outputs\raw_results_YYYYMMDD_HHMMSS.jsonl
```
