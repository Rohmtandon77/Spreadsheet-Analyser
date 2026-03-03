# SpreadX — Spreadsheet Analysis Service

An end-to-end system for analysing spreadsheet data using a locally-served open-source LLM. Upload a CSV or Excel file, ask questions in natural language, and get computed answers with charts -- via a Web UI, CLI, or REST API.

## Architecture

```
                    ┌──────────────┐
   Web UI / CLI ──► │  FastAPI API  │──► Static Files (/files)
                    │  :8080        │
                    └──────┬───────┘
                           │ enqueue (Redis LPUSH)
                    ┌──────▼───────┐
                    │    Redis     │  job queue
                    └──────┬───────┘
                           │ dequeue (BRPOP)
                    ┌──────▼───────┐
                    │    Worker    │  analysis pipeline
                    │              │
                    │  ┌─────────┐ │
                    │  │ Prompt  │ │  build messages + schema
                    │  └────┬────┘ │
                    │  ┌────▼────┐ │
                    │  │  vLLM   │ │  DeepSeek-R1-Distill-Qwen-32B (GPUs 0-3)
                    │  └────┬────┘ │
                    │  ┌────▼────┐ │
                    │  │ Sandbox │ │  execute generated Python code
                    │  └─────────┘ │
                    └──────┬───────┘
                           │ results + charts
                    ┌──────▼───────┐
                    │  PostgreSQL  │  jobs, messages, artifacts
                    └──────────────┘
```

**Voice pipeline**: Whisper large-v3 (GPU 4) for STT, Piper TTS (CPU) for speech output.

## GPU Allocation

| GPUs | Service |
|------|---------|
| 0-3  | DeepSeek-R1-Distill-Qwen-32B via vLLM (tensor-parallel=4) |
| 4    | Whisper large-v3 (faster-whisper, STT) |
| 5-7  | Free / overflow |
| CPU  | Piper TTS (en_US-ryan-high) |

## Prerequisites

- Python 3.10+
- PostgreSQL (running on localhost:5432)
- Redis (running on localhost:6379)
- NVIDIA GPUs with CUDA (H100 recommended)
- vLLM serving DeepSeek-R1-Distill-Qwen-32B

## Quick Start

```bash
# 1. Clone and set up
git clone https://github.com/Rohmtandon77/Spreadsheet-Analyser.git
cd Spreadsheet-Analyser
python -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt

# 2. Start vLLM (in a separate terminal)
python -m vllm.entrypoints.openai.api_server \
  --model deepseek-ai/DeepSeek-R1-Distill-Qwen-32B \
  --tensor-parallel-size 4 \
  --max-model-len 8192 \
  --dtype bfloat16

# 3. Start the API
uvicorn backend.app.main:app --host 0.0.0.0 --port 8080

# 4. Start the worker
python -m worker.main
```

## Usage

### Web UI

Open `http://localhost:8080` in a browser. Upload a spreadsheet, type a question, and get results with charts.

Port forward if accessing remotely: `ssh -L 9090:localhost:8080 your-server -N`, then open `http://localhost:9090`.

### CLI

```bash
# One-shot: submit + poll + results
./sa ask -f data.csv -q "What is the total revenue?"

# Step-by-step
./sa submit -f data.csv -q "What is the average?"
./sa status <job_id>
./sa results <job_id>
./sa results <job_id> --download-charts

# Follow-up
./sa followup <job_id> -q "Break that down by month"
```

### REST API

Interactive docs at `http://localhost:8080/docs` (Swagger UI).

Key endpoints:

| Method | Path | Description |
|--------|------|-------------|
| GET    | `/jobs` | List recent jobs |
| POST   | `/jobs` | Submit file + question |
| GET    | `/jobs/{id}/status` | Check job status |
| GET    | `/jobs/{id}/results` | Get full results |
| POST   | `/jobs/{id}/followup` | Ask follow-up |
| DELETE | `/jobs/{id}` | Delete a job |
| POST   | `/voice/stt` | Speech-to-text |
| POST   | `/voice/tts` | Text-to-speech |

### Voice / Conversation Mode

The Web UI has a **Conversation Mode** toggle (top bar). When enabled, mic buttons auto-submit questions and answers are auto-spoken via TTS. When disabled, per-answer mic buttons provide on-demand playback. Both STT (Whisper) and TTS (Piper) run fully locally -- no external API calls.

## Evaluation (TableBench)

```bash
# Run inference on TableBench (100 samples, ~45min)
python scripts/run_tablebench.py --limit 100

# Parse and evaluate
cd tablebench
python parse_tablebench_instruction_response_script.py
python eval_tablebench_script.py
cat eval_examples/evaluation_results/llm_eval_type_results.csv
```

**Score (100 samples)**: 60.0% overall (target: >= 57%).

## Configuration

All settings are env-configurable (see `.env.example`):

| Variable | Default | Description |
|----------|---------|-------------|
| `VLLM_BASE_URL` | `http://localhost:8000/v1` | vLLM API endpoint |
| `VLLM_MODEL` | `deepseek-ai/DeepSeek-R1-Distill-Qwen-32B` | Model name |
| `POSTGRES_HOST` | `localhost` | PostgreSQL host |
| `REDIS_HOST` | `localhost` | Redis host |
| `DATA_DIR` | `./data` | Storage directory for uploads/outputs |
| `UPLOAD_MAX_SIZE_MB` | `50` | Max upload file size |
| `SANDBOX_TIMEOUT_SECONDS` | `30` | Code execution timeout |
| `SANDBOX_MAX_RETRIES` | `2` | Self-heal retry count |
| `WHISPER_MODEL_SIZE` | `large-v3` | Whisper model |
| `WHISPER_DEVICE_INDEX` | `4` | GPU for Whisper |
| `PIPER_VOICE_ID` | `en_US-ryan-high` | Piper TTS voice |

## Running All Services

To start everything (vLLM + API + workers) in background mode:

```bash
source .venv/bin/activate

# 1. Start vLLM (takes ~2 min to load model)
CUDA_VISIBLE_DEVICES=0,1,2,3 nohup python -m vllm.entrypoints.openai.api_server \
  --model deepseek-ai/DeepSeek-R1-Distill-Qwen-32B \
  --tensor-parallel-size 4 --max-model-len 8192 --dtype bfloat16 \
  > /tmp/vllm.log 2>&1 &

# 2. Start FastAPI
nohup uvicorn backend.app.main:app --host 0.0.0.0 --port 8080 > /tmp/api.log 2>&1 &

# 3. Start workers (4 concurrent)
for i in 1 2 3 4; do
  nohup python -m worker.main > /tmp/worker$i.log 2>&1 &
done
```

To stop everything:

```bash
pkill -f "vllm.entrypoints"
fuser -k 8080/tcp
pkill -f "worker.main"
```

**Remote access**: `ssh -L 9090:localhost:8080 your-server -N`, then open `http://localhost:9090`.

## Load Testing

```bash
python scripts/load_test.py -n 5   # 5 concurrent jobs
```

## Project Structure

```
rohm-project/
├── backend/app/          # FastAPI API
│   ├── routes/           # jobs.py, voice.py
│   ├── models.py         # SQLAlchemy models
│   ├── schemas.py        # Pydantic schemas
│   ├── config.py         # Configuration
│   ├── database.py       # Async DB engine
│   ├── queue.py          # Redis queue
│   └── storage.py        # File storage
├── worker/               # Job processing
│   ├── main.py           # Worker loop + stuck job recovery
│   └── analysis/         # LLM + sandbox pipeline
│       ├── engine.py     # Orchestrator
│       ├── prompt.py     # Prompt construction
│       ├── parser.py     # Response parsing
│       └── sandbox.py    # Safe code execution
├── frontend/
│   └── index.html        # Single-page Web UI
├── cli/
│   └── main.py           # CLI tool
├── scripts/
│   ├── load_test.py      # Concurrent load test
│   └── run_tablebench.py # TableBench evaluation adapter
├── tablebench/           # TableBench benchmark (cloned)
├── sa                    # CLI shortcut (./sa ask ...)
├── requirements.txt
├── designDecisions.md    # Architecture decisions
└── README.md
```
