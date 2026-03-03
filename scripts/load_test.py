#!/usr/bin/env python3
"""
Concurrent load test for the Spreadsheet Analysis Service.

Submits N jobs simultaneously and measures throughput.
"""

import argparse
import io
import time
from concurrent.futures import ThreadPoolExecutor, as_completed

import requests

API = "http://localhost:8080"

TEST_CSV = "month,revenue,expenses\nJan,10000,8000\nFeb,12000,9000\nMar,11000,8500\nApr,15000,10000\nMay,13000,9500\nJun,16000,11000\n"

QUESTIONS = [
    "What is the total revenue?",
    "Which month had the lowest expenses?",
    "What is the average profit margin?",
    "Which month had the highest revenue?",
    "What is the standard deviation of expenses?",
    "How many months had revenue above 12000?",
    "What is the total expenses across all months?",
    "Which month had the biggest difference between revenue and expenses?",
    "What percentage of total revenue comes from Jun?",
    "What is the median revenue?",
]


def submit_and_wait(question: str, timeout: int = 180) -> dict:
    """Submit a job and poll until completion."""
    start = time.time()

    files = {"file": ("test.csv", io.BytesIO(TEST_CSV.encode()), "text/csv")}
    data = {"question": question}
    r = requests.post(f"{API}/jobs", files=files, data=data)
    r.raise_for_status()
    job_id = r.json()["job_id"]

    while time.time() - start < timeout:
        r = requests.get(f"{API}/jobs/{job_id}/status")
        r.raise_for_status()
        status = r.json()["status"]
        if status in ("completed", "failed"):
            elapsed = time.time() - start
            return {"job_id": job_id, "status": status, "elapsed": elapsed, "question": question}
        time.sleep(2)

    return {"job_id": job_id, "status": "timeout", "elapsed": time.time() - start, "question": question}


def main():
    ap = argparse.ArgumentParser(description="Load test the analysis service")
    ap.add_argument("-n", "--num-jobs", type=int, default=5, help="Number of concurrent jobs")
    ap.add_argument("-w", "--max-workers", type=int, default=5, help="Thread pool size")
    args = ap.parse_args()

    n = args.num_jobs
    questions = [QUESTIONS[i % len(QUESTIONS)] for i in range(n)]

    print(f"Submitting {n} jobs with {args.max_workers} threads...")
    start = time.time()

    results = []
    with ThreadPoolExecutor(max_workers=args.max_workers) as pool:
        futures = {pool.submit(submit_and_wait, q): q for q in questions}
        for future in as_completed(futures):
            result = future.result()
            results.append(result)
            status_icon = "OK" if result["status"] == "completed" else "FAIL"
            print(f"  [{status_icon}] {result['elapsed']:.1f}s - {result['question'][:50]}")

    total = time.time() - start
    completed = sum(1 for r in results if r["status"] == "completed")
    failed = sum(1 for r in results if r["status"] == "failed")
    timed_out = sum(1 for r in results if r["status"] == "timeout")
    avg_time = sum(r["elapsed"] for r in results) / len(results)

    print(f"\n--- Results ---")
    print(f"Total time:  {total:.1f}s")
    print(f"Jobs:        {n} submitted, {completed} completed, {failed} failed, {timed_out} timed out")
    print(f"Avg latency: {avg_time:.1f}s per job")
    print(f"Throughput:  {completed / total:.2f} jobs/sec")


if __name__ == "__main__":
    main()
