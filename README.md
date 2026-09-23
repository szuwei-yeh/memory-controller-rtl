# memory-controller-rtl

A synthesizable SystemVerilog controller for a **simplified, single-channel,
four-bank DRAM command protocol**. This portfolio explores bank parallelism,
timing enforcement, scheduling, starvation protection, ordering, verification,
and ASIC implementation tradeoffs. It is not a DDR PHY or JEDEC-compliant device
controller.

## Final v1.1 results — portfolio frozen

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
[ASIC evidence](docs/asic-results.md), and the [release audit](docs/release-audit.md)
for scope, provenance, reproduction status, and limitations.

## Run locally

Requires Python 3.10+, Verilator with `--binary --timing --assert`, a C++ compiler,
and make. The tested tool versions and actual results are in [results](docs/results.md).

```sh
make lint
make smoke
make test
make regress                    # 100 seeds × 10,000 workload requests × 3 policies
make perf                       # identical workloads, warm-up, latency distributions
make formal                     # SymbiYosys, Yosys and ABC
make synth-local-sanity         # optional generic Yosys check, not ASIC evidence
make report                     # requires the preceding run outputs and Matplotlib/NumPy
make lab-bundle                 # explicit allowlist; does not upload anything
```

`build/` contains build logs, simulation event traces, commands, and machine-readable
results. Builds are cached by RTL/testbench content, parameters, and Verilator version.
Regression can be shortened with `make regress SEEDS=5 N=1000 JOBS=4`.

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

- [Frozen architecture and milestones](docs/architecture.md)
- [Interface, timing edges, ordering, and reset](docs/protocol-and-timing.md)
- [Verification strategy and coverage](docs/verification-plan.md)
- [Measured local results and limitations](docs/results.md)
- [Response-refill amendment and before/after measurements](docs/response-refill.md)
- [Annotated command traces](docs/traces.md)
- [UCSB Design Compiler / PrimeTime flow](docs/lab-flow.md)
- [Executed UCSB 5 ns baseline: setup meets, hold/capacitance violations remain](docs/ucsb-baseline.md)
- [Frozen 30-point ASIC area/timing sweep and baseline hold diagnostics](docs/asic-results.md)
- [Verified toolchain and isolated setup](docs/toolchain.md)

Final ASIC evidence comes from the UCSB lab's Design Compiler and technology
library. The supplied flow includes SDC, mapped reports, a clock-period sweep,
and optional PrimeTime. Local generic gate counts are not mapped ASIC area or frequency.
