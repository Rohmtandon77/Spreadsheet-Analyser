Just some things I copied and pasted from the chat - definitely needs to be made proper, whole, and refined later.

Model: DeepSeek-R1-Distill-Qwen-32B -- reasoning model, strong at code gen, fits on 4x H100 with tp=4
Serving: vLLM with tensor-parallel=4, max-model-len=8192
Analysis approach: code generation + subprocess execution (vs. function-calling or direct LLM answers)
Sandbox: subprocess with timeout (vs. Docker container -- simpler, sufficient for now)
Queue: Redis LPUSH/BRPOP (vs. Celery -- lightweight, no extra overhead)
DB: Postgres + async SQLAlchemy (vs. SQLite -- supports concurrent workers)
Self-heal: feed traceback back to model, up to 2 retries
Prompt design: include full schema + sample rows + conversation history (not the entire dataset)
GPU allocation: 0-3 for LLM, 4-7 reserved for STT/TTS/overflow
TTS: Piper (local, en_US-ryan-high) — no external APIs, assignment-compliant; quality comparable to cloud

During phase 7
I'll go with plain HTML + vanilla JS -- no build step, no npm, just a single-page app served from FastAPI. Keeps it simple and dependency-free.