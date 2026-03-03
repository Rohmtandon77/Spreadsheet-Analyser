# Design Decisions & Trade-offs

This document captures the key architectural and technical decisions made during the development of the Spreadsheet Analysis Service, along with alternatives considered and rationale.

---

## 1. Model Choice

**Decision**: DeepSeek-R1-Distill-Qwen-32B

**Alternatives considered**:
- Llama 3 70B -- better general performance but too large for 4x H100 with reasonable context length.
- Qwen-2.5-Coder-32B -- strong coder but lacks the chain-of-thought reasoning that improves data analysis accuracy.
- Smaller models (7B-14B) -- faster but significantly worse at multi-step numerical reasoning.

**Rationale**: DeepSeek-R1-Distill-Qwen-32B combines strong code generation with chain-of-thought reasoning (via `<think>` tags). At 32B parameters, it fits on 4 GPUs with tensor parallelism, leaving headroom for other services. The reasoning traces improve accuracy on numerical and multi-step questions -- critical for spreadsheet analysis.

---

## 2. Serving Framework

**Decision**: vLLM with tensor-parallel-size=4, max-model-len=8192, max_tokens=2048

**Alternatives considered**:
- TGI (Text Generation Inference) -- strong but less flexible batching.
- Direct HuggingFace transformers -- no request batching, much lower throughput.
- Ollama -- simpler setup but no tensor parallelism for large models.

**Rationale**: vLLM provides automatic continuous batching (handles concurrent requests efficiently), PagedAttention for memory efficiency, and native tensor parallelism. The OpenAI-compatible API means the worker code is framework-agnostic -- switching models or serving frameworks requires zero code changes. We set `max_tokens=2048` (output) to leave 6144 tokens for input (system prompt + schema + conversation history). The schema summary is capped (3 sample rows, 10 numeric columns for stats) and conversation history is trimmed to the last 6 messages to prevent context window overflow on large datasets with many follow-ups.

---

## 3. Analysis Architecture

**Decision**: Code generation + subprocess execution (LLM writes Python, we execute it in a sandbox).

**Alternatives considered**:
- Direct LLM answers (no code) -- unreliable for numerical computation; LLMs hallucinate numbers.
- Function-calling / tool-use -- restricts the model to predefined operations; can't handle arbitrary analysis.
- ReAct agent with tools -- adds complexity and latency with multiple LLM round-trips per question.

**Rationale**: Code generation gives the model full expressiveness (any pandas/matplotlib operation) while keeping results verifiable -- the executed code produces deterministic outputs. The self-healing retry loop (feed error tracebacks back to the model, up to 2 retries) handles the majority of first-attempt failures without human intervention.

---

## 4. Sandbox Design

**Decision**: subprocess.run() with timeout, restricted to a temp directory.

**Alternatives considered**:
- Docker container per execution -- stronger isolation but significant overhead (container spin-up, image management).
- RestrictedPython / exec() -- runs in-process, risks crashing the worker.
- AWS Lambda / cloud sandbox -- external dependency, adds latency and cost.

**Rationale**: subprocess isolation is lightweight (~100ms overhead) and sufficient for our threat model (the LLM generates code, not untrusted users). The 30-second timeout prevents infinite loops. The code runs in a temp directory with only the uploaded data file, limiting filesystem access. For a production system with user-submitted code, Docker would be necessary.

---

## 5. Queue & Database

**Decision**: Redis (LPUSH/BRPOP) for job queuing + PostgreSQL with async SQLAlchemy for persistence.

**Alternatives considered**:
- Celery + RabbitMQ -- full-featured but heavy; brings in multiple dependencies for what's essentially a FIFO queue.
- SQLite -- simpler but doesn't support concurrent writer access needed for multiple workers.
- In-memory queue -- lost on restart, can't scale to multiple workers.

**Rationale**: Redis BRPOP gives us a worker-safe, distributed queue in one command. Multiple workers can poll the same queue without coordination. PostgreSQL handles concurrent reads/writes from the API and worker(s) reliably. Alembic manages schema migrations for safe evolution.

---

## 6. Voice Pipeline

**Decision**: faster-whisper (GPU 4) for STT, Piper TTS (CPU) for speech synthesis.

**Alternatives considered**:
- OpenAI Whisper API -- external dependency, not assignment-compliant ("should not communicate with any external service or LLM").
- Edge TTS -- originally implemented, but uses Microsoft's cloud API. Replaced with Piper for full locality.
- Bark / XTTS -- higher quality but extremely slow on CPU and require GPU memory.

**Rationale**: faster-whisper provides CTranslate2-optimised Whisper inference, running the large-v3 model on a dedicated GPU (index 4) for real-time transcription. Piper TTS runs on CPU because it's ONNX-based and fast enough (~0.5s for a sentence) -- using a GPU for TTS would waste VRAM with negligible latency improvement given Piper's architecture. The en_US-ryan-high voice provides clear, natural-sounding output.

---

## 7. Frontend Architecture

**Decision**: Single-page vanilla HTML/CSS/JS, served by FastAPI's StaticFiles.

**Alternatives considered**:
- React / Vue / Svelte -- better for complex UIs but adds a build step, node_modules, and deployment complexity.
- Gradio -- quick prototyping but limited customisation and opinionated styling.
- Streamlit -- Python-native but server-side rendering isn't ideal for real-time polling.

**Rationale**: A single `index.html` with no build tools means zero frontend dependencies, instant hot-reload, and simple deployment. The UI requirements (file upload, text input, status polling, message display, charts) don't need a component framework.

---

## 7a. Frontend Design & UX Decisions

**Branding & Colour scheme**: The app is branded "SpreadX". We iterated through several themes (dark blue → dark green → light faded green → soft beige) based on user feedback. The final palette uses a soft beige background (#f0ece4) for the page, with blue-grey panels (#1e2a3a, #253545) for the sidebar and content cards, and teal/cyan accents (#5eead4, #0ea5e9) for interactive states. The title is dark grey (#3a3f47) for readability on the light background.

**Sticky top bar**: The SpreadX title, subtitle, and Conversation Mode toggle sit in a `position: sticky` bar that stays pinned during scroll. A flex spacer ensures the title stays visually centred between the toggle and the left edge.

**Message layout**: Rather than a single monolithic chat rectangle with internal scroll, each message (user question, assistant answer) is rendered as an independent rounded card with spacing between them. The entire main column scrolls, not an inner container. This gives a cleaner, more modern feel and avoids the "trapped in a box" experience.

**Collapsible sections**: The LLM's chain-of-thought reasoning (`<think>` tags), generated code, and execution output are wrapped in collapsible `<details>` sections. The "Final Answer" is displayed prominently. This keeps the UI clean while still making all details accessible.

**Job history sidebar**: A left-hand sidebar shows past jobs (filename, first question, status, timestamp) in rounded "bubble" cards. It defaults to showing 5 items with a "Show X more" expander. Jobs can be deleted via an × button (appears on hover). A "New Chat" button resets to the upload screen. The current job ID is persisted in `localStorage` for cross-refresh continuity.

**Conversation mode**: A toggleable mode (pill button in the top bar) that, when active, enables voice-driven workflows -- mic input auto-submits questions and answers are auto-spoken via TTS. When off, per-answer mic buttons provide on-demand playback. TTS playback is tracked globally so re-clicking stops the current audio (no double-play).

**Inline loading**: When a job is processing, an "Analyzing..." card with a spinner appears at the bottom of the message list (not just in the header), auto-scrolling to stay visible. This is more intuitive than a status indicator at the top of the page.

**Drag-and-drop upload**: The file upload zone supports both click-to-browse and drag-and-drop, with visual feedback (border highlight, file name display). Accepted formats are CSV and Excel.

---

## 8. Evaluation

**Decision**: TableBench (DP subset, 100 samples) with ROUGE-L and exact-match metrics.

**Alternatives considered**:
- Custom evaluation set -- more relevant but not standardised; hard to compare.
- Full TableBench (4000+ samples) -- would take ~20+ hours with single worker; ran 100-sample subset for practical evaluation.

**Rationale**: TableBench is a published benchmark specifically for table analysis with LLMs, covering fact-checking, numerical reasoning, data analysis, and visualisation. Running 100 diverse samples gives a reliable signal. Our score of 60% overall exceeds the 57% target, with the prompt tuning (Phase 11D) specifically addressing the numerical reasoning failure modes found during evaluation.

---

## 9. Scalability

**Decision**: Horizontal worker scaling via Redis BRPOP + stuck job recovery.

Workers are stateless -- launching N instances gives N concurrent processing slots. Redis BRPOP atomically dequeues one job per worker, preventing double-processing. On startup, each worker sweeps for jobs stuck in "processing" for >5 minutes (crashed worker recovery) and re-enqueues them.

vLLM handles LLM-side batching automatically -- multiple workers sending concurrent requests to vLLM get batched into a single forward pass. With 4x H100s and `max-model-len=8192`, vLLM's KV cache can comfortably hold 20-30 concurrent sequences, meaning we could run 20-30 workers if needed. Our current deployment uses 4 workers, which is sufficient for our use case. Scaling to 8 workers would only increase per-job latency by roughly 15-25% (e.g. ~13s to ~16-18s) due to shared GPU compute in batch inference -- a negligible tradeoff given that it doubles throughput and halves queue wait time. Adding more workers requires no code changes; it's purely a deployment-time decision (`nohup python -m worker.main &`).
