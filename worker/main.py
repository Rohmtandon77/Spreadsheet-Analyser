"""Job worker -- dequeues jobs from Redis and runs the analysis pipeline."""

import asyncio
import logging
import signal
import uuid

from sqlalchemy import select
from sqlalchemy.orm import selectinload

from backend.app.database import async_session, engine
from backend.app.models import Base, Job, JobStatus, Message, MessageRole
from backend.app.queue import close_redis, dequeue_job

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s %(levelname)-8s %(name)s  %(message)s",
)
log = logging.getLogger("worker")

_shutdown = False


def _handle_signal(signum, frame):
    global _shutdown
    log.info("Received signal %s, shutting down gracefully ...", signum)
    _shutdown = True


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
            last_user_msg = None
            for msg in reversed(job.messages):
                if msg.role == MessageRole.user:
                    last_user_msg = msg
                    break

            if last_user_msg is None:
                raise ValueError("No user message found for job")

            # --- Stub analysis (Phase 5 will replace this) ---
            answer_text = (
                f"[STUB] Received your question: \"{last_user_msg.content}\"\n"
                f"File: {job.original_filename} "
                f"({job.row_count} rows x {job.column_count} cols)\n"
                f"Analysis engine not yet implemented."
            )
            generated_code = None
            execution_output = None
            # --- End stub ---

            assistant_msg = Message(
                job_id=job_id,
                role=MessageRole.assistant,
                content=answer_text,
                code=generated_code,
                execution_output=execution_output,
            )
            session.add(assistant_msg)

            job.status = JobStatus.completed
            job.error = None
            await session.commit()
            log.info("Job %s completed", job_id)

        except Exception as e:
            log.exception("Job %s failed: %s", job_id, e)
            job.status = JobStatus.failed
            job.error = str(e)
            await session.commit()


async def run() -> None:
    """Main worker loop."""
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)

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
