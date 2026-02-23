import argparse
import csv
import json
import os
from datetime import datetime
from pathlib import Path

from dotenv import load_dotenv


def normalize(text: str) -> str:
    return " ".join(text.strip().lower().split())


def build_prompt(context: str, question: str) -> str:
    return (
        "You are answering strictly from provided context. "
        "If the answer is not in the context, reply exactly: NOT_IN_CONTEXT.\n\n"
        f"Context:\n{context}\n\n"
        f"Question:\n{question}\n\n"
        "Answer:"
    )


def ask_openai(prompt: str) -> str:
    from openai import OpenAI

    key = os.getenv("OPENAI_API_KEY", "")
    model = os.getenv("OPENAI_MODEL", "")
    if not key or not model:
        raise RuntimeError("OPENAI_API_KEY or OPENAI_MODEL missing")

    client = OpenAI(api_key=key)
    resp = client.chat.completions.create(
        model=model,
        messages=[{"role": "user", "content": prompt}],
    )
    return (resp.choices[0].message.content or "").strip()


def ask_anthropic(prompt: str) -> str:
    import anthropic

    key = os.getenv("ANTHROPIC_API_KEY", "")
    model = os.getenv("ANTHROPIC_MODEL", "")
    if not key or not model:
        raise RuntimeError("ANTHROPIC_API_KEY or ANTHROPIC_MODEL missing")

    client = anthropic.Anthropic(api_key=key)
    resp = client.messages.create(
        model=model,
        max_tokens=300,
        messages=[{"role": "user", "content": prompt}],
    )

    parts = []
    for block in resp.content:
        if hasattr(block, "text") and block.text:
            parts.append(block.text)
    return "\n".join(parts).strip()


def ask_gemini(prompt: str) -> str:
    import google.generativeai as genai

    key = os.getenv("GEMINI_API_KEY", "")
    model = os.getenv("GEMINI_MODEL", "")
    if not key or not model:
        raise RuntimeError("GEMINI_API_KEY or GEMINI_MODEL missing")

    genai.configure(api_key=key)
    m = genai.GenerativeModel(model)
    resp = m.generate_content(prompt)
    return (getattr(resp, "text", "") or "").strip()


def ask_llama_groq(prompt: str) -> str:
    from openai import OpenAI

    key = os.getenv("GROQ_API_KEY", "")
    model = os.getenv("GROQ_MODEL", "")
    if not key or not model:
        raise RuntimeError("GROQ_API_KEY or GROQ_MODEL missing")

    client = OpenAI(api_key=key, base_url="https://api.groq.com/openai/v1")
    resp = client.chat.completions.create(
        model=model,
        messages=[{"role": "user", "content": prompt}],
    )
    return (resp.choices[0].message.content or "").strip()


def score(answer: str, ground_truth: str) -> dict:
    a = normalize(answer)
    g = normalize(ground_truth)
    return {
        "exact_match": int(a == g),
        "abstained_not_in_context": int(a == "not_in_context"),
    }


def load_rows(csv_path: Path) -> list[dict]:
    rows = []
    with csv_path.open("r", encoding="utf-8-sig", newline="") as f:
        reader = csv.DictReader(f)
        for row in reader:
            rows.append(row)
    return rows


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--providers",
        nargs="+",
        default=["openai", "anthropic", "gemini", "llama"],
        choices=["openai", "anthropic", "gemini", "llama"],
    )
    parser.add_argument("--data", default="data/eval_set.csv")
    parser.add_argument("--dry-run", action="store_true")
    args = parser.parse_args()

    load_dotenv()
    root = Path(__file__).resolve().parents[1]
    data_path = root / args.data
    out_dir = root / "outputs"
    out_dir.mkdir(parents=True, exist_ok=True)

    provider_fns = {
        "openai": ask_openai,
        "anthropic": ask_anthropic,
        "gemini": ask_gemini,
        "llama": ask_llama_groq,
    }

    rows = load_rows(data_path)
    ts = datetime.now().strftime("%Y%m%d_%H%M%S")
    out_jsonl = out_dir / f"raw_results_{ts}.jsonl"
    out_csv = out_dir / f"summary_{ts}.csv"

    all_records = []
    with out_jsonl.open("w", encoding="utf-8") as jf:
        for row in rows:
            for provider in args.providers:
                prompt = build_prompt(row["context"], row["question"])
                if args.dry_run:
                    answer = f"DRY_RUN_{provider}"
                    err = ""
                else:
                    try:
                        answer = provider_fns[provider](prompt)
                        err = ""
                    except Exception as e:
                        answer = ""
                        err = str(e)

                metric = score(answer, row["ground_truth"]) if not err else {"exact_match": 0, "abstained_not_in_context": 0}
                rec = {
                    "item_id": row["item_id"],
                    "failure_mode": row["failure_mode"],
                    "provider": provider,
                    "question": row["question"],
                    "ground_truth": row["ground_truth"],
                    "answer": answer,
                    "error": err,
                    **metric,
                }
                all_records.append(rec)
                jf.write(json.dumps(rec, ensure_ascii=True) + "\n")

    with out_csv.open("w", encoding="utf-8", newline="") as f:
        writer = csv.DictWriter(
            f,
            fieldnames=["item_id", "failure_mode", "provider", "exact_match", "abstained_not_in_context", "error"],
        )
        writer.writeheader()
        for r in all_records:
            writer.writerow({k: r.get(k, "") for k in writer.fieldnames})

    print(f"Wrote: {out_jsonl}")
    print(f"Wrote: {out_csv}")


if __name__ == "__main__":
    main()

