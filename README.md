# Multi-LLM Context Evaluation

Synthetic evaluation corpus for comparing context-grounded generation across multiple LLM providers (OpenAI, Gemini, Claude, Llama).

## Scope (minimal)

This scaffold evaluates one core behavior: can each model answer from provided context only.

- Context is injected directly (retrieval is intentionally out of scope).
- Same prompt template is sent to each provider.
- Results are written to `outputs/` for later analysis.

## Repo Layout

- `artifacts/`: source evaluation assets (Velutrex corpus and question set)
- `artifacts/velutrex_product_information.md`: canonical runtime context loaded once per run
- `data/eval_set.csv`: full operational evaluation dataset (28 Velutrex items)
- `data/eval_set_smoke.csv`: lightweight 3-row smoke dataset for quick checks
- `src/run_eval.py`: minimal runner
- `.env.example`: required keys/models
- `requirements.txt`: SDK dependencies

## Quick Start

```powershell
cd C:\Users\david\Dropbox\ai_engineering\projects\multi-llm-context-eval
python -m venv .venv
.\.venv\Scripts\Activate.ps1
pip install -r requirements.txt
copy .env.example .env
```

## Which Command To Run

Use this sequence every time to avoid accidental spend.

1. Safe plumbing check (no API spend)

```powershell
python src\run_eval.py --dry-run --data data\eval_set_smoke.csv
```

2. Cheap real check (small API spend; one provider, 3 rows)

```powershell
python src\run_eval.py --data data\eval_set_smoke.csv --providers openai
```

3. Full real evaluation (higher API spend; all providers, full dataset)

```powershell
python src\run_eval.py --data data\eval_set.csv --providers openai anthropic gemini llama
```

How to choose:

- Use `--dry-run` when you only want to validate wiring, paths, and output files.
- Use `eval_set_smoke.csv` when you want a fast, low-cost real sanity check.
- Use `eval_set.csv` only when you are ready for full paid evaluation.

Important:

- `--dry-run` means no model API call is made.
- `--providers` controls which model backends are exercised.
- `--data` controls how many rows/questions are run.

Run all providers listed in `.env`:

```powershell
python src\run_eval.py
```

Run a quick smoke test dataset (3 rows):

```powershell
python src\run_eval.py --data data\eval_set_smoke.csv
```

Run a subset:

```powershell
python src\run_eval.py --providers openai anthropic
```

Dry-run (no API calls):

```powershell
python src\run_eval.py --dry-run
```

## Dataset Contract

CSV columns:

- `item_id`
- `failure_mode`
- `question`
- `ground_truth`

## Evaluation Artifacts

- `artifacts/velutrex_product_information.docx`: source human-authored context document for the Velutrex eval.
- `artifacts/velutrex_question_set.docx`: 28-question source set and trap taxonomy.
- `artifacts/velutrex_product_information.md` is the canonical context injected by `run_eval.py`.
- `data/eval_set.csv` is the operational CSV used by `run_eval.py`.
- `data/eval_set_smoke.csv` is a small regression/smoke input for fast sanity checks.

## Notes

- `llama` in this scaffold uses a Groq-compatible OpenAI endpoint (`GROQ_API_KEY`, `GROQ_MODEL`).
- The scoring is intentionally minimal for now (exact-match flag + abstention flag).
- This is an analysis-first starter: expand dataset + metrics before engineering complexity.

## Design Rationale

- See `docs/design_decisions.md` for explicit project design decisions and non-goals.
