"""File storage helpers -- saving uploads and creating job directories."""

import shutil
import uuid
from pathlib import Path

from fastapi import UploadFile

from backend.app.config import DATA_DIR, UPLOAD_MAX_SIZE_MB

ALLOWED_EXTENSIONS = {".csv", ".xlsx", ".xls"}
MAX_BYTES = UPLOAD_MAX_SIZE_MB * 1024 * 1024


def job_dir(job_id: uuid.UUID) -> Path:
    return DATA_DIR / "jobs" / str(job_id)


def ensure_job_dirs(job_id: uuid.UUID) -> dict[str, Path]:
    """Create the standard directory layout for a job and return the paths."""
    base = job_dir(job_id)
    dirs = {
        "root": base,
        "input": base / "input",
        "outputs": base / "outputs",
        "charts": base / "charts",
        "logs": base / "logs",
    }
    for d in dirs.values():
        d.mkdir(parents=True, exist_ok=True)
    return dirs


async def save_upload(file: UploadFile, job_id: uuid.UUID) -> tuple[Path, int]:
    """
    Save an uploaded file into the job's input/ directory.

    Returns (saved_path, size_in_bytes).
    Raises ValueError on invalid extension or oversized file.
    """
    if not file.filename:
        raise ValueError("Uploaded file has no filename.")

    ext = Path(file.filename).suffix.lower()
    if ext not in ALLOWED_EXTENSIONS:
        raise ValueError(
            f"Unsupported file type '{ext}'. Allowed: {', '.join(sorted(ALLOWED_EXTENSIONS))}"
        )

    dirs = ensure_job_dirs(job_id)
    dest = dirs["input"] / f"upload{ext}"

    size = 0
    with open(dest, "wb") as f:
        while chunk := await file.read(1024 * 1024):
            size += len(chunk)
            if size > MAX_BYTES:
                dest.unlink(missing_ok=True)
                raise ValueError(
                    f"File exceeds {UPLOAD_MAX_SIZE_MB} MB limit."
                )
            f.write(chunk)

    return dest, size


def delete_job_data(job_id: uuid.UUID) -> None:
    """Remove all on-disk data for a job."""
    path = job_dir(job_id)
    if path.exists():
        shutil.rmtree(path)
