# Multi-LLM Context Evaluation Report

Version: v3

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

## Run Status (as of 2026-03-13)

All inference and judging complete. The Gemini free-tier quota failure reported in v2 was resolved via a targeted retry, and the full judge pass has run across all 112 records.

| Provider | Questions answered | Judge scored | Status |
|---|---|---|---|
| OpenAI | 28 / 28 | 28 / 28 | Complete |
| Anthropic | 28 / 28 | 28 / 28 | Complete |
| Gemini | 28 / 28 | 28 / 28 | Complete (retry merged) |
| Llama | 28 / 28 | 28 / 28 | Complete |

---

## Results

### Overall scores

| Provider | Score | Max | % |
|---|---|---|---|
| OpenAI | 53 | 56 | 95% |
| Anthropic | 48 | 56 | 86% |
| Gemini | 46 | 56 | 82% |
| Llama | 41 | 56 | 73% |

OpenAI leads by a clear margin. The gap between Anthropic and Gemini is narrow; Llama trails the field by 7–12 points.

### Scores by failure mode

The table shows points scored out of the category maximum (number of questions × 2).

| Mode | Questions | OpenAI | Anthropic | Gemini | Llama |
|---|---|---|---|---|---|
| EASY | 6 | 12/12 (100%) | 11/12 (92%) | 12/12 (100%) | 12/12 (100%) |
| NEGATION | 3 | 6/6 (100%) | 6/6 (100%) | 6/6 (100%) | 6/6 (100%) |
| NUMERICAL | 5 | 10/10 (100%) | 10/10 (100%) | 10/10 (100%) | 10/10 (100%) |
| ABSTENTION | 4 | 8/8 (100%) | 6/8 (75%) | 8/8 (100%) | 6/8 (75%) |
| KNOWLEDGE | 2 | 4/4 (100%) | 4/4 (100%) | 2/4 (50%) | 2/4 (50%) |
| INFERENCE | 2 | 2/4 (50%) | 4/4 (100%) | 1/4 (25%) | 1/4 (25%) |
| CONFIRMATION | 2 | 4/4 (100%) | 3/4 (75%) | 2/4 (50%) | 2/4 (50%) |
| RED HERRING | 2 | 3/4 (75%) | 2/4 (50%) | 2/4 (50%) | 1/4 (25%) |
| COHERENCE | 2 | 4/4 (100%) | 2/4 (50%) | 3/4 (75%) | 1/4 (25%) |

### Where each provider lost points

| Mode | OpenAI | Anthropic | Gemini | Llama |
|---|---|---|---|---|
| EASY | 0 | 1 | 0 | 0 |
| NEGATION | 0 | 0 | 0 | 0 |
| NUMERICAL | 0 | 0 | 0 | 0 |
| ABSTENTION | 0 | 2 | 0 | 2 |
| KNOWLEDGE | 0 | 0 | 2 | 2 |
| INFERENCE | 2 | 0 | 3 | 3 |
| CONFIRMATION | 0 | 1 | 2 | 2 |
| RED HERRING | 1 | 2 | 2 | 3 |
| COHERENCE | 0 | 2 | 1 | 3 |
| **Total lost** | **3** | **8** | **10** | **15** |

### Finding 1: Three categories were perfect across all four providers

NEGATION, NUMERICAL, and EASY each scored 100% for every provider. This is notable because negation dropout and numerical drift were specifically engineered to be hard — prior clinical knowledge creates the temptation to substitute the familiar 14-day MAOI washout for the document's 21 days, and the failed trial result creates pressure to misread the p-value. Every model resisted both. These are genuinely positive results, not simply the absence of failure.

### Finding 2: NOT_IN_CONTEXT is not always the safe answer

Of the 23 non-perfect scores across all providers, 16 are cases where the model returned NOT_IN_CONTEXT. In roughly half of those, this was the right call — the answer genuinely was not in the document. In the other half, it was wrong: the model deflected on a question the document did address. This matters because NOT_IN_CONTEXT carries an implicit claim of faithfulness — the model appears to be following instructions — while actually failing to retrieve content that is present. It is a quiet failure mode, harder to catch than a hallucinated answer.

The remaining 7 non-perfect scores are substantive answers that scored 1 (partial): the model found the relevant content but either dropped a caveat or added detail beyond what the ground truth required.

### Finding 3: Inference is the sharpest differentiator between providers

Anthropic is the only provider to score perfectly on INFERENCE (4/4). The other three all scored 0 on v21 — the question that embeds a false premise about statistical significance ("Given that Velutrex showed statistically significant results in CLARITY-2..."). OpenAI, Gemini, and Llama all returned NOT_IN_CONTEXT, which is technically a refusal rather than an acceptance of the false premise, but is still wrong: the document does address the trial result, and the correct response is to correct the false premise. Only Anthropic did this, explicitly identifying the premise as incorrect and citing p = 0.21.

This is the most revealing result in the dataset. Correcting a false premise embedded in a question requires the model to do something more than retrieve or abstain — it must reason about the relationship between the question's framing and the document's content, and push back. That is a harder task, and the spread across providers is the largest of any category.

### Finding 4: Gemini and Llama share a distinctive failure on KNOWLEDGE

Both Gemini and Llama returned NOT_IN_CONTEXT on v20, the SNRI classification question. The question asks about dual neurotransmitter systems on the assumption that Velutrex is classified as an SNRI — a false premise the document explicitly contradicts. The correct answer is to reject the classification. OpenAI and Anthropic both did so with substantive responses citing the mechanism section. Gemini and Llama deflected instead.

Unlike the v21 failure (where all four providers struggle), this is a case where two providers consistently failed and two consistently succeeded. It suggests a difference in how aggressively models search the context for relevant content before concluding a question is unanswerable.

### Finding 5: Abstention failures are false negatives, not hallucinations

The two abstention failures — Anthropic on v17 (dosage for over-65 patients) and Llama on v16 (lithium co-administration) — are both cases where the model returned NOT_IN_CONTEXT when the answer was in the document. These are not hallucinations; the models did not generate plausible-sounding false content. They under-retrieved instead. On v17, the document states explicitly that there is no approved dosage for patients over 65. On v16, it states that lithium co-administration has not been studied and cannot be recommended or excluded — which is itself the answer. In both cases the model missed findable content and reported silence where the document was not silent.

### Finding 6: Red herring is the hardest category across all providers

No provider scored perfectly on RED HERRING. The dominant failure is on v26, the social functioning question, where models correctly stated that Velutrex is not indicated for anxiety disorders but then added unsupported claims about CLARITY-2 secondary endpoints. This is a consistent pattern across providers rather than a provider-specific weakness: the question names a real feature of the document (social functioning scores) and leads toward a plausible extension (anxiety disorder suitability). Every model partially followed the lead.

### Finding 7: Coherence separates OpenAI from the field

OpenAI is the only provider to score perfectly on COHERENCE (4/4). Llama scores 1/4 — its worst category — returning NOT_IN_CONTEXT on v27, the question asking how confident clinicians should be in Velutrex's efficacy. This question requires integrating multiple pieces of information (non-significant p-value, narrow trial population, female-only sample) into a synthesised judgement. Bare deflection is the weakest possible response. Anthropic and Gemini both attempted synthesis but lost points for omitting one or more of the key caveats from the ground truth.

---

## Limitations

**Single context document.** This evaluation uses one context document across all 28 questions. Findings describe model behaviour on this specific corpus. Generalisation across document types, lengths, and domains would require additional evaluation sets.

**Small question counts per category.** Several categories contain only two questions. A single unexpected result can shift a category score by 50%. The category-level findings are indicative rather than definitive, and should be read alongside the individual item analysis rather than as standalone statistics.

**Free-tier provider constraints.** Gemini's free-tier rate limit required a retry strategy and introduced a gap in v2. The retry completed successfully and all Gemini data is present in v3. The constraint is a practical limitation of running cross-provider evaluations at low cost, not a flaw in the evaluation design.

**Judge scoring against terse ground truths.** The LLM-as-judge approach scores answers against a known ground truth. Where ground truths are written minimally, a model that gives a richer but entirely faithful answer can be penalised for including correct detail. One confirmed instance of this occurred on v05 (Anthropic): the model correctly stated the trial duration and accurately described the randomisation design — information present verbatim in the document — but received a score of 1 rather than 2 because the ground truth was simply "12 weeks." This is a judge error, not a model error, and it marginally understates Anthropic's true performance on that item. The score has been left as-is rather than adjusted post-hoc, but the pattern is worth noting as a limitation of ground-truth-anchored LLM-as-judge evaluation when ground truths vary in verbosity.

**Potential judge bias toward OpenAI.** The judge model is an OpenAI model (gpt-5-nano). The possibility that it scores OpenAI responses more generously than competitors cannot be ruled out, though the task — comparing an answer against a known ground truth — is more constrained than open-ended generation and less likely to exhibit systematic stylistic preference. The judge received no provider labels.

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
