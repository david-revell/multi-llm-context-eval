# Multi-LLM Context Evaluation

Synthetic evaluation corpus for comparing context-grounded generation across multiple LLM providers (OpenAI, Gemini, Claude, Llama).

## Scope (minimal)

This scaffold evaluates one core behavior: can each model answer from provided context only.

- Context is injected directly (retrieval is intentionally out of scope).
- Same prompt template is sent to each provider.
- Results are written to `outputs/` for later analysis.

## Repo Layout

- `artifacts/`: source evaluation assets (Velutrex corpus and question set)
- `data/eval_set.csv`: runtime evaluation dataset used by the runner
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

Run all providers listed in `.env`:

```powershell
python src\run_eval.py
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
- `context`
- `question`
- `ground_truth`

## Evaluation Artifacts

- `artifacts/velutrex_product_information.docx`: injected context document for the Velutrex eval.
- `artifacts/velutrex_question_set.docx`: 28-question source set and trap taxonomy.
- `data/eval_set.csv` should contain the operational CSV version of the question set used by `run_eval.py`.

## Notes

- `llama` in this scaffold uses a Groq-compatible OpenAI endpoint (`GROQ_API_KEY`, `GROQ_MODEL`).
- The scoring is intentionally minimal for now (exact-match flag + abstention flag).
- This is an analysis-first starter: expand dataset + metrics before engineering complexity.
