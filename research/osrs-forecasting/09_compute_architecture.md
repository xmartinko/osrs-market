# Compute and experiment architecture

Phase Zero, 2026-11-01. Recommendation only. No software installation, configuration, training, network benchmarking or infrastructure changes were performed.

## Evidence and capacity

Coordinator live checks: desktop RTX 5080, Windows driver 610.88, 16,303 MiB VRAM total and 14,641 MiB free. The homelab overview reports approximately 833 GB C: free; this was not independently remeasured. WSL2 distributions Ubuntu-24.04, Ubuntu and docker-desktop are installed and stopped; none was started. Hardware and installed distributions do not prove working Linux CUDA/PyTorch.

The coordinator read /home/martin/homelab-overview.md dated 2026-11-01. It reports the ThinkPad as a Ready third k3s node at 100.125.3.123, superseding the directive's offline description. Reported driver/module strings differ (580.105 versus 615.78.08); training compatibility remains unverified. The overview reports historical P2P throughput 893 Mbit/s versus Wi-Fi 165.7 Mbit/s. These are not new benchmarks. The VPS coordinates the repository and is not an additional research GPU.

CPU RAM and GPU VRAM are separate resources. Ordinary data parallelism replicates the model; summing 16+8+8 GB does not provide one 32 GB GPU. Reserve resources for existing Jellyfin, Hermes, k3s, Minecraft and other services. Check availability and thermal conditions before each approved workload.

## Node allocation and compatibility

| Node | Proposed role | Gate before Phase One |
|---|---|---|
| Desktop RTX 5080 | Principal small Gaussian neural and flow experiments | WSL2 CUDA smoke test; pinned wheel including Blackwell kernels |
| ThinkPad RTX 3070 Laptop | Independent seeds, smaller models, replication | Driver/module discrepancy resolved; GPU and thermal checks |
| Homeserver GTX 1070 | Bounded CPU audit/baselines and manifests | Production-service headroom; optional GPU only with legacy compatibility evidence |

RTX 5080 is compute capability 12.0; GTX 1070 is 6.1. [NVIDIA current GPUs](https://developer.nvidia.com/cuda/gpus), [legacy GPUs](https://developer.nvidia.com/cuda/gpus/legacy).

PyTorch 2.7 introduced Blackwell support using CUDA12.8 builds. This is historical compatibility evidence, not a claim that 2.7 is latest or a recommendation to install that old release. Select a supported, pinned binary including the target GPU and verify representative forward/backward kernels. Search indexing exposed inconsistent installer-version information; a mutable main release matrix does not identify an installed wheel. [PyTorch 2.7 release](https://pytorch.org/blog/pytorch-2-7/), [release matrix](https://github.com/pytorch/pytorch/blob/main/RELEASE.md).

CUDA13 removed Pascal offline compilation and library support. A driver advertising CUDA13 does not establish GTX1070 PyTorch compatibility. Start with CPU duties; any legacy GPU environment must be isolated, CUDA12.x-compatible and tested on the actual sm_61 device. Preserve the working homeserver driver. [CUDA13 release notes](https://docs.nvidia.com/cuda/archive/13.0.1/cuda-toolkit-release-notes/index.html).

WSL2 is appropriate subject to unperformed smoke tests. Its CUDA driver comes from Windows; do not install a Linux GPU driver in WSL. Native Windows remains a single-GPU fallback; documented NCCL availability differs from Linux. [NVIDIA WSL guide](https://docs.nvidia.com/cuda/wsl-user-guide/index.html), [PyTorch backends](https://docs.pytorch.org/docs/stable/distributed).

After approval, active Linux caches should reside inside WSL's Linux filesystem for performance. No VHDX conversion or storage relocation is authorized now. [Microsoft filesystem guidance](https://learn.microsoft.com/en-us/windows/wsl/filesystems).

Start reference models in FP32. Test BF16 encoder/vector-field autocast on RTX GPUs only, with probability losses, covariance/Cholesky, log determinants and spline Jacobians retained in FP32 or FP64 where needed. Record TF32 flags. GTX1070 has no Tensor Cores; assume no AMP speed benefit. [PyTorch AMP](https://docs.pytorch.org/docs/stable/amp.html).

## Minimal reproducible stack

Use Python with a dependency lock, NumPy/SciPy and statistical baseline libraries; add PyTorch for neural experiments. Prefer existing repository conventions. Evaluate DuckDB for read-only SQL audits and Polars lazy scans for preprocessing; choose one primary engine after a small approved comparison. Neither is mandatory for small data. Lazy processing can reduce reads and memory, but not every operation automatically streams. [Polars lazy guide](https://docs.pola.rs/user-guide/lazy/using/), [DuckDB Parquet](https://duckdb.org/docs/stable/data/parquet/overview).

Keep raw archives immutable. Proposed manifests contain SHA256, file sizes, schema, extraction/as-of time, UTC semantics, feed generation and collector version. Derived dataset IDs also hash eligibility rules, transformations, temporal splits and train-only scaling. Partition derived Parquet by resolution/date; avoid millions of tiny per-item files. Export point-in-time-consistent research snapshots only after approval; do not train against a mutable production database.

Copy the same frozen subset to each training SSD. Centralize manifests and result summaries; distribute checksummed, read-only caches. Remote random minibatch reads add latency/source load. No dataset transfer or export occurred in Phase Zero.

One immutable directory per run holds config, code commit, dataset ID, environment freeze, seeds, split IDs, metrics JSON, resource usage and checkpoints. JSONL or coordinator-local SQLite is sufficient initially; never put concurrent SQLite writers on a network share. MLflow, distributed object storage or a new daemon requires demonstrated need and separate approval.

Schedule independent configurations/seeds per GPU. A later coordinator can claim jobs with leases and completion manifests; retries affect one job. Avoid k3s GPU scheduling complexity initially. Use existing SSH/Tailscale and verified host-native supervision; the overview warns Windows can terminate SSH child processes. No firewall/NAT/monitoring changes. Keep socktop; do not reintroduce Glances.

## Independent scheduling versus DDP

For P parameters, n workers and FP32 gradients, ring all-reduce transfers roughly 2*(n-1)/n*4P bytes per worker per step. P=10 million and n=3 implies about 53 MB: ideal lower bounds of 0.48 seconds at 893 Mbit/s or 2.57 seconds at 165.7 Mbit/s before latency, encryption, contention and slow-worker compute. These are arithmetic illustrations from historical link reports, not measured collective times; full three-node routing may be slower. Small time-series models may finish local steps much faster.

Only consider DDP if a later controlled pilot demonstrates at least 1.3x faster time to the same validation criterion than the RTX5080 alone and higher completed-trial throughput than independent scheduling, with matched effective batch/optimization and an energy budget. Sharding is a separate complex design outside the initial campaign. Confidence high in deferring DDP; exact performance is unmeasured.

## Budget estimates: reservations, not benchmarks

Assume 100-200 eligible items, hourly data for roughly one year, context168, horizon24, 1-10M parameters, batch32-128 and local cached features. Actual archive suitability is determined separately. Generate sliding windows lazily: 1.75M windows *168*10 FP32 features is about11.8GB before labels/framework overhead.

| Work | Planning memory ceiling | Planning wall time per selected panel/fold/run |
|---|---:|---:|
| Statistical baseline family | 2-8GB host, no GPU | 10 minutes-4 CPU-hours |
| Small neural Gaussian | 1-4GB GPU | 15 minutes-2 GPU-hours |
| 4-8 layer conditional spline flow, H24 | 2-6GB GPU | 30 minutes-4 GPU-hours |
| Small conditional flow matching | 4-10GB GPU | 1-8 GPU-hours; sampling evaluation separately |

These are wide provisional allowances, not hardware throughput forecasts. Adam FP32 parameter/gradient/two moments alone cost about16P bytes (160MB at10M parameters). Activations, workspaces and sampled-path buffers can dominate. Joint200-item H24 output has dimension4800 and is excluded from these small-model ceilings; start with univariate trajectories and a shared item-conditioned encoder.

Use an initial aggregate ceiling of 20 GB for new research artifacts: roughly 0.1–5 GB of qualified derived data and up to 5 GB of checkpoints, with remaining space for metrics, manifests and retained diagnostic paths. These are unmeasured allowances and require schema/row checks before export. Larger caches need a revised budget. Storing 10,000 origins * 100 items * 500 paths * 24 steps * 4 bytes costs 48 GB per model. Score paths in chunks and retain a preregistered diagnostic subset plus sufficient summaries. The existing 48 GB archive remains in place.

Six neural configurations * three seeds = 18 seeded trial pipelines. Each pipeline includes three rolling validation fits and one final refit: at most 72 individual fits if every contender proceeds. At an unmeasured 0.5–4 hours per fit, the full campaign allowance is 36–288 GPU-hours. Validation no-go gates should stop unsuccessful contenders before final refits. Flow matching is a separately approved extension. An approved three-fit pilot must replace guesses with measured seconds per step, peak memory and scoring cost before broader runs. No budget approval or model fitting has occurred.

## Reproducibility and gates

Save Python/NumPy/CPU/CUDA RNG and sampler states, optimizer, config and transformations. Pin dependencies, driver/runtime, hardware, precision and deterministic flags. Use CPU-loadable state dictionaries and versioned model/schema metadata. Portability means successful reload and numerical/distribution agreement within stated tolerances, not bitwise equality across platforms. [PyTorch reproducibility](https://docs.pytorch.org/docs/stable/notes/randomness.html).

After approval: verify architecture/representative backward pass; CPU and second-node reload; finite losses and covariance stability; peak RAM/VRAM and short-fixture throughput; service responsiveness and thermal headroom. Reject unsupported kernels, persistent nonfinite losses, throttling or production interference. Do not fix these through desktop reboots, BIOS changes, new gear or unrelated service modifications.

Recommendation: one RTX5080 job at a time; ThinkPad independent replication when verified; homeserver bounded CPU duties. Confidence high in division/simplicity, moderate in WSL suitability until checked, low in runtime estimates.
