# Optimization experiments

The current RTL adopts [parallel command-class arbitration](parallel-arbitration-experiment.md).
Earlier documents retain the measurements and source revisions for their own
experiments; their results do not automatically apply to the current RTL.

The follow-up [mapped hold repair](hold-repair-experiment.md) eliminates the
remaining hold failures at Q16/3 ns and 4 ns while preserving setup slack.
The subsequent [setup-margin mapping](setup-margin-experiment.md) increases
setup margins to 50.054 / 55.773 ps while preserving zero setup/hold failures
and inherited capacitance violation counts.
The [capacitance diagnosis](capacitance-diagnosis.md) then traces every remaining
violation to source/DB zero limits and positive pin loads; it does not claim repair.

Read the following in order to follow the optimization history:

| Step | Document | Evidence directory |
|---|---|---|
| 1 | [Candidate decoding](scheduler-optimization.md) | [`scheduler_optimization`](../../results/scheduler_optimization/) |
| 2 | [Shared address comparisons](address-sharing-optimization.md) | [`address_sharing`](../../results/address_sharing/) |
| 3 | [3 ns critical-path diagnosis](critical-path-3ns.md) | [`critical_path_3ns`](../../results/critical_path_3ns/) |
| 4 | [Candidate masks](candidate-mask-optimization.md) | [`candidate_mask`](../../results/candidate_mask/) |
| 5 | [Storage timing and free-slot experiments](storage-timing-experiment.md) | [`storage_timing`](../../results/storage_timing/) |
| 6 | [Command masks and storage](command-mask-optimization.md) | [`command_mask`](../../results/command_mask/) |
| 7 | [Remaining command-output paths](command-path-3ns.md) | [`command_path_3ns`](../../results/command_path_3ns/) |
| 8 | [Parallel command-class arbitration](parallel-arbitration-experiment.md) | [`parallel_arbitration`](../../results/parallel_arbitration/) |
| 9 | [Mapped hold repair](hold-repair-experiment.md) | [`hold_repair`](../../results/hold_repair/) |
| 10 | [Mapped setup-margin improvement](setup-margin-experiment.md) | [`setup_margin`](../../results/setup_margin/) |
| 11 | [Capacitance and library diagnosis](capacitance-diagnosis.md) | [`capacitance_diagnosis`](../../results/capacitance_diagnosis/) |

See the [documentation guide](../README.md) for design contracts and published
baseline results, or the [script guide](../../scripts/README.md) for verification
and report tools.
