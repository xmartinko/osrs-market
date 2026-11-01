# Phase One execution plan

The user approved Phase One with the RTX 5080 and RTX 3070 running simultaneous,
independent jobs. Each job owns one GPU; no distributed training, pooled VRAM or
cross-node gradient synchronization is implied. Existing services retain resource
headroom. The principal coordinates environment setup; this document makes no
claim that an environment or training run has already completed.

## Pilot sequence and accounting

The first three pilot fits are registered across both nodes: pilot 1 on the desktop
RTX 5080, pilot 2 on the ThinkPad RTX 3070, and pilot 3 on whichever node is free
under the preregistered dispatch order. Pilots 1 and 2 may run simultaneously after
their individual compatibility and data-integrity gates pass. Pilot 3 checks the
next planned architecture or a replication selected before observing performance.

Every fit counts toward the campaign budget, including pilots, failed or aborted
fits, retries, seeds, tuning attempts and resumed fits with changed configurations.
Record attempts individually, together with resumed lineage, actual elapsed time,
GPU-hours, peak RAM/VRAM, numerical failures and completion status. A resumed
unchanged fit remains linked to its original experiment and all consumed time is
counted. Do not quietly discard failed pilots or replace them outside the budget.
The coordinator freezes concrete model IDs, trial count and resource caps in the
campaign manifest before dispatch; this plan does not authorize an extra search.

## Evaluation contract

The CPU NumPy module `osrs_ml.probabilistic_evaluation` consumes samples `[B,M,H]`
and targets `[B,H]`. It scores supplied units. When samples contain normalized
increments, invert train-only scaling and sum along the horizon before scoring
cumulative returns. Never compare increment scores with cumulative-return scores.
Preserve item and forecast-origin IDs outside the metric arrays.

Sample CRPS uses sorted draws in O(B H M log M) time, without an M-by-M matrix.
Its default fair estimator uses off-diagonal sample pairs and estimates population
CRPS without bias for conditionally IID draws. The explicitly selectable `ecdf`
estimator instead scores the finite empirical forecast distribution; report which
was used. Fair estimates can occasionally be negative. Marginal distributions
within a path need not be independent across horizons.

WIS uses fixed central intervals with alpha levels 0.1, 0.2 and 0.5 and the median;
report empirical coverage and widths at every level and horizon. Fix levels before
comparing models. Sample quantiles introduce Monte Carlo error. Energy score uses
independent disjoint path pairs, avoiding quadratic cost in draw count; variogram
score uses power 0.5 and fixed horizon weights. Energy Monte Carlo variance and
variogram plug-in bias require equal sample counts and sampling-seed sensitivity
checks. Neither attractive path plots nor a single joint score establishes useful
dependence modeling.

Compare Gaussian random-walk and centered empirical-innovation random-walk
controls, fitted only from available historical increments. Empirical independent
resampling retains empirical tails but deliberately omits innovation dependence.
The marginal-preserving horizon shuffle control tests whether a joint model adds
information beyond the same marginal distributions.

The paired circular-block bootstrap aggregates the complete cross-section at each
timestamp before resampling contiguous time blocks. Feed aligned per-origin loss
arrays, preserve the same universe/weights between models, and freeze block length
in advance. Its output is exploratory: short coverage or few independent regimes
cannot be repaired by increasing bootstrap repetitions. Confirmatory claims still
require the registered temporal test, multiplicity adjustment and separate locked
test access policy. No test data may choose the pilot, model, precision, stopping
rule or economic policy.

This work package implements metrics and synthetic correctness tests only. It does
not install environments, acquire or modify data, execute trades, or infer a
positive market result from synthetic diagnostics.
