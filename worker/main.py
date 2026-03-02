"""Job processor -- dequeues jobs from Redis and runs the analysis pipeline."""

import asyncio
import logging

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
log = logging.getLogger(__name__)


async def run():
    log.info("Worker started, waiting for jobs ...")
    # TODO: connect to Redis, dequeue job_ids, run analysis engine
    while True:
        await asyncio.sleep(1)


if __name__ == "__main__":
    asyncio.run(run())
