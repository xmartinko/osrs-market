# Phase One: approved, bounded pilot campaign

The user approved the Phase Zero proposal and simultaneous use of the RTX 3070 and RTX 5080. This stage runs independent jobs, one per GPU. It does not pool VRAM, use heterogeneous DDP, access the sealed holdout, execute trades or change production services.

## Actual data gate

The pipeline read existing canonical main-economy mirror partitions and wrote a new derived panel outside the source tree. Item selection uses only 2024-10-29 through 2025-10-29. Later development data ends strictly before 2026-07-26 00:00 UTC; the original reserved holdout begins at Unix 1785024300. Source files and existing datasets remain unchanged.

The frozen 95% usable-hour threshold admitted **74 items**; it was not relaxed to obtain 100. The dense panel contains **1,127,760 item-hours**, including **1,086,789 usable hours**. Unknown directional volume occurs in 19,976 hours per side. There are 20,555 inverted-side hours, retained for diagnostics and excluded from usable prices and initial eligibility. Complete observed zero-volume sides remain zero; missing subintervals produce unknown totals. Directional means use volume weights across twelve distinct five-minute rows.

Selection scanned 166,533,346 source rows in the first training year. The subsequent selected-item development scope contained 13,464,284 source rows. These are actual bounded-scope diagnostic counts, not independent samples or counts for the entire archive. Duplicate and source/timestamp checks passed in the scanned scopes. Full source-payload hashes were not recomputed; source footer and sidecar fingerprints plus a full derived-panel hash are recorded in [data_manifest.json](data_manifest.json).

Panel SHA-256: `5a5bf0fa4d656b24b4df5883804fbb32068e5c0262924c3d51ccffe93af321a8`.

## Frozen pilot protocol

[pilot_protocol.json](pilot_protocol.json) was written before market-data optimizer steps. The three authorized pilot fits are a diagonal Gaussian on the 3070, a low-rank Gaussian on the 5080 concurrently, then a small spline flow on the 5080. Each uses seed 11, at most 256 optimizer steps, batch 64, 168-hour context, 24 future increments and 256 sampled paths per scored origin. Every attempt consumes a fit slot. This does not launch the full 72-fit campaign automatically.

The pilot uses at most 20,000 training origins and 512 validation origins. These sampled scores are origin-weighted, not the registered item-macro primary scores. Only fixed training-volatility Gaussian random-walk and no-change controls are included. The remaining baseline hierarchy, complete walk-forward evaluation, calibration and significance work remain outstanding.

Targets are future aggregate observations, not executable prices. Decision time is origin bucket start plus 3,900 seconds; the first target bucket has already begun five minutes earlier and becomes available one hour after the decision. No first-hour fill, wholly post-decision price window, continuous-time barrier or executable return claim follows. Requiring complete future targets selects a potentially biased observed-window cohort; report its coverage before generalizing.

Historical publication delay remains an assumption, and source classification uses current listed-item status. Source rights are limited to private research pending review. These limitations prevent a confirmatory or economic interpretation of pilot scores.

## Environment and verification

Both nodes have isolated CPython 3.13.13 environments with PyTorch 2.8.0+cu128. The build includes both sm_86 and sm_120. The 5080 passed all four model heads' synthetic forward/backward/sampling checks; the 3070 passed a representative synthetic GRU/Gaussian backward/sampling check. These checks performed no optimizer steps or market-data training.

All 39 new tests passed, including weighted aggregation, duplicate/holdout guards, source and output checksums, likelihood/covariance references, flow round trips, proper scores, causal normalization, missing-label handling and temporal purging. Model pilots have no silent CPU fallback and cap CUDA allocations at 75% of the device, with four CPU threads per job. All results must retain the code revision, panel hashes, environment, origin indices and fit status.

See [environment.md](environment.md) for installation provenance and node paths, [execution_plan.md](execution_plan.md) for scheduling, and the eventual pilot results for measured runtime and memory. Test and smoke results establish implementation readiness only.
