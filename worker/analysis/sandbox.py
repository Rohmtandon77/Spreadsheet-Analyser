"""Safe Python execution sandbox for model-generated analysis code."""

from __future__ import annotations

import subprocess
import sys
import tempfile
import textwrap
from dataclasses import dataclass, field
from pathlib import Path


@dataclass
class SandboxResult:
    success: bool
    stdout: str
    stderr: str
    chart_paths: list[Path] = field(default_factory=list)
    error: str = ""


_SANDBOX_PREAMBLE = textwrap.dedent("""\
    import os
    import sys
    import warnings
    warnings.filterwarnings('ignore')

    import pandas as pd
    import numpy as np
    import matplotlib
    matplotlib.use('Agg')
    import matplotlib.pyplot as plt
    import seaborn as sns
    from scipy import stats

    # Load the DataFrame
    _file_path = {file_path!r}
    _ext = os.path.splitext(_file_path)[1].lower()
    if _ext == '.csv':
        df = pd.read_csv(_file_path)
    else:
        df = pd.read_excel(_file_path)

""")


def run_code(
    code: str,
    file_path: Path,
    charts_dir: Path,
    timeout: int = 30,
) -> SandboxResult:
    """
    Execute model-generated code in a subprocess.

    - Runs with cwd=charts_dir so plt.savefig('name.png') saves there
    - Captures stdout/stderr
    - Detects new .png/.svg files in charts_dir after execution
    - Enforces a timeout
    """
    charts_before = set(charts_dir.glob("*.png")) | set(charts_dir.glob("*.svg"))

    preamble = _SANDBOX_PREAMBLE.format(file_path=str(file_path))
    full_script = preamble + "\n# --- Generated code ---\n" + code

    with tempfile.NamedTemporaryFile(
        mode="w", suffix=".py", delete=False, dir=charts_dir
    ) as tmp:
        tmp.write(full_script)
        script_path = tmp.name

    try:
        proc = subprocess.run(
            [sys.executable, script_path],
            capture_output=True,
            text=True,
            timeout=timeout,
            cwd=str(charts_dir),
        )
        success = proc.returncode == 0
        stdout = proc.stdout.strip()
        stderr = proc.stderr.strip()
        error = stderr if not success else ""
    except subprocess.TimeoutExpired:
        return SandboxResult(
            success=False,
            stdout="",
            stderr="",
            error=f"Code execution timed out after {timeout}s",
        )
    except Exception as e:
        return SandboxResult(success=False, stdout="", stderr="", error=str(e))
    finally:
        Path(script_path).unlink(missing_ok=True)

    charts_after = set(charts_dir.glob("*.png")) | set(charts_dir.glob("*.svg"))
    new_charts = sorted(charts_after - charts_before)

    return SandboxResult(
        success=success,
        stdout=stdout,
        stderr=stderr,
        chart_paths=new_charts,
        error=error,
    )
