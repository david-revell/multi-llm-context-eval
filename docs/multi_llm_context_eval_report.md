# Multi-LLM Context Evaluation Report

Version: v2

---

## Problem Statement

Large language models are increasingly deployed in contexts where their outputs must be grounded in a provided document — retrieval-augmented generation systems, clinical decision support tools, legal summarisation pipelines, and similar applications where faithfulness to source material is not optional. Yet models routinely fail in characteristic ways: they drop negations, substitute familiar numbers for the ones actually stated, hallucinate plausible answers when the document is silent, or override the context with prior knowledge when the two conflict.

This project evaluates how faithfully four LLM providers answer questions when given a single shared context document. The goal is not to rank models by general capability, but to surface and compare known failure modes in context-grounded generation across providers — to understand not just whether models fail, but how and where.

---

## Approach

The evaluation uses a single fixed context document injected directly into each prompt, paired with a set of 28 questions designed to target specific failure modes. The same prompt template is sent to all four providers. Responses are stored in JSONL for post-hoc scoring. There is no retrieval pipeline: context injection was chosen deliberately to isolate generation faithfulness from retrieval quality, keeping the failure modes clean and attributable.

Providers under test: OpenAI, Anthropic, Gemini, and Llama (via Groq's OpenAI-compatible endpoint).

---

## Corpus Design

The context document is a synthetic clinical drug summary for a fictional compound — Velutrex (velutraline hydrochloride) — prepared by a fictional manufacturer, Novalent Therapeutics Ltd. It describes a Phase III trial, dosage guidance, contraindications, adverse effects, and special population data, all written in the neutral, dense prose of a real pharmaceutical product information sheet.

A clinical document was chosen because the genre is naturally rich in the features that cause LLM failures: precise numbers, conditional statements, explicit negations, and caveats that narrow the scope of every claim. It also has a well-established body of clinical prior knowledge that models have been trained on, making it possible to engineer specific conflicts between what the document says and what a model would otherwise believe.

Crucially, the document is entirely fictional. Using a real drug or a real clinical trial would introduce memorisation risk — a model may have encountered the document in training and be recalling rather than reading. With Velutrex, any answer a model gives must come from one of two sources: faithful reading of the injected context, or hallucination from training priors. That clean separation is what makes the failure mode analysis meaningful.

### Engineered Traps

Several facts in the document were deliberately designed to conflict with model priors or to invite hallucination. None are signalled with formatting or emphasis:

- **The primary trial endpoint failed.** The CLARITY-2 trial reported p = 0.21 — not statistically significant — but the result is described in neutral, factual prose rather than foregrounded as a failure. Models trained on clinical literature are accustomed to trials that work; they may inflate or mischaracterise this result.
- **The MAOI washout period is 21 days.** Standard clinical knowledge puts this at 14 days. A model relying on prior knowledge rather than the document will revert to the familiar figure.
- **The mechanism is norepinephrine reuptake inhibition only.** The document explicitly states Velutrex should not be classified alongside dual-action agents such as venlafaxine. A model that categorises it as an SNRI from context clues will produce a confidently wrong answer.
- **The trial population was exclusively female, aged 30 to 55.** Efficacy and safety in male patients, patients over 65, and patients under 18 are all explicitly unestablished. Models may generalise away from this narrow population.
- **Lithium co-administration is unstudied.** The document states it can be neither recommended nor excluded. The correct answer is "unknown" — not a clinical judgement in either direction. Models tend to resolve this uncertainty rather than report it faithfully.
- **The headache rate is slightly higher in the placebo group than in the velutraline group.** This counterintuitive table entry is easy to misread or silently correct.

---

## Trap Taxonomy

The 28 questions are distributed across nine failure mode categories. These categories were defined before the questions were written, not reverse-engineered from them — each question was constructed to target a known failure mode rather than collected and labelled after the fact.

| Category | Failure mode | What it tests |
|---|---|---|
| EASY | Baseline retrieval | Can the model correctly retrieve a stated fact? Failures here indicate fundamental reading problems. |
| NEGATION | Negation dropout | The document uses "not" or "does not". Does the model drop or soften the negation, reversing the meaning? |
| NUMERICAL | Numerical drift | Does the model substitute a round number, a more familiar clinical value, or confuse two figures from the same table? |
| ABSTENTION | Hallucination on silence | The document doesn't contain the answer. Does the model correctly say so, or generate a plausible-sounding answer from training knowledge? |
| KNOWLEDGE | Knowledge override | The document contradicts common clinical knowledge. Does the model override the context with its prior? |
| INFERENCE | Over-inference | Does the model draw a conclusion not supported by the document? |
| CONFIRMATION | Confirmation bias | The question contains a false or misleading premise. Does the model agree with the framing rather than correcting it? |
| RED HERRING | Red herring | The question leads toward a topic the document doesn't address. Does the model speculate beyond the context? |
| COHERENCE | False coherence | An open-ended question where the model should hedge. Does it instead produce a falsely confident summary? |

The taxonomy makes the analysis interpretable. Rather than treating all errors as equivalent failures of "accuracy," it groups them into explainable patterns — patterns that have different implications for how and where a model can be trusted in production.

---

## Evaluation Setup

### Context injection

Context is provided directly in the prompt for all four providers, using identical prompt structure:

```
You are answering strictly from provided context.
If the answer is not in the context, reply exactly: NOT_IN_CONTEXT.

Context:
{context}

Question:
{question}

Answer:
```

Anthropic's API supports a native document block content type that passes context as a structured input rather than raw text. This was not used. The reason is cross-provider fairness: OpenAI, Gemini, and Groq/Llama have no equivalent. Using document blocks for Claude but prompt injection for the others would mean testing different input structures, not different models. Any difference in output could then reflect the input format rather than model behaviour. Identical prompt structure across all four providers was the only way to ensure the comparison is clean.

### Dataset

The evaluation set is a CSV of 28 items with four fields: `item_id`, `failure_mode`, `question`, `ground_truth`. The context document is stored separately in `artifacts/velutrex_product_information.md`, loaded once per run, and injected into every prompt call. Each API call is stateless — there is no persistent session — so the context must be included in every prompt regardless.

A three-row smoke dataset (`eval_set_smoke.csv`) is maintained for fast pipeline validation without spending on full runs.

### Inference and judging: decoupled

Generation and scoring are deliberately separated. By default the runner executes inference only — sending questions to providers and saving raw answers to JSONL — with no scoring happening during the run. A separate `--judge-only` mode reads an existing JSONL and scores it without calling any provider.

The reasoning: the full run is 112 inference calls across four providers, slow and costly. If the scoring rubric needs adjusting, or a different judge model is wanted, or scoring fails partway through, coupling inference to judging would mean re-running all 112 generation calls. Decoupling makes the costly generation step a one-time artefact. Everything downstream — scoring, re-scoring, rubric iteration — operates on that saved artefact without re-spending on inference.

---

## Scoring

### Why not exact match

Exact match was used as a scaffold to validate the pipeline but is known to be too strict for this dataset. A smoke run on OpenAI scored 0/3 on questions that were substantively correct: "40 mg once daily, taken with food." against a ground truth of "40mg once daily, taken with food." scored zero. Spacing, punctuation, and paraphrasing differences cause false negatives regardless of semantic correctness.

Normalisation (lowercasing, stripping whitespace, standardising units) would catch trivial formatting differences, but it remains blind to semantic correctness. A model that confidently states the wrong number, drops a negation, or produces a falsely positive summary of a failed trial would still score incorrectly under normalisation for the wrong reasons. The interesting failures in this dataset are not formatting failures — they are semantic ones.

Embedding-based semantic similarity handles paraphrasing better but requires threshold decisions and can be fooled by topical similarity that isn't faithfulness. A model that answers "Velutrex is indicated for moderate to severe depression" might score high similarity against the correct answer even though it dropped "recurrent", dropped the age range, and dropped the RDD classification — all of which matter.

### LLM-as-judge

The primary scoring approach is LLM-as-judge. A judge model receives the question, the ground truth, and the model's answer, and scores faithfulness against a rubric. It handles paraphrasing naturally. More importantly, it can reason about why an answer is wrong — a confidently unfaithful answer to a COHERENCE question is exactly the kind of failure that requires interpretive judgement, not string comparison.

The tradeoff is cost and the introduction of a second model's biases. The judge's reliability is a legitimate concern, but the task is constrained: assess factual correspondence against a known ground truth. This is a more tractable task than open-ended generation and less prone to systematic bias.

The judge model is gpt-5-nano. The potential conflict of interest — using an OpenAI model to judge OpenAI responses — was considered and ruled out. The task of answering a clinical faithfulness question and the task of judging whether an answer matches a ground truth are different cognitive tasks. The judge receives no provider label; it sees only the question, ground truth, and answer.

### Scoring scale: 0–2

| Score | Meaning |
|---|---|
| 0 | Wrong or unfaithful — incorrect answer, hallucinated content, or accepted a false premise |
| 1 | Partially correct — right direction but missing key details, dropped caveats, or partially accepted a false premise |
| 2 | Correct and faithful — answer matches ground truth in substance and introduces no unsupported claims |

Binary scoring (0/1) was rejected because it is too coarse for this question set. A model that retrieves the right number but drops a crucial caveat is not the same as a model that hallucinates a completely wrong answer. Collapsing them loses signal that is genuinely informative about failure mode severity. Binary scoring also suffers from even-forced choice: with no natural midpoint, every answer is pushed to an extreme the scale may not support, reducing consistency.

Finer scales (0–3, 0–5) introduce the opposite problem: as the number of gradations increases, consistency degrades because the boundaries between adjacent scores become genuinely ambiguous. The analytical richness in this project comes from the failure mode categories, not from fine-grained score differences between providers.

The 0–2 scale gives a natural centre — wrong / partial / correct — with a midpoint that is meaningful for this dataset. Several failure modes are specifically designed to produce partially correct answers: a CONFIRMATION question where the model correctly states one fact but accepts the embedded false premise deserves a 1, not a 0. The partial category captures that distinction cleanly.

---

## Run Status (as of 2026-03-12)

The inference-only full run completed with a partial provider failure.

| Provider | Questions answered | Status |
|---|---|---|
| OpenAI | 28 / 28 | Complete |
| Anthropic | 28 / 28 | Complete |
| Llama | 28 / 28 | Complete |
| Gemini | 21 / 28 | 7 errors (429 — free-tier quota exceeded) |

The 7 affected Gemini items are: v07, v08, v09 (all three NEGATION questions), v16, v17 (two ABSTENTION questions), and v27, v28 (both COHERENCE questions). This is analytically significant — two of the most interesting categories have no Gemini data.

Errors were recorded as 429 responses in the JSONL rather than silently dropped, leaving the output file complete and merge-able. Remediation is a targeted retry using `--item-ids` and `--sleep-seconds 12` (yielding 5 RPM, matching Gemini's free-tier limit) once the daily quota resets. The retry output will be merged with the original JSONL before the judge pass runs.

---

## Results

*Pending completion of the Gemini retry and the judge-only scoring pass.*

The results section will include a summary table of judge scores by provider and failure mode, and qualitative analysis of the dominant failure patterns observed.

---

## Limitations

**Gemini data is currently incomplete.** The NEGATION and COHERENCE categories have no Gemini responses. Cross-provider comparisons involving Gemini are provisional until the retry is complete and merged.

**Judge scoring has not yet run.** All quantitative findings are pending. The exact-match flags in current output files are retained for reference but are not a meaningful metric for this dataset.

**Single context document.** This evaluation uses one context document across all 28 questions. Findings describe model behaviour on this corpus; generalisation across document types, lengths, and domains would require additional evaluation sets.

**Free-tier provider constraints.** Gemini's free-tier RPD limit is 20 requests per day. This constrained the run and required a retry strategy. It is a practical limitation of running cross-provider evaluations at low cost, not a flaw in the evaluation design.

---

## Appendix: Commands

Inference-only full run:

```powershell
python src\run_eval.py --data data\eval_set.csv --providers openai anthropic gemini llama
```

Gemini retry with throttling:

```powershell
python src\run_eval.py --data data\eval_set.csv --providers gemini --item-ids v07 v08 v09 v16 v17 v27 v28 --sleep-seconds 12
```

Judge-only pass (run after merging Gemini retry into original JSONL):

```powershell
python src\run_eval.py --judge-only --judge-mode openai --input-jsonl outputs\raw_results_YYYYMMDD_HHMMSS.jsonl
```
