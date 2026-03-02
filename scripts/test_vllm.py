#!/usr/bin/env python3
"""Quick smoke test for the vLLM API server."""

import os
import sys

from openai import OpenAI

base_url = os.getenv("VLLM_BASE_URL", "http://localhost:8000/v1")
model = os.getenv("VLLM_MODEL", "deepseek-ai/DeepSeek-R1-Distill-Qwen-32B")

client = OpenAI(base_url=base_url, api_key="dummy")

print(f"Connecting to {base_url} ...")
try:
    models = client.models.list()
    print(f"Available models: {[m.id for m in models.data]}")
except Exception as e:
    print(f"Failed to list models: {e}", file=sys.stderr)
    sys.exit(1)

print(f"\nSending test prompt to {model} ...")
response = client.chat.completions.create(
    model=model,
    messages=[{"role": "user", "content": "What is 2 + 2? Reply in one sentence."}],
    max_tokens=64,
)
print(f"Response: {response.choices[0].message.content}")
print(f"Tokens: {response.usage.prompt_tokens} prompt, {response.usage.completion_tokens} completion")
