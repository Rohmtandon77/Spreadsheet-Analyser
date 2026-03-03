#!/bin/bash
# Wait for tablebench inference to finish, then run parse + eval
set -e
cd /home/ubuntu/rohm-project
source .venv/bin/activate

echo "Waiting for run_tablebench.py to finish..."
while pgrep -f "run_tablebench.py" > /dev/null; do
    sleep 30
done

echo "Inference complete! Running parse + eval..."
echo "$(date): Starting parse step"

cd tablebench
python parse_tablebench_instruction_response_script.py 2>&1
echo "$(date): Parse complete"

python eval_tablebench_script.py 2>&1
echo "$(date): Eval complete"

echo ""
echo "=== RESULTS ==="
cat eval_examples/evaluation_results/llm_eval_type_results.csv
echo ""
echo "Done! Full results in tablebench/eval_examples/evaluation_results/"
