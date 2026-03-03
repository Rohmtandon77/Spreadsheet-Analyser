#!/usr/bin/env python3
"""
TableBench evaluation adapter.

Runs our spreadsheet analysis engine on TableBench_DP.jsonl, produces
inference results in the format expected by TableBench's parse and eval scripts.
"""

import argparse
import json
import os
import re
import sys
import tempfile
from pathlib import Path

# Project root
ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

import pandas as pd
from backend.app.models import Message, MessageRole
from worker.analysis.engine import run_analysis


def table_to_csv(table: dict) -> str:
    """Convert TableBench table dict to CSV string."""
    cols = table["columns"]
    rows = table["data"]
    df = pd.DataFrame(rows, columns=cols)
    return df.to_csv(index=False)


def extract_final_answer(answer: str, execution_output: str) -> str:
    """
    Extract or construct 'Final Answer: X' for TableBench parser.
    Parser expects regex: Final Answer: (.+)
    """
    # Already has it
    m = re.search(r"Final Answer:\s*(.+)", answer, re.IGNORECASE | re.DOTALL)
    if m:
        return m.group(0).strip()

    # Try execution output (often has the numeric result)
    m = re.search(r"Final Answer:\s*(.+)", execution_output, re.IGNORECASE | re.DOTALL)
    if m:
        return m.group(0).strip()

    # Last non-empty line of stdout often has the result
    lines = [l.strip() for l in execution_output.strip().split("\n") if l.strip()]
    if lines:
        last = lines[-1]
        # If it looks like a number or short answer, use it
        if len(last) < 100 and not last.startswith("Traceback"):
            return f"Final Answer: {last}"

    # Use answer text, take first line or first 50 chars
    first_line = answer.strip().split("\n")[0][:80].strip()
    if first_line:
        return f"Final Answer: {first_line}"

    return "Final Answer: "


def load_tablebench_dp() -> list[dict]:
    """Load TableBench_DP.jsonl from HuggingFace cache or download."""
    try:
        from huggingface_hub import hf_hub_download

        path = hf_hub_download(
            repo_id="Multilingual-Multimodal-NLP/TableBench",
            filename="TableBench_DP.jsonl",
            repo_type="dataset",
        )
    except Exception as e:
        raise SystemExit(f"Failed to load TableBench: {e}") from e

    samples = []
    with open(path) as f:
        for line in f:
            samples.append(json.loads(line))
    return samples


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--limit", type=int, default=0, help="Max samples (0=all)")
    ap.add_argument(
        "--output",
        type=Path,
        default=ROOT / "tablebench" / "eval_examples" / "inference_results",
        help="Output dir for inference jsonl",
    )
    ap.add_argument("--model-name", default="DeepSeek-R1-Distill-Qwen-32B", help="Model name for results")
    args = ap.parse_args()

    samples = load_tablebench_dp()
    if args.limit:
        samples = samples[: args.limit]
    print(f"Running on {len(samples)} samples")

    args.output.mkdir(parents=True, exist_ok=True)
    out_path = args.output / f"{args.model_name}=TableBench_DP=Ours.jsonl"

    results = []
    with tempfile.TemporaryDirectory() as tmpdir:
        tmp = Path(tmpdir)
        charts_dir = tmp / "charts"
        charts_dir.mkdir()

        for i, sample in enumerate(samples):
            print(f"  [{i+1}/{len(samples)}] {sample['id']} ({sample['qtype']})")

            csv_path = tmp / f"{sample['id']}.csv"
            csv_path.write_text(table_to_csv(sample["table"]), encoding="utf-8")

            conversation = [
                Message(role=MessageRole.user, content=sample["question"]),
            ]

            try:
                result = run_analysis(
                    file_path=str(csv_path),
                    charts_dir=charts_dir,
                    conversation=conversation,
                )
                prediction = extract_final_answer(result.answer, result.execution_output)

                # Build full prediction string for parser (it may extract code for PoT etc.)
                full_pred = result.answer
                if result.code:
                    full_pred = f"```python\n{result.code}\n```\n\n{full_pred}"
                if "Final Answer:" not in full_pred:
                    full_pred = f"{full_pred}\n\n{prediction}"
            except Exception as e:
                print(f"    ERROR: {e}")
                full_pred = f"Final Answer: "
                prediction = "Final Answer: "

            out = {**sample, "model_name": args.model_name, "prediction": full_pred}
            results.append(out)

    with open(out_path, "w", encoding="utf-8") as f:
        for r in results:
            f.write(json.dumps(r, ensure_ascii=False) + "\n")

    print(f"\nWrote {out_path}")
    print("Next: cd tablebench && python parse_tablebench_instruction_response_script.py")
    print("      python eval_tablebench_script.py")


if __name__ == "__main__":
    main()
