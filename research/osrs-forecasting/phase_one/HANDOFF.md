# Handoff / parallel-agent entry point

The user opened a Gemini 4 Argon sidebar agent while Codex was completing this milestone. The user asked for parallel context, not cancellation. Until ownership is explicitly assigned, the incoming agent should review independently and return findings without editing shared files, switching branches, installing dependencies or launching jobs. There are no active training jobs at this milestone: all three pilots have completed.

## Authority and scope

Phase One and concurrent independent use of RTX 3070 / RTX 5080 are approved. Keep the original holdout starting at Unix 1785024300 sealed. No trading, game automation, raw-archive rewriting, new acquisition, production deployment, driver/BIOS/network changes or unrelated-service disruption is authorized. Never display secrets/private keys. Follow /home/martin/homelab-overview.md and the user's infrastructure instructions.

The proposal's methodological requirements remain binding. Pilot execution and resource review are recorded here; they do not constitute predictive success. Final prospective test dates and final model selection are not registered yet. Current-day collectors/forward ledgers are unrelated services and were left alone.

## Canonical locations

- Devstash repository: https://git.devstash.tech/martinko/osrs-market
- Active branch: research/osrs-phase-one-2026-11-01. Read its latest commit; do not assume the original Phase Zero branch is current.
- VPS working tree: /home/martin/osrs-phase-one-worktree.
- Windows development copy: C:/Users/xmart/osrs-phase-one. The lead synchronizes it to the published branch before final handoff; check git status before edits.
- Desktop: WSL Ubuntu-24.04, /home/xmart/osrs-research/{code,venv,data,runs}.
- ThinkPad: /home/martin/osrs-research/{code,venv,data,runs}; reached via existing root SSH from VPS. The shell is fish: pipe scripts rather than relying on scp protocol behavior.
- Central full artifacts: /home/martin/osrs-data/phase-one-20261101/{hourly.parquet,hourly.manifest.json,runs/}.
- Local artifact mirror: C:/Users/xmart/osrs-phase-one-tools/results. Keep panels/checkpoints/per-origin rows outside Git.

## Actual state

The frozen 95% coverage gate admitted 74 items. The panel has 1,127,760 item-hours and SHA-256 `5a5bf0fa4d656b24b4df5883804fbb32068e5c0262924c3d51ccffe93af321a8`. Eligibility uses only the initial training year; derived development dates stay before the old holdout. See data_manifest.json and data_gate.md for exact semantics, caveats and source checks.

Both nodes have isolated Python 3.13.13 / torch 2.8.0+cu128 environments, matching installed-distribution freezes, and supported sm_86/sm_120 kernels. No system GPU driver was installed. There are 40 new tests after the CUDA-device regression fix. All three market-data fits ran code bca7dfb3abaf9bdef351b482c9c1c9dc4afafbfb; later commits may add only reports.

Completed runs: p01_diag_3070_r1, p02_lowrank_5080_r1 and p03_spline_5080. Each ran 256 optimizer steps and scored 512 sampled validation origins. The 3070 Gaussian and 5080 spline optimizer loops overlapped. Initial p01_diag_3070 and p02_lowrank_5080 failed before optimization; their status records remain. All artifact hashes were verified; a 3070 checkpoint reloaded on desktop CPU.

Read pilot_protocol.json, pilot_amendment_01.json, pilot_budget_review.json and pilot_results.md/json. Scores are sampled, origin-weighted, complete-future-window diagnostics with only Gaussian random-walk and no-change controls. Source latency is assumed; current-listed survivorship and future-target completeness selection limit generalization. The first target aggregate bucket starts five minutes before the forecast decision. No executable-price or continuous barrier claim follows.

## Next bounded work package

First independently audit the pilot implementation, result interpretation and budget. Then, once the user assigns ownership, implement the stronger baseline suite on the same frozen panel: rolling/EWMA Gaussian and Student-t, empirical/block innovations, regularized linear/tree controls and representative statistical models. Retain common origins and paired per-origin losses, macro-average items, and evaluate chronological folds before selecting neural complexity. Do not use the existing original-export holdout.

Five neural fit attempts have consumed five of the 72 allowed slots. These subset pilots do not replace full-fold runs. The original 72-full-fit matrix cannot also fit into the 67 remaining slots. Register a reduced allocation or revise the budget explicitly before more neural fits. No queue currently launches the full campaign. The prospective final test begins only after the final protocol/model/data configuration is frozen; do not infer dates from today's pilot commit.

Save code, tests, manifests and aggregate findings to devstash with follow-up commits. Preserve the live infrastructure and existing branch histories; never force-push. Package locks and code revisions matter more than matching filenames across machines.
