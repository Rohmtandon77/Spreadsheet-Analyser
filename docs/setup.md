# Setup Guide -- H100 GPU Environment

## Prerequisites

- 8x NVIDIA H100 GPUs with NVSwitch
- NVIDIA Driver 580.126.09 (CUDA 13.0)
- Ubuntu 22.04
- Python 3.10+

## Initial Setup

```bash
cd /home/ubuntu/rohm-project
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
```

PyTorch is installed as a dependency of vLLM. If you need to reinstall torch separately:

```bash
pip install torch --index-url https://download.pytorch.org/whl/cu130
```

## Known Issues and Fixes

### Error 802: "system not yet initialized"

**Symptom**: `torch.cuda.is_available()` returns `False`, CUDA error 802.

**Root cause**: On 8x H100 NVSwitch systems, the `nvidia-fabricmanager` service must be running.

**Fix**:

```bash
sudo apt-get install -y nvidia-fabricmanager-580
sudo systemctl unmask nvidia-fabricmanager
sudo systemctl enable nvidia-fabricmanager
sudo systemctl start nvidia-fabricmanager
```

### Error 803: "unsupported display driver / cuda driver combination"

**Symptom**: After installing `nvidia-fabricmanager`, CUDA reports a driver mismatch.

**Root cause**: `apt-get install nvidia-fabricmanager-580` can inadvertently replace
`libnvidia-compute-580` with an older version (e.g. 535).

**Fix**:

```bash
sudo apt-get install -y libnvidia-compute-580-server
sudo systemctl restart nvidia-fabricmanager
```

### LD_LIBRARY_PATH for libcuda.so

The CUDA toolkit stubs can shadow the real driver library. Always set:

```bash
export LD_LIBRARY_PATH="/usr/lib/x86_64-linux-gnu${LD_LIBRARY_PATH:+:$LD_LIBRARY_PATH}"
```

Or use the wrapper script: `scripts/run_gpu.sh <your_script.py>`

## Starting the vLLM Server

```bash
source .venv/bin/activate
export LD_LIBRARY_PATH="/usr/lib/x86_64-linux-gnu${LD_LIBRARY_PATH:+:$LD_LIBRARY_PATH}"

CUDA_VISIBLE_DEVICES=0,1,2,3 python3 -m vllm.entrypoints.openai.api_server \
  --model deepseek-ai/DeepSeek-R1-Distill-Qwen-32B \
  --tensor-parallel-size 4 \
  --dtype auto \
  --max-model-len 8192
```

Verify it's running:

```bash
curl http://localhost:8000/v1/models
python scripts/test_vllm.py
```

## GPU Allocation

| GPUs | Service |
|------|---------|
| 0-3  | DeepSeek-R1-Distill-Qwen-32B via vLLM (tp=4) |
| 4    | Whisper STT (Phase 9) |
| 5    | TTS model (Phase 9) |
| 6-7  | Free / overflow |
