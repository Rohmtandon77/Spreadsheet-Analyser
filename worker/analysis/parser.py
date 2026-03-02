"""Parse model responses: strip reasoning tokens, extract code and answer."""

from __future__ import annotations

import re


def strip_think_tags(text: str) -> str:
    """Remove <think>...</think> reasoning blocks produced by DeepSeek-R1."""
    return re.sub(r"<think>.*?</think>", "", text, flags=re.DOTALL).strip()


def extract_code(text: str) -> str | None:
    """Extract the first Python code block from the response."""
    # Match ```python ... ``` or ``` ... ```
    match = re.search(r"```(?:python)?\s*\n(.*?)```", text, re.DOTALL)
    if match:
        return match.group(1).strip()
    return None


def extract_answer(text: str) -> str:
    """
    Extract the natural language answer from the response.

    Strips think tags, then removes code blocks, leaving only the
    human-readable explanation.
    """
    text = strip_think_tags(text)
    # Remove all code blocks
    text = re.sub(r"```(?:python)?\s*\n.*?```", "", text, flags=re.DOTALL)
    return text.strip()


def parse_response(raw: str) -> tuple[str | None, str]:
    """
    Parse a full model response into (code, answer).

    Returns:
        code:   Python code to execute (or None if none found)
        answer: Natural language summary of the result
    """
    clean = strip_think_tags(raw)
    code = extract_code(clean)
    answer = extract_answer(raw)
    return code, answer
