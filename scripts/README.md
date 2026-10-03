# Script guide

Run commands from the repository root. Prefer the public `make` targets for
routine work; see [reproduction](../docs/reproduce.md) for tool requirements and
the distinction between current checks and historical workflows.

Scripts stay in one directory because they import each other as Python modules.
The groups below separate their purposes without changing those imports or
recorded verification paths.

## Daily checks

| Script | Purpose / entry point |
|---|---|
| [`run.py`](run.py) | `make lint`, `make smoke`, `make test`, `make regress`, `make perf` |
| [`check_portfolio.py`](check_portfolio.py) | `make check-evidence`: source hashes and published evidence |
| [`formal.py`](formal.py) | `make formal`: controller property tasks |
| [`parallel_arbitration_check.py`](parallel_arbitration_check.py) | `make formal-parallel`, `make compare-parallel`: current equivalence and traces |

## Synthesis and lab transfers

| Script | Purpose |
|---|---|
| [`synth.py`](synth.py) | Local synthesis sanity check, Design Compiler and PrimeTime |
| [`lab_bundle.py`](lab_bundle.py) | Create an allowlisted controller lab bundle |
| [`import_lab_results.py`](import_lab_results.py) | Import lab result artifacts |
| [`dc_sweep.py`](dc_sweep.py) | Run the mapped synthesis matrix |

## Focused and historical verification

| Script | Purpose |
|---|---|
| [`scheduler_equiv.py`](scheduler_equiv.py) | Candidate-decode scheduler equivalence |
| [`scheduler_trace_compare.py`](scheduler_trace_compare.py) | Paired complete-controller cycle traces |
| [`address_equiv.py`](address_equiv.py) | Address-sharing equivalence and trace workflow |
| [`candidate_mask_equiv.py`](candidate_mask_equiv.py) | Candidate-mask equivalence and trace workflow |
| [`command_mask_equiv.py`](command_mask_equiv.py) | Command-mask equivalence and trace workflow |
| [`response_capacity.py`](response_capacity.py) | Isolated response-path throughput study |
| [`perf_stability.py`](perf_stability.py) | Multi-seed performance experiments |

Use the checkpoints specified in each experiment when reproducing historical
encoded-interface checks. These checks are not all intended for the current RTL.

## Reports and shared helpers

Report publishers can overwrite frozen documents and public evidence. They are
not cleanup tools or part of the current quickstart. Review each experiment's
inputs and source revision before running its publisher.

| Script | Output / responsibility |
|---|---|
| [`report.py`](report.py) | Historical local results, plots and annotated traces |
| [`response_refill_report.py`](response_refill_report.py) | Response-refill comparison |
| [`perf_stability_report.py`](perf_stability_report.py) | Performance stability report |
| [`dc_sweep_publish.py`](dc_sweep_publish.py) | Frozen ASIC sweep publication |
| [`scheduler_optimization_report.py`](scheduler_optimization_report.py) | Candidate-decode experiment report |
| [`address_optimization_report.py`](address_optimization_report.py) | Address-sharing experiment report |
| [`critical_path_report.py`](critical_path_report.py) | 3 ns path analysis |
| [`candidate_mask_report.py`](candidate_mask_report.py) | Candidate-mask experiment report |
| [`storage_timing_report.py`](storage_timing_report.py) | Storage timing experiment report and report helpers |
| [`command_mask_report.py`](command_mask_report.py) | Command-mask experiment report |
| [`command_path_report.py`](command_path_report.py) | Command-output path analysis |
| [`parallel_arbitration_report.py`](parallel_arbitration_report.py) | Current parallel-arbitration evidence publication |
| [`dc_sweep_report.py`](dc_sweep_report.py) | Shared mapped-report parsers and sweep summaries |
| [`log_experiment.py`](log_experiment.py) | Append to the ignored local experiment journal |
| [`requirements-plot.txt`](requirements-plot.txt) | Optional plotting dependencies |
