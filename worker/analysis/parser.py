"""Parse model responses: strip reasoning tokens, extract code and answer."""

from __future__ import annotations

import re


def extract_thinking(text: str) -> str | None:
    """Extract the <think>...</think> reasoning content from DeepSeek-R1 output.

    Handles two patterns:
      1. <think>content</think>  -- standard
      2. content</think>         -- vLLM sometimes strips the opening tag
    """
    match = re.search(r"<think>(.*?)</think>", text, flags=re.DOTALL)
    if match:
        return match.group(1).strip() or None

    match = re.search(r"^(.*?)</think>", text, flags=re.DOTALL)
    if match:
        return match.group(1).strip() or None

    return None


def strip_think_tags(text: str) -> str:
    """Remove <think>...</think> reasoning blocks produced by DeepSeek-R1.

    Also handles the case where the opening <think> tag is missing.
    """
    text = re.sub(r"<think>.*?</think>", "", text, flags=re.DOTALL).strip()
    text = re.sub(r"^.*?</think>", "", text, flags=re.DOTALL).strip()
    return text


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


def parse_response(raw: str) -> tuple[str | None, str, str | None]:
    """
    Parse a full model response into (code, answer, thinking).

    Returns:
        code:     Python code to execute (or None if none found)
        answer:   Natural language summary of the result
        thinking: Raw chain-of-thought reasoning (or None)
    """
    thinking = extract_thinking(raw)
    clean = strip_think_tags(raw)
    code = extract_code(clean)
    answer = extract_answer(raw)
    return code, answer, thinking
