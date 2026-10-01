# memory-controller-rtl

A synthesizable SystemVerilog controller for a **simplified, single-channel,
four-bank DRAM command protocol**. This portfolio explores bank parallelism,
timing enforcement, scheduling, starvation protection, ordering, verification,
and ASIC implementation tradeoffs. It is not a DDR PHY or JEDEC-compliant device
controller.

## Current ASIC optimization

Parallel column/PRE-ACT arbitration changes Q=16/3 ns setup slack from
**−0.068773 to +0.000038 ns**, removing all **50 setup violations** relative to
the selected command-mask plus storage revision. Mapped area decreases
**1.89% at 3 ns** and **0.44% at 4 ns**. The 4 ns setup margin increases from
+0.000109 to +0.001984 ns. No pipeline, storage or command latency is added.
See the [parallel-arbitration experiment](docs/parallel-arbitration-experiment.md)
for matched measurements, verification and adoption criteria.
The measured RTL passes nine whole-controller equivalence configurations,
120 complete trace pairs, 42 directed/corner simulations, five formal tasks,
and 300 regression runs with 3,003,000 accepted transactions.

**3 ns setup passes with only 0.038 ps margin; hold still fails at both targets**
(eight endpoints at 3 ns, two at 4 ns). These typical-corner, ideal-clock,
pre-layout results are not timing closure or a routed-frequency claim.
The preceding [command-mask experiment](docs/command-mask-optimization.md)
retains its three alternatives and source-matched evidence. The earlier
[address-sharing experiment](docs/address-sharing-optimization.md) achieved
16.71% area reduction at Q=16/5 ns and 24.19% at Q=32/5 ns; those measurements
belong to that earlier revision, not the current mask RTL.
The [candidate-mask](docs/candidate-mask-optimization.md) and standalone
[storage timing](docs/storage-timing-experiment.md) studies retain their historical
measurements. The latter rejected fixed-slot writes alone; the new combined
implementation was independently measured before the parallel-arbitration change.

## Published v1.1 results

- **Verification:** 3,003,000 accepted transactions across 300 randomized regression
  runs; 42 directed/workload/reset/corner simulations plus model, scheduler, and
  response unit checks. Five formal tasks pass: three depth-12 controller BMC
  checks and two focused unbounded control proofs in reduced configurations.
- **Scheduling:** in the 20-seed always-ready random study, FR-FCFS averaged
  0.419 responses/cycle versus 0.146 for Strict-FCFS. On hot/cold traffic,
  aging reduced p99 latency from 333 to 137 cycles, with throughput falling
  from 0.481 to 0.462 responses/cycle. Aging protects command service;
  response consumption still requires host readiness.
- **Response path:** the isolated tCCD=1 row-hit experiment sustains **1 response/cycle**
  (previously 0.5). Default tCCD=2 still limits column issue to 0.5/cycle.
  The paired random/50%-ready study found a systematic p99 increase of 8.8 cycles
  across 20 seeds, alongside 28.6% higher throughput and 23.1% lower mean latency.
- **ASIC:** 30 Synopsys Design Compiler runs using the inherited GSCL45nm typical
  library and fixed medium mapping effort; 25 tested setup targets pass.
  At Q=16 and 5 ns, mapped areas are 76,534 / 78,520 / 80,975 µm² for
  Strict-FCFS / FR-FCFS / FR-FCFS+aging. Doubling Q from 16 to 32 costs roughly
  3× area. The **fastest tested setup-passing targets** at Q=16 are respectively
  **3 ns (333.33 MHz), 4 ns (250 MHz), and 4 ns (250 MHz)**, not exact maximum frequencies.

These are simplified-protocol simulations and **pre-layout** mapped ASIC results,
not JEDEC compliance, post-layout timing, or physical DDR bandwidth. Hold violations
remain. The inherited library's zero allowed-load/max-capacitance constraints also
remain violated and are not waived. Setup passes do not imply timing signoff.
See [local evidence](docs/results.md), [multi-seed stability](docs/performance-stability.md),
and [ASIC evidence](docs/asic-results.md) for methodology and limitations.

## Run locally

Requires Python 3.10+, Verilator with `--binary --timing --assert`, a C++ compiler,
and make. See [tool setup](docs/results.md#tool-setup) and
[workloads](docs/results.md#workloads) for dependencies and experiment definitions.

```sh
make lint
make smoke
make test
make regress                    # 100 seeds × 10,000 workload requests × 3 policies
make perf                       # identical workloads, warm-up, latency distributions
make formal                     # SymbiYosys, Yosys and ABC
make formal-command-mask        # whole-controller equivalence at Q=1/3/16, all policies
make compare-command-mask       # 120 complete old/new cycle-trace pairs
make formal-parallel            # current controller vs selected command-mask baseline
make compare-parallel           # 120 complete baseline/current cycle-trace pairs
make synth-local-sanity         # optional generic Yosys check, not ASIC evidence
make report                     # requires the preceding run outputs and Matplotlib/NumPy
make lab-bundle                 # explicit allowlist; does not upload anything
```

`build/` contains build logs, simulation event traces, commands, and machine-readable
results. Builds are cached by RTL/testbench content, parameters, and Verilator version.
Regression can be shortened with `make regress SEEDS=5 N=1000 JOBS=4`.
Earlier encoded-interface checks are reproduced at their recorded checkpoints:
`27f522c` for candidate decoding and `12db399` for address sharing.
The compact candidate-mask snapshot is preserved under `results/candidate_mask/variants/`.

## Architecture

Requests occupy transaction-table slots through response consumption. Same-address
memory operations **and host responses** preserve acceptance order; independent
addresses may bypass. There is no global in-order retirement buffer.
The response register can consume and refill in the same cycle from another
already-eligible independent completion, sustaining one response per cycle when
such completions are available. Stalled payloads remain stable; same-address
successors retain the conservative pre-edge eligibility rule.

| Policy identifier | Behavior |
|---|---|
| `strict_fcfs` | Strict Request FCFS / Strict-FCFS (HOL baseline): a blocked oldest pending request stalls all command issue |
| `frfcfs` | Bank-aware ready-column-first, oldest-first arbitration with open-row preference |
| `frfcfs_aging` | FR-FCFS plus bounded emergency protection for the oldest aged request |

ACT/READ/WRITE/PRE use independent bank state and tRCD/tRP/tRAS/tWR counters;
tCCD is channel-wide. A preparation owner reserves a bank through its column
command. Aging protection drains an existing owner before the protected request
and prevents unrelated column commands from consuming its next tCCD opportunity.

Read values snapshot at READ issue and return after fixed latency. Writes commit
with their command. Requests are full-word transfers; there are no bursts or byte masks.

## Design and evidence

- [Architecture](docs/architecture.md)
- [Interface, timing, ordering, and reset](docs/protocol-and-timing.md)
- [Verification strategy and proof scope](docs/verification-plan.md)
- [Performance, response throughput, workloads, and reproduction](docs/results.md)
- [Multi-seed performance stability](docs/performance-stability.md)
- [ASIC area/timing tradeoffs and synthesis setup](docs/asic-results.md)
- [Candidate-decode optimization and paired ASIC evidence](docs/scheduler-optimization.md)
- [Shared address comparisons and matched ASIC evidence](docs/address-sharing-optimization.md)
- [3 ns critical-path breakdown and next experiment](docs/critical-path-3ns.md)
- [Candidate-mask timing experiment and remaining violations](docs/candidate-mask-optimization.md)
- [Storage timing diagnosis and free-slot experiments](docs/storage-timing-experiment.md)
- [Direct command-mask and storage optimization](docs/command-mask-optimization.md)
- [Remaining 68.8 ps: selected command-path analysis](docs/command-path-3ns.md)
- [Parallel command-class arbitration and 3 ns setup pass](docs/parallel-arbitration-experiment.md)
- [Annotated command traces](docs/traces.md)

ASIC evidence uses Synopsys Design Compiler and the GSCL45nm typical library.
Local generic Yosys counts are synthesizability evidence, not mapped ASIC area or frequency.
