# DRAM Memory Controller RTL

A synthesizable **SystemVerilog controller for a simplified, single-channel,
four-bank DRAM command protocol**, with configurable queue depth and three
scheduling policies. The project covers request ordering, bank timing,
backpressure, starvation protection, and measured ASIC area/timing tradeoffs.

[Five-minute design review](docs/portfolio-review.md) ·
[Architecture](docs/architecture.md) ·
[Verification](docs/verification-plan.md) ·
[Reproduce](docs/reproduce.md)

![Controller architecture: host requests enter the transaction table, bank candidates feed a selectable scheduler and command issue, and read returns feed an ordered response path. Bank timing controls legality; the behavioral DRAM model is simulation only.](docs/figures/controller-architecture.svg)

*Requests keep their transaction slots until the host consumes the response.
Bank timing legality and scheduling policy are separate blocks.*

## Results at a glance

| Study | Measured result | Evidence |
|---|---|---|
| **Current RTL: parallel arbitration** | Q=16 / 3 ns setup slack **−0.068773 → +0.000038 ns**; **50 → 0 setup violations**, with **1.89% lower mapped area** and no added cycle latency | [Matched experiment](docs/experiments/parallel-arbitration-experiment.md) |
| **Earlier address-sharing revision** | **16.71% lower mapped area** at Q=16 / 5 ns; **24.19% lower** at Q=32 / 5 ns | [Separate before/after measurements](docs/experiments/address-sharing-optimization.md) |
| **Frozen v1.1 scheduling study** | Always-ready random traffic: **0.146 → 0.419 responses/cycle**, Strict-FCFS → FR-FCFS, averaged across 20 seeds | [Multi-seed results](docs/performance-stability.md) |
| **Frozen v1.1 aging tradeoff** | Hot/cold p99 latency **333 → 137 cycles**; throughput **0.481 → 0.462 responses/cycle** | [Workload and metric definitions](docs/results.md#performance) |
| **Current RTL verification** | **300 regression runs**, **3,003,000 accepted transactions**, and **42 directed/workload/reset/corner simulations**, plus unit checks | [Source-matched validation](results/parallel_arbitration/validation_summary.json) |

ASIC measurements use Synopsys Design Compiler and the GSCL45nm typical library,
with ideal clocks and pre-layout mapping. The current 3 ns setup margin is only
**0.038 ps**; hold and the library's zero-limit capacitance violations remain.
These results establish an RTL optimization, not physical timing signoff.
Each study above has its own baseline; the historical area and performance
measurements are not new measurements of the current RTL.

## Architecture and design choices

- **Separate legality from policy.** Per-bank timing and preparation ownership
  determine which commands can issue. Strict-FCFS provides a head-of-line
  baseline; FR-FCFS prefers ready columns; aging protects the oldest aged
  request's command service, at a measured throughput cost.
- **Preserve ordering where required.** Same-address operations and host
  responses follow acceptance order; independent addresses may bypass. An
  explicit older-than matrix avoids sequence-number wraparound but costs
  quadratic storage/logic as queue depth grows.
- **Handle backpressure without losing completion capacity.** Requests retain
  their slots until response consumption. The response register holds stalled
  payloads stable and can consume/refill from an already-eligible independent
  completion on the same edge. The isolated tCCD=1 study sustains one response
  per cycle; default tCCD=2 still limits column issue to 0.5/cycle.
- **Optimize a measured dependency.** Critical-path analysis led to computing
  column and PRE/ACT oldest winners in parallel, then selecting the command
  class. This removes a serial arbitration dependency without adding pipeline
  stages or state. A deliberately wrong class selector is rejected by equivalence.

![Arbitration before and after: the baseline selects the command class before oldest-winner arbitration; current RTL computes column and PRE/ACT winners in parallel, then selects using column presence.](docs/figures/parallel-arbitration.svg)

*The change moves class selection after parallel winner computation. This is an
RTL dependency sketch; box sizes do not represent measured delays. See the
[matched timing experiment](docs/experiments/parallel-arbitration-experiment.md).*

Default RTL: 16 outstanding slots, 32-bit words, 256 rows × 64 columns per bank,
three-cycle read latency, and FR-FCFS with aging. Timing parameters are illustrative
cycle counts. The interface supports full-word requests and tagged responses;
PHY, refresh, training, bursts, ECC and JEDEC compliance are outside this project.
See the [protocol contract](docs/protocol-and-timing.md) for ordering and reset.

## Verification and reproducibility

The current optimization is checked with **nine whole-controller equivalence
configurations** (Q=1/3/16 × three policies) and **120 complete baseline/current
cycle-trace pairs**, in addition to the simulations above. Property checks include
three depth-12 controller BMC tasks with symbolic data and two focused unbounded
control proofs in reduced configurations. This is not an all-parameter unbounded
proof of data correctness. See [proof scope](docs/verification-plan.md).

Published evidence retains source/report hashes and matched synthesis conditions.
A [fresh-checkout audit](docs/reproduce.md#fresh-checkout-audit) reproduces local
checks, equivalence, traces and properties; its regression portion is a 15-run
sample. The full 300-run result is recorded separately.

Start from the repository root with the evidence audit, which needs only Python
and Git. Simulation needs Python 3.10+, Verilator supporting
`--binary --timing --assert`, a C++ compiler and make. Run commands sequentially:

```sh
make check-evidence                      # inspect published hashes and measurements
make lint
make smoke
make test
make regress SEEDS=5 N=1000 JOBS=2        # 15-run regression sample
```

For equivalence and traces, install Yosys, then run:

```sh
make formal-parallel                    # all nine equivalence configurations
make compare-parallel                   # 120 complete trace pairs
```

`make formal` runs the five property tasks with SymbiYosys. The
[reproduction guide](docs/reproduce.md) documents tested tools, full regression,
historical checkpoints and optional synthesis. New mapped PPA requires licensed
Synopsys tools and the matching library. `make report` republishes historical
artifacts and can overwrite frozen evidence; it is not part of the quickstart.

## Repository guide

| Location | Contents |
|---|---|
| `rtl/`, `tb/` | Current controller RTL, simulation testbenches and DRAM model |
| `formal/` | Property harnesses, task configurations and historical reference RTL |
| `synth/` | RTL manifest, constraints and DC / PrimeTime flows |
| [`scripts/`](scripts/README.md) | Daily checks, synthesis tools and historical report publishers |
| [`docs/`](docs/README.md) | Design contracts, verification, reproduction and result explanations |
| [`docs/experiments/`](docs/experiments/README.md) | Optimization history, timing diagnoses and rejected alternatives |
| [`results/`](results/README.md) | Published summaries, selected reports and frozen source snapshots |
| `build/`, `.tools/`, `local_notes/` | Ignored working outputs, local dependencies and private notes |

For a technical review, start with the [five-minute walkthrough](docs/portfolio-review.md),
then inspect the [current experiment](docs/experiments/parallel-arbitration-experiment.md)
and its linked reports. The [experiment index](docs/experiments/README.md) preserves
both adopted changes and rejected alternatives, including their tradeoffs.
