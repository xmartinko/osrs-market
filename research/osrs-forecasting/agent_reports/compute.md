# Agent6: compute research

Independent PhaseZero report,2026-11-01. Native Codex subagent; no DeepSeek execution claimed. Detailed source-linked design and estimates: [compute architecture](../09_compute_architecture.md).

## Question and scope

What is the smallest defensible research environment for this heterogeneous homelab? Scope is documentation research, resource arithmetic and proposed tests only. No installs, distribution starts, training or infrastructure modifications.

## Key findings and evidence classes

Coordinator-observed: RTX5080 driver610.88 with16,303MiB total/14,641MiB free; WSL2 distributions installed/stopped; C: approximately833GB free. Overview-reported: ThinkPad Ready in k3s, driver/module discrepancy unresolved, historical P2P893 versus Wi-Fi165.7Mbit/s. These establish availability clues, not PyTorch readiness.

Documented: Blackwell requires a matching binary; PyTorch2.7 added CUDA12.8 support ([release](https://pytorch.org/blog/pytorch-2-7/)). CUDA13 removed Pascal compilation/library support ([notes](https://docs.nvidia.com/cuda/archive/13.0.1/cuda-toolkit-release-notes/index.html)). WSL uses Windows-host driver ([guide](https://docs.nvidia.com/cuda/wsl-user-guide/index.html)). Framework/wheel architecture support must be checked independently of driver-reported CUDA capability.

Deductions: independent scheduling avoids slowest-GPU synchronization; local frozen caches avoid repeated remote minibatch load; precise run manifests aid reproduction. Hypotheses: a small H24 flow fits8GB RTX memory; RTX BF16 encoder improves throughput without score drift; WSL2 performs adequately. None has been empirically tested here.

## Mathematical justification

Ring DDP traffic is approximately2*(n-1)/n*gradient_bytes per worker/step. Ten million FP32 gradients over three workers imply53MB and optimistic historical-link lower bounds0.48-2.57seconds/step, excluding overhead and slowest-worker compute. Adam FP32 parameter/gradient/moments cost about16P bytes; activations/workspaces remain additional. Distributed VRAM is not shared VRAM.

## Falsifiable engineering tests proposed for approval

1. GPU kernel/backward and CPU/second-RTX checkpoint reload must succeed; otherwise reject that environment.
2. Compare FP32 and BF16 encoder with identical seeds/origins. Admit mixed precision only if no nonfinite values, relative validation score change within0.1%, and throughput gain at least10%. These are proposed engineering tolerances.
3. Compare local versus remote frozen-subset reads. Retain local caches unless ordinary-load input stalls stay below5% remotely.
4. Consider DDP only after a pilot suggests amortizable communication. Require1.3x faster time-to-criterion and higher completed-trial throughput than independent scheduling at matched batch/optimization.
5. Cross-machine portability requires stated numerical tolerances, not bitwise equivalence ([PyTorch reproducibility](https://docs.pytorch.org/docs/2.15/notes/randomness.html)).

## Alternatives and limitations

Native Windows is a single-GPU fallback; NCCL support differs from Linux ([backends](https://docs.pytorch.org/docs/stable/distributed)). Containers improve packaging but add operational dependencies; lockfiles suffice initially. k3s scheduling,MLflow and object storage are unjustified for an18-fit campaign. CPU baselines might answer no-signal before neural training.

Actual disk, network, thermal and model throughput remain unmeasured. Published specs do not reveal laptop power limits or service contention. Exact package artifacts must be pinned; current main documentation can move. The archive has not been audited by this agent.

## Complexity, budget and recommendation

Small reproducible runner/snapshot exporter: moderate PhaseOne engineering. Distributed training/orchestration: high complexity, defer. Planning GPU ceilings: Gaussian1-4GB, spline flow2-6GB, small flow matching4-10GB. Per-run reservations15minutes-8hours depending on family are estimates. Six configurations*three seeds at0.5-4hours reserve9-72GPU-hours; flow-matching extension separate. Budget sampled forecasts by dimensions and chunk scoring.

Use RTX5080 primary; RTX3070 independent replication after compatibility/thermal checks; homeserver CPU with service caps. High confidence in deferring DDP and protecting existing services, moderate in WSL suitability, low in timing estimates pending approved pilot.
