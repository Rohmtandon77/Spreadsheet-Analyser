"""Analysis orchestrator: load data, call LLM, execute code, self-heal on error."""

from __future__ import annotations

import logging
from dataclasses import dataclass, field
from pathlib import Path

import pandas as pd
from openai import OpenAI

from backend.app.config import SANDBOX_MAX_RETRIES, SANDBOX_TIMEOUT_SECONDS, VLLM_BASE_URL, VLLM_MODEL
from backend.app.models import Message
from worker.analysis.parser import parse_response
from worker.analysis.prompt import build_error_retry_messages, build_messages
from worker.analysis.sandbox import SandboxResult, run_code

log = logging.getLogger("worker.analysis")

_client: OpenAI | None = None


def _get_client() -> OpenAI:
    global _client
    if _client is None:
        _client = OpenAI(base_url=VLLM_BASE_URL, api_key="dummy")
    return _client


@dataclass
class AnalysisResult:
    answer: str
    code: str | None
    execution_output: str
    chart_paths: list[Path] = field(default_factory=list)
    retries_used: int = 0


def load_dataframe(file_path: str) -> pd.DataFrame:
    path = Path(file_path)
    ext = path.suffix.lower()
    if ext == ".csv":
        return pd.read_csv(path)
    elif ext in (".xlsx", ".xls"):
        return pd.read_excel(path)
    else:
        raise ValueError(f"Unsupported file type: {ext}")


def _call_llm(messages: list[dict]) -> str:
    client = _get_client()
    response = client.chat.completions.create(
        model=VLLM_MODEL,
        messages=messages,
        max_tokens=4096,
        temperature=0.1,
    )
    return response.choices[0].message.content or ""


def run_analysis(
    file_path: str,
    charts_dir: Path,
    conversation: list[Message],
) -> AnalysisResult:
    """
    Run the full analysis pipeline:
    1. Load the DataFrame
    2. Build prompt from conversation history
    3. Call DeepSeek to generate analysis code
    4. Execute in sandbox
    5. Self-heal: retry up to SANDBOX_MAX_RETRIES times on execution error
    6. Return answer + code + execution output + chart paths
    """
    df = load_dataframe(file_path)
    messages = build_messages(df, conversation)

    code: str | None = None
    result: SandboxResult | None = None
    retries = 0
    raw_response = ""

    for attempt in range(SANDBOX_MAX_RETRIES + 1):
        log.info("LLM call attempt %d/%d", attempt + 1, SANDBOX_MAX_RETRIES + 1)
        raw_response = _call_llm(messages)

        code, answer = parse_response(raw_response)

        if code is None:
            log.warning("No code block found in response, returning text answer only")
            return AnalysisResult(
                answer=answer or raw_response,
                code=None,
                execution_output="",
                retries_used=attempt,
            )

        log.info("Executing generated code (timeout=%ds)", SANDBOX_TIMEOUT_SECONDS)
        result = run_code(
            code=code,
            file_path=Path(file_path),
            charts_dir=charts_dir,
            timeout=SANDBOX_TIMEOUT_SECONDS,
        )

        if result.success:
            log.info(
                "Code executed successfully, %d chart(s) generated",
                len(result.chart_paths),
            )
            # Prefer stdout as the answer if it exists, else use model text
            final_answer = result.stdout if result.stdout else answer
            return AnalysisResult(
                answer=final_answer,
                code=code,
                execution_output=result.stdout,
                chart_paths=result.chart_paths,
                retries_used=attempt,
            )

        retries += 1
        log.warning("Code execution failed (attempt %d): %s", attempt + 1, result.error)

        if attempt < SANDBOX_MAX_RETRIES:
            log.info("Requesting fix from model ...")
            messages = build_error_retry_messages(messages, code, result.error)

    # All retries exhausted
    log.error("Analysis failed after %d attempts", SANDBOX_MAX_RETRIES + 1)
    _, answer = parse_response(raw_response)
    return AnalysisResult(
        answer=(
            f"I was unable to compute the answer due to a code execution error.\n\n"
            f"Error: {result.error if result else 'unknown'}\n\n"
            f"My analysis: {answer}"
        ),
        code=code,
        execution_output=result.stderr if result else "",
        retries_used=retries,
    )
