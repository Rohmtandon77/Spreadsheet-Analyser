"""Prompt construction for the spreadsheet analysis engine."""

from __future__ import annotations

import pandas as pd

from backend.app.models import Message, MessageRole

SYSTEM_PROMPT = """\
You are a data analysis assistant. You are given a pandas DataFrame `df` (already loaded) \
and a question about it. Your job is to write Python code to answer the question accurately.

Rules:
- Write Python code that operates on `df`, which is already defined
- Allowed libraries: pandas, numpy, matplotlib, seaborn, scipy
- To save a chart, call plt.savefig('chart_name.png') — do NOT call plt.show()
- Always print your final answer using print() so it appears in stdout
- Never fabricate data or numbers — always compute from df
- Keep code focused and correct

Respond with:
1. A ```python code block containing your analysis code
2. A brief natural-language answer summarising what you found (after the code block)
3. End with exactly one line: Final Answer: <value>

The Final Answer line must be the last line of your response. Use a number or short entity name, no explanation.
"""


def build_schema_summary(df: pd.DataFrame) -> str:
    """Describe the DataFrame so the model can reason about its structure."""
    lines = [
        f"Shape: {df.shape[0]} rows x {df.shape[1]} columns",
        "",
        "Columns and types:",
    ]
    for col, dtype in df.dtypes.items():
        null_count = df[col].isna().sum()
        lines.append(f"  - {col!r} ({dtype}){f', {null_count} nulls' if null_count else ''}")

    lines += ["", "Sample data (first 5 rows):", df.head(5).to_markdown(index=False)]
    return "\n".join(lines)


def build_messages(
    df: pd.DataFrame,
    conversation: list[Message],
) -> list[dict]:
    """
    Build the OpenAI-compatible messages list for a full conversation.

    The system prompt and DataFrame schema are prepended to every request.
    Prior turns (user questions + assistant code/answers) are included for
    multi-turn context.
    """
    schema = build_schema_summary(df)
    system_content = f"{SYSTEM_PROMPT}\n\nDataFrame schema:\n{schema}"

    messages: list[dict] = [{"role": "system", "content": system_content}]

    for msg in conversation:
        if msg.role == MessageRole.user:
            messages.append({"role": "user", "content": msg.content})
        elif msg.role == MessageRole.assistant:
            # Include prior code + answer so the model has full context
            parts = []
            if msg.code:
                parts.append(f"```python\n{msg.code}\n```")
            if msg.content:
                parts.append(msg.content)
            messages.append({"role": "assistant", "content": "\n\n".join(parts)})

    return messages


def build_error_retry_messages(
    messages: list[dict],
    failed_code: str,
    error: str,
) -> list[dict]:
    """Append a user message asking the model to fix a code error."""
    retry_messages = list(messages)
    retry_messages.append({
        "role": "assistant",
        "content": f"```python\n{failed_code}\n```",
    })
    retry_messages.append({
        "role": "user",
        "content": (
            f"That code produced an error:\n\n```\n{error}\n```\n\n"
            "Please fix the code and try again."
        ),
    })
    return retry_messages
