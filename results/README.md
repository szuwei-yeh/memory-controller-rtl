# Published evidence guide

This directory contains selected public evidence. Working builds, full logs and
new experiment outputs belong in ignored `build/` until deliberately published.
Preserve recorded reports, manifests and source snapshots when organizing files.

## Current implementation

- [`parallel_arbitration/`](parallel_arbitration/): current experiment summary,
  validation, paired traces, mapped reports and scheduler snapshot.
- [`hold_repair/`](hold_repair/): paired mapped hold repair at Q16/3 ns and 4 ns,
  unchanged constraints/setup, and mapped equivalence with negative controls.
- [`setup_margin/`](setup_margin/): latest paired incremental mappings at Q16/3 ns
  and 4 ns, original constraints, unchanged DRC counts, complete state/clock/output
  comparison and rejected negative controls. Exploratory screens are recorded separately.
- [`capacitance_diagnosis/`](capacitance_diagnosis/): read-only source/DB limit
  comparison, all-net load accounting, selected native examples and bounded
  library/physical-view inventory. Existing timing/area reproduce exactly; no repair.
- [`portfolio_audit/summary.json`](portfolio_audit/summary.json): recorded
  fresh-checkout audit; see [reproduction](../docs/reproduce.md) for its scope.
- Run `make check-evidence` to compare current RTL with published source hashes,
  report hashes, verification summaries and mapped measurements.

The [parallel-arbitration document](../docs/experiments/parallel-arbitration-experiment.md)
explains the RTL optimization; [mapped hold repair](../docs/experiments/hold-repair-experiment.md)
records the subsequent hold result, followed by the latest
[setup-margin mapping](../docs/experiments/setup-margin-experiment.md).

## Frozen baseline and earlier studies

| Directory | Evidence |
|---|---|
| [`dc_baseline/`](dc_baseline/) | Initial mapped ASIC baseline and diagnostics |
| [`dc_sweep/`](dc_sweep/) | Frozen 30-point mapped ASIC sweep |
| [`perf_stability/`](perf_stability/) | Per-seed performance distributions and frozen inputs |
| [`scheduler_optimization/`](scheduler_optimization/) | Candidate-decode experiment |
| [`address_sharing/`](address_sharing/) | Shared address-comparison experiment |
| [`critical_path_3ns/`](critical_path_3ns/) | Critical-path decomposition and endpoint analysis |
| [`candidate_mask/`](candidate_mask/) | Candidate-mask alternatives and source snapshots |
| [`storage_timing/`](storage_timing/) | Storage timing diagnosis and alternatives |
| [`command_mask/`](command_mask/) | Command-mask and storage alternatives |
| [`command_path_3ns/`](command_path_3ns/) | Remaining command-output path analysis |

Each study has its own source revision and constraints. The
[experiment index](../docs/experiments/README.md) links each directory to its
explanation and reproduction instructions.

## Files at this level

| Files | Purpose |
|---|---|
| [`local_summary.json`](local_summary.json), [`performance.png`](performance.png), [`performance.pdf`](performance.pdf) | Frozen local verification and performance summary / plots |
| [`response_capacity_before.json`](response_capacity_before.json), [`response_capacity_after.json`](response_capacity_after.json) | Isolated response-path capacity comparison |
| [`response_refill_before.json`](response_refill_before.json), [`response_refill_comparison.json`](response_refill_comparison.json), [`response_refill.patch`](response_refill.patch) | Response-refill baseline, comparison and recorded patch |

These existing paths are retained for report consumers and historical workflows.
Adding this index does not republish their measurements.
