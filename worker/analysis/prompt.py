"""Prompt construction for the spreadsheet analysis engine."""

from __future__ import annotations

import pandas as pd

from backend.app.models import Message, MessageRole

SYSTEM_PROMPT = """\
You are a data analysis assistant. You are given a pandas DataFrame `df` (already loaded) \
and a question about it. Write Python code to answer the question accurately.

Rules:
- Write Python code that operates on `df`, which is already defined.
- Allowed libraries: pandas, numpy, matplotlib, seaborn, scipy.
- To save a chart, call plt.savefig('chart_name.png', dpi=100, bbox_inches='tight'). Do NOT call plt.show().
- The very last print() in your code MUST output only the final answer value — a number, name, or short phrase. Do NOT print the entire DataFrame or intermediate results.
- Round numerical answers to 2 decimal places unless the question specifies otherwise.
- For yes/no or true/false questions, print only "Yes" or "No".
- Never fabricate data — always compute from df.
- Handle dirty data: use pd.to_numeric(errors='coerce') when converting columns that may contain non-numeric strings. Use .dropna() or .fillna() as appropriate.
- If a column looks numeric but has non-number entries (e.g. "Current", "N/A", "-"), coerce them rather than crashing.

Respond with:
1. A ```python code block containing your analysis code.
2. A brief natural-language answer (1-2 sentences) after the code block.
3. End with exactly: Final Answer: <value>

The Final Answer must be the very last line. Use a number or short entity name only, no explanation.
"""


MAX_SCHEMA_COLS_FOR_STATS = 10
MAX_SAMPLE_ROWS = 3
MAX_CONVERSATION_TURNS = 6


def build_schema_summary(df: pd.DataFrame) -> str:
    """Describe the DataFrame so the model can reason about its structure."""
    lines = [
        f"Shape: {df.shape[0]} rows x {df.shape[1]} columns",
        "",
        "Columns and types:",
    ]
    for col, dtype in df.dtypes.items():
        null_count = int(df[col].isna().sum())
        unique_count = int(df[col].nunique())
        info = f"  - {col!r} ({dtype}, {unique_count} unique"
        if null_count:
            info += f", {null_count} nulls"
        info += ")"
        if unique_count <= 12 and dtype == "object":
            vals = df[col].dropna().unique()[:12].tolist()
            info += f" values: {vals}"
        lines.append(info)

    lines += ["", "Sample data:", df.head(MAX_SAMPLE_ROWS).to_markdown(index=False)]

    num_cols = df.select_dtypes(include="number")
    if not num_cols.empty:
        subset = num_cols.iloc[:, :MAX_SCHEMA_COLS_FOR_STATS]
        desc = subset.describe().round(2)
        lines += ["", "Numeric column statistics:", desc.to_markdown()]
        if num_cols.shape[1] > MAX_SCHEMA_COLS_FOR_STATS:
            lines.append(f"  ... and {num_cols.shape[1] - MAX_SCHEMA_COLS_FOR_STATS} more numeric columns")

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

    recent = conversation[-MAX_CONVERSATION_TURNS:] if len(conversation) > MAX_CONVERSATION_TURNS else conversation
    for msg in recent:
        if msg.role == MessageRole.user:
            messages.append({"role": "user", "content": msg.content})
        elif msg.role == MessageRole.assistant:
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
