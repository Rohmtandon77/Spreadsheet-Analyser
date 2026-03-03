"""Job worker -- dequeues jobs from Redis and runs the analysis pipeline."""

import asyncio
import logging
import mimetypes
import signal
import uuid
from datetime import datetime, timedelta, timezone
from pathlib import Path

from sqlalchemy import select, update
from sqlalchemy.orm import selectinload

from backend.app.database import async_session, engine
from backend.app.models import Artifact, ArtifactType, Base, Job, JobStatus, Message, MessageRole
from backend.app.queue import close_redis, dequeue_job, enqueue_job
from backend.app.storage import job_dir
from worker.analysis.engine import run_analysis

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s %(levelname)-8s %(name)s  %(message)s",
)
log = logging.getLogger("worker")

STUCK_JOB_THRESHOLD_MINUTES = 5

_shutdown = False


def _handle_signal(signum, frame):
    global _shutdown
    log.info("Received signal %s, shutting down gracefully ...", signum)
    _shutdown = True


def _artifact_type_for(path: Path) -> ArtifactType:
    ext = path.suffix.lower()
    if ext in (".png", ".svg"):
        return ArtifactType.chart
    if ext in (".csv",):
        return ArtifactType.table
    return ArtifactType.processed_file


async def process_job(job_id: uuid.UUID) -> None:
    """Process a single job: load context, run analysis, persist results."""
    async with async_session() as session:
        stmt = (
            select(Job)
            .where(Job.id == job_id)
            .options(selectinload(Job.messages))
        )
        result = await session.execute(stmt)
        job = result.scalar_one_or_none()

        if job is None:
            log.warning("Job %s not found in DB, skipping", job_id)
            return

        job.status = JobStatus.processing
        await session.commit()
        log.info("Processing job %s (file: %s)", job_id, job.original_filename)

        try:
            charts_dir = job_dir(job_id) / "charts"
            charts_dir.mkdir(parents=True, exist_ok=True)

            analysis = await asyncio.get_event_loop().run_in_executor(
                None,
                run_analysis,
                job.file_path,
                charts_dir,
                list(job.messages),
            )

            if analysis.retries_used:
                log.info("Job %s required %d retry/retries", job_id, analysis.retries_used)

            assistant_msg = Message(
                job_id=job_id,
                role=MessageRole.assistant,
                content=analysis.answer,
                thinking=analysis.thinking,
                code=analysis.code,
                execution_output=analysis.execution_output,
            )
            session.add(assistant_msg)
            await session.flush()  # get assistant_msg.id before adding artifacts

            for chart_path in analysis.chart_paths:
                mime, _ = mimetypes.guess_type(str(chart_path))
                artifact = Artifact(
                    job_id=job_id,
                    message_id=assistant_msg.id,
                    type=_artifact_type_for(chart_path),
                    filename=chart_path.name,
                    file_path=str(chart_path),
                    mime_type=mime or "application/octet-stream",
                )
                session.add(artifact)

            job.status = JobStatus.completed
            job.error = None
            await session.commit()
            log.info(
                "Job %s completed (%d chart(s))",
                job_id,
                len(analysis.chart_paths),
            )

        except Exception as e:
            log.exception("Job %s failed: %s", job_id, e)
            job.status = JobStatus.failed
            job.error = str(e)
            await session.commit()


async def recover_stuck_jobs() -> None:
    """Reset jobs stuck in 'processing' for too long and re-enqueue them."""
    cutoff = datetime.now(timezone.utc) - timedelta(minutes=STUCK_JOB_THRESHOLD_MINUTES)
    async with async_session() as session:
        stmt = (
            select(Job)
            .where(Job.status == JobStatus.processing)
            .where(Job.updated_at < cutoff)
        )
        result = await session.execute(stmt)
        stuck_jobs = result.scalars().all()
        for job in stuck_jobs:
            log.warning("Recovering stuck job %s (stuck since %s)", job.id, job.updated_at)
            job.status = JobStatus.pending
            job.error = None
        await session.commit()

    for job in stuck_jobs:
        await enqueue_job(job.id)

    if stuck_jobs:
        log.info("Recovered %d stuck job(s)", len(stuck_jobs))


async def run() -> None:
    """Main worker loop."""
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)

    await recover_stuck_jobs()
    log.info("Worker started, polling for jobs ...")

    while not _shutdown:
        job_id = await dequeue_job(timeout=2)
        if job_id is not None:
            await process_job(job_id)

    await close_redis()
    await engine.dispose()
    log.info("Worker shut down cleanly.")


if __name__ == "__main__":
    signal.signal(signal.SIGINT, _handle_signal)
    signal.signal(signal.SIGTERM, _handle_signal)
    asyncio.run(run())
