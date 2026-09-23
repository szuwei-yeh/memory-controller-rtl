# Measured local results

The verification and performance results below come from executed local runs.
The subsequent [UCSB Design Compiler baseline](ucsb-baseline.md) maps the unchanged
v1.1 RTL at 5 ns: 80,975.37 µm² cell area and +0.001615 ns worst setup slack.
It is not timing/DRC clean: 14 hold and 5,556 library max-capacitance violations
remain. The subsequent [30-point frozen ASIC sweep](asic-results.md) is complete:
25 targets pass setup, with hold and inherited capacitance violations retained.
PrimeTime has not been run.

## Verification

- Verilator: `Verilator 5.046 2026-02-28 rev vUNKNOWN-built20260228`.
- Yosys: `Yosys 0.68+post (git sha1 c12172fbae8af5e20f6fb52e3d4e92d56ed587b6, Release, AppleClang clang++ 16.0.0.16000026)`.
- 300 regression runs passed; 3,003,000 accepted transactions,
  comprising 100 seeds × 10,000 workload requests × three policies plus directed preludes.
- 42 directed/workload/reset/parameter-corner runs passed.
- Two legal model boundary traces, eight expected-failure traces, and the defensive
  existing-owner aging arbitration test passed.
- The response-refill test passed: eight consecutive independent handshakes,
  stable stalled payloads, ordered same-address consumption, and reset cancellation.
- RTL lint passed. Optional generic Yosys synthesis completed; it is a synthesizability check.
- Private-directory ignore/tracking and allowlisted lab-bundle checks passed.

Aggregated coverage counts (events/cycles, not percentages):

```json
{
  "protection": 1471,
  "same_addr_block": 21287036,
  "independent_bypass": 3113098,
  "overlap": 407,
  "full": 342,
  "bank_overlap": 1617766,
  "protected_owner_block": 0
}
```

Same-address blocking counts blocked transaction-cycles. The zero existing-owner
count reflects the normal bank-preparation invariant; its defensive branch is
tested separately by `tb_scheduler`, as described in the verification plan.

## Formal evidence and limits

| Task | Mode | Depth | Outcome |
|---|---|---|---|
| strict | bmc | 12 | PASS |
| frfcfs | bmc | 12 | PASS |
| aging | bmc | 12 | PASS |
| bank | prove | unbounded | PASS |
| progress | prove | unbounded | PASS |

Integrated BMC covers symbolic data, addresses, operation mix, tags, and backpressure
for a two-slot configuration. It is not an unbounded data-correctness proof.
The bank proof establishes timing-permission equivalence to independent elapsed-cycle
counters under legal issue assumptions. The progress proof checks mixed reads/writes,
all four banks, two slots, fixed one-cycle reads, small positive timing values and
age threshold three. Payloads are zero; response readiness is unrestricted. It proves
the conservative 63-cycle pending-service bound for this reduced control configuration,
plus ownership/ordering/capacity assertions. It does not prove all parameter settings.

Earlier integrated 80-cycle attempts with Z3 and ABC timed out. Splitting focused
control proofs from bounded symbolic-data checks made the final suite tractable.

## Performance

Simulation configuration: four banks, eight rows × eight columns per bank, 32-bit
words, 16 outstanding slots, read latency three; timing 3/3/6/2/3 and aging 128.
Each experiment uses seed 42, 200 warm-up requests, 2,000 measured requests, fixed
request sequences, and complete drain. The table uses always-ready responses and
one offered request per cycle. Throughput includes the measured cohort's drain.

| Workload | Policy | Responses/cycle | Mean latency | p99 | Maximum |
|---|---|---:|---:|---:|---:|
| row_hit | Strict-FCFS (HOL baseline) | 0.496 | 31.0 | 32 | 32 |
| row_hit | FR-FCFS | 0.496 | 31.0 | 32 | 32 |
| row_hit | FR-FCFS + aging | 0.496 | 31.0 | 32 | 32 |
| row_conflict | Strict-FCFS (HOL baseline) | 0.110 | 143.0 | 143 | 143 |
| row_conflict | FR-FCFS | 0.449 | 34.4 | 68 | 68 |
| row_conflict | FR-FCFS + aging | 0.449 | 34.4 | 68 | 68 |
| random | Strict-FCFS (HOL baseline) | 0.147 | 107.4 | 125 | 131 |
| random | FR-FCFS | 0.417 | 37.0 | 72 | 93 |
| random | FR-FCFS + aging | 0.417 | 37.0 | 72 | 93 |
| hot_cold | Strict-FCFS (HOL baseline) | 0.361 | 43.0 | 44 | 44 |
| hot_cold | FR-FCFS | 0.481 | 31.9 | 333 | 403 |
| hot_cold | FR-FCFS + aging | 0.462 | 33.3 | 137 | 137 |
| hol | Strict-FCFS (HOL baseline) | 0.305 | 51.0 | 51 | 51 |
| hol | FR-FCFS | 0.495 | 30.9 | 102 | 105 |
| hol | FR-FCFS + aging | 0.495 | 30.9 | 102 | 105 |

![Reproducible throughput, tail-latency and offered-load comparisons](../results/performance.png)

[Annotated command traces](traces.md) show a row conflict, overlapping bank
activations, and a measured aging intervention from these runs.

The response holding register now consumes and refills on the same edge for
already-eligible independent transactions. The default tCCD=2 limits sustained
column-command throughput to 0.5/cycle; row-hit traffic approaches that limit across
all policies. A separate tCCD=1 capacity experiment isolates the response path's
one-per-cycle capability; see [before/after response-refill results](response-refill.md).
FR-FCFS
improves locality and bank overlap on conflicts and random traffic. Hot/cold traffic
shows its tail-latency cost; aging trades some throughput for a shorter tail.
At low offered load, latency reflects individual service rather than a full queue.
These are abstract word-transfer results, not physical DDR bandwidth measurements.

## Reproduce

See the [v1.1 portfolio release audit](release-audit.md) for clean-checkout
validation and the boundary between local reproduction and licensed lab runs.

The subsequent [frozen v1.1 stability study](performance-stability.md) covers 20
seeds for random, hot/cold, and HOL traffic at 100%, 50%, and 20% ready across all
three policies. Its 540 final-design runs and 60 historical random/50% paired runs
all passed. The FR-FCFS random/50% p99 increase is consistent across all 20 seeds
(mean +8.8 cycles), alongside 28.6% higher throughput and 23.1% lower mean latency.
The report includes all per-seed metrics and explains the deterministic hot/cold
and HOL stimulus limitation. Controller RTL and testbench hashes are unchanged.

```sh
make lint test
make regress SEEDS=100 N=10000 JOBS=4
make formal
make perf
make synth-local-sanity
make lab-bundle
make report
```

Machine-readable public results and RTL hashes are in `results/local_summary.json`.
Detailed commands, source hashes, logs and CSV events are retained locally under
`build/`. The publication script reads only explicitly selected build summaries
and traces; it never reads the private engineering notebook.
