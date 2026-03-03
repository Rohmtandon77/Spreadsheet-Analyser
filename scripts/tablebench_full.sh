#!/usr/bin/env bash
# Full TableBench pipeline: run inference -> parse -> evaluate
set -e
ROOT="$(cd "$(dirname "$0")/.." && pwd)"
cd "$ROOT"
source .venv/bin/activate

echo "=== 1. Run inference (886 samples, ~4-5 hours) ==="
python scripts/run_tablebench.py

echo ""
echo "=== 2. Parse predictions ==="
cd tablebench && python parse_tablebench_instruction_response_script.py

echo ""
echo "=== 3. Evaluate ==="
python eval_tablebench_script.py

echo ""
echo "=== Results ==="
cat eval_examples/evaluation_results/llm_eval_type_results.csv
