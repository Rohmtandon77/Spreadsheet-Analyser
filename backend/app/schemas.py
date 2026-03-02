"""Pydantic schemas for API request/response models."""

import uuid
from datetime import datetime

from pydantic import BaseModel

from backend.app.models import ArtifactType, JobStatus, MessageRole


# ---------------------------------------------------------------------------
# Job
# ---------------------------------------------------------------------------

class JobCreate(BaseModel):
    """Not used directly as a JSON body -- the upload endpoint uses multipart form."""
    pass


class JobOut(BaseModel):
    id: uuid.UUID
    status: JobStatus
    original_filename: str
    file_size_bytes: int
    row_count: int | None = None
    column_count: int | None = None
    error: str | None = None
    created_at: datetime
    updated_at: datetime

    model_config = {"from_attributes": True}


class JobSubmitResponse(BaseModel):
    job_id: uuid.UUID


class JobStatusResponse(BaseModel):
    job_id: uuid.UUID
    status: JobStatus
    error: str | None = None


# ---------------------------------------------------------------------------
# Message
# ---------------------------------------------------------------------------

class MessageOut(BaseModel):
    id: uuid.UUID
    role: MessageRole
    content: str
    code: str | None = None
    execution_output: str | None = None
    created_at: datetime

    model_config = {"from_attributes": True}


# ---------------------------------------------------------------------------
# Artifact
# ---------------------------------------------------------------------------

class ArtifactOut(BaseModel):
    id: uuid.UUID
    type: ArtifactType
    filename: str
    file_path: str
    url: str | None = None  # set by the API from file_path
    mime_type: str
    message_id: uuid.UUID | None = None
    created_at: datetime

    model_config = {"from_attributes": True}


# ---------------------------------------------------------------------------
# Results (combined response)
# ---------------------------------------------------------------------------

class JobResultsResponse(BaseModel):
    job: JobOut
    messages: list[MessageOut]
    artifacts: list[ArtifactOut]
