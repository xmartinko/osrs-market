# Isolated research environments

Created 2026-11-01 under the approved Phase One scope. No GPU driver, kernel, firewall, BIOS, monitoring or production service was changed. Ubuntu-24.04 WSL2 was started on the desktop; other WSL distributions were not started deliberately.

| Node | Environment | Operator |
|---|---|---|
| Desktop / Ubuntu-24.04 WSL2 | /home/xmart/osrs-research/venv | xmart |
| ThinkPad / Fedora | /home/martin/osrs-research/venv | Existing root SSH access, isolated research directory |

Both use the existing VPS uv executable version 0.11.15, copied into each research directory's bin/ without changing system package managers. uv installed CPython 3.13.13 and created separate virtual environments. On the ThinkPad the managed interpreter belongs to root's uv cache; use the existing root research route until ownership/interpreter placement is deliberately revised. No global Python packages were replaced.

PyTorch 2.8.0 with CUDA 12.8 was selected as a documented common Blackwell/Ampere build, not claimed to be the latest release. The [official previous-version instructions](https://pytorch.org/get-started/previous-versions/) specify its cu128 index. The Windows GPU driver supplies WSL CUDA; no Linux display driver was installed, following [NVIDIA's WSL guidance](https://docs.nvidia.com/cuda/wsl-user-guide/).

The complete desktop environment is frozen in ml/requirements-probabilistic.lock; each fit also records its own installed distributions. Direct research dependencies include NumPy 2.3.3, pandas 2.3.3, PyArrow 21.0.0, DuckDB 1.5.0, SciPy 1.16.2, nflows 0.14, pytest 8.4.2 and Ruff 0.14.3. Existing application pyproject.toml and uv.lock are untouched; GPU research modules are optional, standalone additions.

Reproduction after installing uv in an appropriate isolated tool directory:

```bash
uv venv --python 3.13.13 /chosen/research/venv
uv pip install --python /chosen/research/venv/bin/python \
  torch==2.8.0 --index-url https://download.pytorch.org/whl/cu128
uv pip install --python /chosen/research/venv/bin/python \
  -r ml/requirements-probabilistic.lock
```

Linux GPU code and panel caches belong inside each node's native filesystem. Frozen Git bundles provide the same committed source to both nodes; the SHA-256-verified derived panel is copied once. Research artifacts remain outside Git, except configuration, manifests and aggregate results. Source archives and private per-origin price data are never pushed.

Readiness evidence: gpu3070_readiness.json and gpu5080_readiness.json. GPU free memory is transient; pilot jobs enforce a 0.75 allocation fraction and record peak allocation. Package caches/environment storage are separate from the 20 GB cap on derived data, checkpoints and research outputs.
