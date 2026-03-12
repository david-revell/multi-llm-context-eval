import argparse
import csv
import json
import os
import re
import time
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
    # Groq supports OpenAI-compatible APIs, but chat.completions may be disabled
    # for some keys/accounts while responses works. Prefer responses first.
    try:
        resp = client.responses.create(model=model, input=prompt)
        text = getattr(resp, "output_text", "") or ""
        if text.strip():
            return text.strip()
    except Exception:
        pass

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


def load_context(context_path: Path) -> str:
    text = context_path.read_text(encoding="utf-8").strip()
    if not text:
        raise RuntimeError(f"Context file is empty: {context_path}")
    return text


def build_judge_prompt(question: str, ground_truth: str, answer: str) -> str:
    return (
        "You are grading factual faithfulness of an answer against a ground truth.\n"
        "Score using this rubric:\n"
        "0 = materially wrong/unfaithful (contradiction, hallucination, or false-premise acceptance)\n"
        "1 = partially faithful (right direction but missing key caveat/detail)\n"
        "2 = faithful in substance (matches meaning, no unsupported claims)\n\n"
        "Return exactly two lines:\n"
        "SCORE: <0|1|2>\n"
        "REASON: <one concise sentence>\n\n"
        f"Question:\n{question}\n\n"
        f"Ground truth:\n{ground_truth}\n\n"
        f"Answer:\n{answer}\n"
    )


def parse_judge_output(text: str) -> tuple[int, str]:
    score_match = re.search(r"(?im)^SCORE:\s*([012])\s*$", text)
    reason_match = re.search(r"(?im)^REASON:\s*(.+)\s*$", text)
    if not score_match:
        raise RuntimeError(f"Judge output missing SCORE line: {text!r}")
    score_val = int(score_match.group(1))
    reason_val = reason_match.group(1).strip() if reason_match else ""
    return score_val, reason_val


def judge_with_openai(question: str, ground_truth: str, answer: str) -> dict:
    from openai import OpenAI

    key = os.getenv("OPENAI_API_KEY", "")
    model = os.getenv("OPENAI_JUDGE_MODEL", "") or os.getenv("OPENAI_MODEL", "")
    if not key or not model:
        raise RuntimeError("OPENAI_API_KEY or OPENAI_JUDGE_MODEL/OPENAI_MODEL missing")

    client = OpenAI(api_key=key)
    prompt = build_judge_prompt(question, ground_truth, answer)
    resp = client.chat.completions.create(
        model=model,
        messages=[{"role": "user", "content": prompt}],
    )
    text = (resp.choices[0].message.content or "").strip()
    judge_score, judge_reason = parse_judge_output(text)
    return {
        "judge_score": judge_score,
        "judge_reason": judge_reason,
        "judge_error": "",
    }


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--providers",
        nargs="+",
        default=["openai", "anthropic", "gemini", "llama"],
        choices=["openai", "anthropic", "gemini", "llama"],
    )
    parser.add_argument("--data", default="data/eval_set.csv")
    parser.add_argument("--context-file", default="artifacts/velutrex_product_information.md")
    parser.add_argument("--judge-mode", choices=["off", "openai"], default="off")
    parser.add_argument("--dry-run", action="store_true")
    parser.add_argument("--judge-only", action="store_true")
    parser.add_argument("--input-jsonl", default="")
    parser.add_argument("--output-jsonl", default="")
    parser.add_argument("--output-csv", default="")
    parser.add_argument("--item-ids", nargs="+", default=[])
    parser.add_argument("--sleep-seconds", type=float, default=0.0)
    parser.add_argument("--sleep-providers", nargs="+", default=[])
    args = parser.parse_args()
    if args.sleep_seconds > 0 and not args.sleep_providers:
        args.sleep_providers = ["gemini"]

    load_dotenv(dotenv_path=Path(__file__).resolve().parents[1] / '.env', override=True)
    root = Path(__file__).resolve().parents[1]
    out_dir = root / "outputs"
    out_dir.mkdir(parents=True, exist_ok=True)

    if args.judge_only:
        if not args.input_jsonl:
            raise RuntimeError("--input-jsonl is required when --judge-only is set")

        in_path = Path(args.input_jsonl)
        if not in_path.is_absolute():
            in_path = root / in_path

        ts = datetime.now().strftime("%Y%m%d_%H%M%S")
        out_jsonl = Path(args.output_jsonl) if args.output_jsonl else out_dir / f"judged_results_{ts}.jsonl"
        out_csv = Path(args.output_csv) if args.output_csv else out_dir / f"judged_summary_{ts}.csv"
        if not out_jsonl.is_absolute():
            out_jsonl = root / out_jsonl
        if not out_csv.is_absolute():
            out_csv = root / out_csv

        records = []
        with in_path.open("r", encoding="utf-8") as f:
            for line in f:
                line = line.strip()
                if not line:
                    continue
                rec = json.loads(line)
                if args.item_ids and rec.get("item_id") not in args.item_ids:
                    continue
                records.append(rec)

        total = len(records)
        with out_jsonl.open("w", encoding="utf-8") as jf:
            for idx, rec in enumerate(records, start=1):
                err = rec.get("error", "")
                answer = rec.get("answer", "")
                judge = {"judge_score": "", "judge_reason": "", "judge_error": ""}
                if not err and answer and args.judge_mode == "openai":
                    try:
                        judge = judge_with_openai(
                            question=rec.get("question", ""),
                            ground_truth=rec.get("ground_truth", ""),
                            answer=answer,
                        )
                    except Exception as e:
                        judge["judge_error"] = str(e)

                metric = score(answer, rec.get("ground_truth", "")) if not err else {"exact_match": 0, "abstained_not_in_context": 0}
                rec.update(judge)
                rec.update(metric)
                jf.write(json.dumps(rec, ensure_ascii=True) + "\n")

                judge_note = "judge=off" if args.judge_mode == "off" else ("judge=ok" if not judge.get("judge_error") else "judge=err")
                provider = rec.get("provider", "unknown")
                item_id = rec.get("item_id", "unknown")
                print(f"Progress {idx}/{total} | provider={provider} | item_id={item_id} | {judge_note}", flush=True)
                if args.sleep_seconds > 0 and (not args.sleep_providers or provider in args.sleep_providers):
                    time.sleep(args.sleep_seconds)

        with out_csv.open("w", encoding="utf-8", newline="") as f:
            writer = csv.DictWriter(
                f,
                fieldnames=[
                    "item_id",
                    "failure_mode",
                    "provider",
                    "exact_match",
                    "abstained_not_in_context",
                    "judge_score",
                    "judge_error",
                    "error",
                ],
            )
            writer.writeheader()
            for r in records:
                writer.writerow({k: r.get(k, "") for k in writer.fieldnames})

        print(f"Wrote: {out_jsonl}")
        print(f"Wrote: {out_csv}")
        return

    data_path = root / args.data
    context_path = root / args.context_file
    provider_fns = {
        "openai": ask_openai,
        "anthropic": ask_anthropic,
        "gemini": ask_gemini,
        "llama": ask_llama_groq,
    }

    rows = load_rows(data_path)
    if args.item_ids:
        rows = [r for r in rows if r.get("item_id") in args.item_ids]
    default_context = load_context(context_path)
    ts = datetime.now().strftime("%Y%m%d_%H%M%S")
    out_jsonl = out_dir / f"raw_results_{ts}.jsonl"
    out_csv = out_dir / f"summary_{ts}.csv"

    all_records = []
    total = len(rows) * len(args.providers)
    counter = 0
    with out_jsonl.open("w", encoding="utf-8") as jf:
        for row_idx, row in enumerate(rows, start=1):
            for provider in args.providers:
                counter += 1
                prompt = build_prompt(default_context, row["question"])
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

                judge = {"judge_score": "", "judge_reason": "", "judge_error": ""}
                if not args.dry_run and not err and args.judge_mode == "openai":
                    try:
                        # Intentionally pass only q/gt/answer to avoid provider leakage.
                        judge = judge_with_openai(
                            question=row["question"],
                            ground_truth=row["ground_truth"],
                            answer=answer,
                        )
                    except Exception as e:
                        judge["judge_error"] = str(e)

                metric = score(answer, row["ground_truth"]) if not err else {"exact_match": 0, "abstained_not_in_context": 0}
                rec = {
                    "item_id": row["item_id"],
                    "failure_mode": row["failure_mode"],
                    "provider": provider,
                    "question": row["question"],
                    "ground_truth": row["ground_truth"],
                    "answer": answer,
                    "error": err,
                    **judge,
                    **metric,
                }
                all_records.append(rec)
                jf.write(json.dumps(rec, ensure_ascii=True) + "\n")
                judge_note = "judge=off" if args.judge_mode == "off" else ("judge=ok" if not judge.get("judge_error") else "judge=err")
                print(
                    f"Progress {counter}/{total} | q {row_idx}/{len(rows)} | provider={provider} | item_id={row['item_id']} | {judge_note}",
                    flush=True,
                )
                if args.sleep_seconds > 0 and (not args.sleep_providers or provider in args.sleep_providers):
                    time.sleep(args.sleep_seconds)

    with out_csv.open("w", encoding="utf-8", newline="") as f:
        writer = csv.DictWriter(
            f,
            fieldnames=[
                "item_id",
                "failure_mode",
                "provider",
                "exact_match",
                "abstained_not_in_context",
                "judge_score",
                "judge_error",
                "error",
            ],
        )
        writer.writeheader()
        for r in all_records:
            writer.writerow({k: r.get(k, "") for k in writer.fieldnames})

    print(f"Wrote: {out_jsonl}")
    print(f"Wrote: {out_csv}")


if __name__ == "__main__":
    main()



