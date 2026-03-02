"""Job management endpoints: submit, status, results."""

import uuid

import pandas as pd
from fastapi import APIRouter, Depends, File, Form, HTTPException, UploadFile
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from backend.app.database import get_session
from backend.app.models import Artifact, Job, JobStatus, Message, MessageRole
from backend.app.schemas import (
    ArtifactOut,
    JobOut,
    JobResultsResponse,
    JobStatusResponse,
    JobSubmitResponse,
    MessageOut,
)
from backend.app.storage import save_upload

router = APIRouter(prefix="/jobs", tags=["jobs"])


@router.post("", response_model=JobSubmitResponse, status_code=201)
async def submit_job(
    file: UploadFile = File(...),
    question: str = Form(...),
    session: AsyncSession = Depends(get_session),
):
    """Upload a spreadsheet and ask a question. Returns a job_id immediately."""
    job_id = uuid.uuid4()

    try:
        file_path, file_size = await save_upload(file, job_id)
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))

    # Parse basic metadata from the file
    row_count, col_count = None, None
    try:
        ext = file_path.suffix.lower()
        if ext == ".csv":
            df = pd.read_csv(file_path, nrows=0)
            row_count = sum(1 for _ in open(file_path)) - 1
        else:
            df = pd.read_excel(file_path, nrows=0)
            row_count = len(pd.read_excel(file_path))
        col_count = len(df.columns)
    except Exception:
        pass

    job = Job(
        id=job_id,
        status=JobStatus.pending,
        original_filename=file.filename or "unknown",
        file_path=str(file_path),
        file_size_bytes=file_size,
        row_count=row_count,
        column_count=col_count,
    )
    session.add(job)

    initial_message = Message(
        job_id=job_id,
        role=MessageRole.user,
        content=question,
    )
    session.add(initial_message)

    await session.commit()

    # TODO (Phase 4): enqueue job_id to Redis here

    return JobSubmitResponse(job_id=job_id)


@router.get("/{job_id}/status", response_model=JobStatusResponse)
async def get_job_status(
    job_id: uuid.UUID,
    session: AsyncSession = Depends(get_session),
):
    """Check the current status of a job."""
    job = await session.get(Job, job_id)
    if not job:
        raise HTTPException(status_code=404, detail="Job not found")
    return JobStatusResponse(job_id=job.id, status=job.status, error=job.error)


@router.get("/{job_id}/results", response_model=JobResultsResponse)
async def get_job_results(
    job_id: uuid.UUID,
    session: AsyncSession = Depends(get_session),
):
    """Retrieve the full results for a job: metadata, conversation, and artifacts."""
    stmt = (
        select(Job)
        .where(Job.id == job_id)
        .options(selectinload(Job.messages), selectinload(Job.artifacts))
    )
    result = await session.execute(stmt)
    job = result.scalar_one_or_none()
    if not job:
        raise HTTPException(status_code=404, detail="Job not found")

    return JobResultsResponse(
        job=JobOut.model_validate(job),
        messages=[MessageOut.model_validate(m) for m in job.messages],
        artifacts=[ArtifactOut.model_validate(a) for a in job.artifacts],
    )
