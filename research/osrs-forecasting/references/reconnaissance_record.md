# Reconnaissance record

Session date: 2026-11-01. These are command observations, not model results. Commands used the existing Windows SSH identity; no private keys or credential values were read into tool output.

| Inspection | Recorded result | Scope |
|---|---|---|
| VPS hostname | v2202605360246461845 | Live SSH |
| Homelab overview | /home/martin/homelab-overview.md, 15,721 bytes, dated 2026-11-01 | Read in full; hardware/network facts attributed to this document |
| Repository | /home/martin/src/osrs-market, ml/financial-model, 4f281ba | Working tree initially clean; local history contains binary LFS probes |
| Published research base | devstash/ml/financial-model at 0bf062b0cfb2ebafb1eabb37cfb6324a10f09455 | New documentation branch starts here to avoid unrelated unpublished changes |
| devstash main | 8e03d49eb72a25a20a277385b8976e510479dcc8 | Observed through git ls-remote; no main update |
| Archive size | du -sh: 48G | Rounded disk use, includes multiple representations/artifacts |
| Original prices footer | 2,502,566 rows, 3 row groups, ZSTD, 30,458,813 bytes | Metadata plus first two rows only |
| Original items footer | 4,524 rows, ZSTD, 163,811 bytes | Metadata plus first two rows only |
| Sample broad archive partition | Kaggle canonical main November 2021: 10,969,245 rows, 90 row groups, ZSTD | Footer and two rows; no full partition scan |
| Sample latest snapshot | 1793381862.parquet: 4,551 rows, ZSTD | Footer and two rows; side timestamps in source_extra |
| Legacy quality/coverage | Export metadata, assembled-v3 manifests, October 30 source inventory and timestamp validation | Read existing reported results, not recomputed |
| Desktop NVIDIA | RTX 5080; driver 610.88; 16,303 MiB total, 14,641 MiB free | Live nvidia-smi; free memory is transient |
| WSL inventory | Ubuntu-24.04, Ubuntu, docker-desktop; all WSL2 and stopped | Live wsl --list --verbose; no distro started |
| ThinkPad / homeserver readiness | Not independently checked over SSH | Current overview supersedes stale instructions; GPU training environment unverified |
| DeepSeek availability | OpenRouter model catalogue includes ~deepseek/deepseek-flash-latest | Live model catalogue query; reviews routed to deepseek-v4.1-flash-1017 |

Archive duplicate/null scans, PostgreSQL schema queries, forward-ledger reads, hardware throughput tests, model training, trading and archive acquisition were not executed. Later footers may change if unrelated existing collectors continue running.

The existing original-export holdout was preserved: the sampled original rows and Kaggle partition precede its reserved start. The sampled latest snapshot is after the old export's end; published aggregate summaries and timestamp-validation evidence were read without loading the sealed daily holdout panel's observations. Do not confuse this with proof that every historical date is untouched by previous research.

Operational limits encountered: initial Windows sandbox denied directory/WSL access and some piped SSH invocations; read-only retries succeeded after escalation. Nested quoting caused two unsuccessful shell commands; subsequent scripts used stdin. One broad text-search process returned a session ID; it is checked and stopped before finalization if still active. No diagnostic error was interpreted as an absent archive.

Final checks cover research-file completeness, local Markdown links, JSON syntax, basic credential patterns and local/remote SHA-256 agreement. They do not verify every external link or replicate existing archive-quality claims. Devstash publication is verified by remote branch commit identity after push.
