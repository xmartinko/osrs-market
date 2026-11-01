# Isolated research environments

Created 2026-11-01 under the approved Phase One scope. No GPU driver, kernel, firewall, BIOS, monitoring or production service was changed. Ubuntu-24.04 WSL2 was started on the desktop; other WSL distributions were not started deliberately.

| Node | Environment | Operator |
|---|---|---|
| Desktop / Ubuntu-24.04 WSL2 (neural GPU) | /home/xmart/osrs-research/venv | xmart |
| Desktop / Ubuntu-24.04 WSL2 (`E1` CPU baselines) | /home/xmart/osrs-research/venv-baselines | xmart |
| ThinkPad / Fedora (neural GPU) | /home/martin/osrs-research/venv | Existing root SSH access, isolated research directory |

Both use the existing VPS uv executable version 0.11.15, copied into each research directory's bin/ without changing system package managers. uv installed CPython 3.13.13 and created separate virtual environments. On the ThinkPad the managed interpreter belongs to root's uv cache; use the existing root research route until ownership/interpreter placement is deliberately revised. No global Python packages were replaced.

PyTorch 2.8.0 with CUDA 12.8 was selected as a documented common Blackwell/Ampere build, not claimed to be the latest release. The [official previous-version instructions](https://pytorch.org/get-started/previous-versions/) specify its cu128 index. The Windows GPU driver supplies WSL CUDA; no Linux display driver was installed, following [NVIDIA's WSL guidance](https://docs.nvidia.com/cuda/wsl-user-guide/).

The complete neural GPU desktop environment is frozen in `ml/requirements-probabilistic.lock`. The separate `E1` statistical/tabular baseline environment (`/home/xmart/osrs-research/venv-baselines`) is frozen in `ml/requirements-baselines.lock` (SHA-256 `9500f5e75fa4794410e0cc91517d5873277dc2a92914fb072671848c0669f6ac`), adding `statsforecast==2.0.3`, `arch==8.0.0`, `scikit-learn==1.8.0`, and `catboost==1.2.10` without mutating the pilot neural environment. Each run also records its own installed distributions in `environment.txt`. Direct research dependencies include NumPy 2.3.3, pandas 2.3.3, PyArrow 21.0.0, DuckDB 1.5.0, SciPy 1.16.2, nflows 0.14, pytest 8.4.2 and Ruff 0.14.3. Existing application `pyproject.toml` and `uv.lock` are untouched; research modules are standalone additions.

Reproduction after installing uv in an appropriate isolated tool directory:

```bash
# Neural GPU environment
uv venv --python 3.13.13 /chosen/research/venv
uv pip install --python /chosen/research/venv/bin/python \
  torch==2.8.0 --index-url https://download.pytorch.org/whl/cu128
uv pip install --python /chosen/research/venv/bin/python \
  -r ml/requirements-probabilistic.lock

# E1 CPU baseline environment
uv venv --python 3.13.13 /chosen/research/venv-baselines
uv pip install --python /chosen/research/venv-baselines/bin/python \
  --extra-index-url https://download.pytorch.org/whl/cu128 \
  --index-strategy unsafe-best-match \
  -r ml/requirements-baselines.lock
```

Linux GPU code and panel caches belong inside each node's native filesystem. Frozen Git bundles or local fetches provide the same committed source to both nodes; the SHA-256-verified derived panel is copied once. Research artifacts remain outside Git, except configuration, manifests and aggregate results. Source archives and private per-origin price data are never pushed.

Readiness evidence: `gpu3070_readiness.json` and `gpu5080_readiness.json`. GPU free memory is transient; pilot jobs enforce a 0.75 allocation fraction and record both peak allocated and peak reserved bytes. Package caches/environment storage are separate from the 20 GB cap on derived data, checkpoints and research outputs.
