# Response-refill microarchitecture amendment

Only `rtl/mc_response.sv` changes in the controller. The exact patch is in
`results/response_refill.patch`. No scheduler, transaction table, timing, interface,
or default parameter changed. No global retirement buffer or additional registers
were introduced.

## Exact change

Previously, a valid/ready handshake cleared `held_valid`; selection occurred only
on a later edge with an empty register. Now a combinational `selectable` mask excludes
the currently held slot from both candidate selection and the oldest-candidate
comparison. On `!held_valid || rsp_ready`, the register loads that winner and its valid
bit. An occupied, stalled register is not updated.

Same-address eligibility still examines all pre-edge occupied entries, including
the consumed predecessor. Newly unblocked successors cannot refill on that edge.
Already-eligible independent transactions can refill immediately. This removes the
global selection bubble while preserving the conservative same-address rule and
stable payload under backpressure. `rsp_ready` does not feed combinational `rsp_valid`.

## Directed verification and complete checks

- The new `tb_response` fails on the original RTL's second expected consecutive response.
- It passes eight consecutive independent handshakes on the revised RTL.
- It covers a held response stalled while an older independent completion becomes ready,
  oldest-other replacement, same-address consumption order, the retained same-address
  bubble, final-entry non-duplication, and reset cancellation.
- Formal assertions check no reselection of the held slot and next-cycle occupancy/slot
  after a handshake with an available replacement; previous stability/order checks remain.
- 42 directed/workload/reset/corner runs passed, plus the response,
  scheduler and model unit tests. RTL lint passed.
- 300 full regression runs passed: 3,003,000
  accepted transactions (100 × 10,000 requests × three policies, plus preludes).
- All five formal tasks passed: three depth-12 symbolic-data BMC tasks, bank timing PDR,
  and reduced mixed-read/write progress PDR. These proof scope limits are unchanged.
- Revised performance experiments were run after correctness passed. No UCSB DC/PT run
  was started for this amendment.

## Row-hit maximum throughput

Identical before/after workload: 64 columns, 16 slots, three-cycle READ latency,
seed 42, 200 warm-up and 5,000 measured requests, 75/25 read/write mix, ready always
asserted, one offered request per cycle. Only the test's tCCD changes between rows.

Response-window rate is `(N-1)/(last_response-first_response)`. Cohort throughput is
`N/(last_response-first_acceptance+1)` and includes drain/queue latency. The longest
consecutive sequence establishes actual adjacent-cycle handshakes, not just an average.

| Policy | tCCD | Response-window rate, old → new | Cohort rate, old → new | Longest consecutive handshakes, old → new |
|---|---:|---:|---:|---:|
| strict_fcfs | 1 | 0.500000 → 1.000000 | 0.498504 → 0.997606 | 1 → 5000 |
| frfcfs | 1 | 0.500000 → 1.000000 | 0.498504 → 0.997606 | 1 → 5000 |
| frfcfs_aging | 1 | 0.500000 → 1.000000 | 0.498504 → 0.997606 | 1 → 5000 |
| strict_fcfs | 2 | 0.500000 → 0.499850 | 0.498504 → 0.498405 | 1 → 3 |
| frfcfs | 2 | 0.500000 → 0.499850 | 0.498504 → 0.498405 | 1 → 3 |
| frfcfs_aging | 2 | 0.500000 → 0.499850 | 0.498504 → 0.498405 | 1 → 3 |

The response path's capability is one response/cycle when independent eligible
completions exist. Default tCCD=2 still limits DRAM column commands to one every
two cycles, so removing the response bubble does not double default row-hit throughput.

## Default-timing workload changes

The regular 48-experiment suite retains its original eight-column geometry,
seed 42, 200 warm-up/2,000 measured requests, and tCCD=2. Table entries below use
ready=100% and one offered request/cycle. Full distributions and load/backpressure
sweeps are in `results/response_refill_comparison.json`.

| Policy | Workload | Responses/cycle, old → new | Mean latency, old → new | p99 latency, old → new |
|---|---|---:|---:|---:|
| strict_fcfs | row_hit | 0.4963 → 0.4960 | 31.00 → 31.00 | 31 → 32 |
| strict_fcfs | sequential | 0.3781 → 0.3779 | 41.02 → 41.02 | 52 → 52 |
| strict_fcfs | row_conflict | 0.1103 → 0.1103 | 143.00 → 143.00 | 143 → 143 |
| strict_fcfs | random | 0.1465 → 0.1465 | 107.37 → 107.37 | 125 → 125 |
| strict_fcfs | hot_cold | 0.3609 → 0.3608 | 43.00 → 43.00 | 43 → 44 |
| strict_fcfs | hol | 0.3054 → 0.3054 | 51.00 → 51.00 | 51 → 51 |
| strict_fcfs | read_only | 0.1469 → 0.1469 | 107.13 → 107.13 | 125 → 125 |
| strict_fcfs | read_write_50 | 0.1463 → 0.1463 | 107.49 → 107.49 | 125 → 125 |
| strict_fcfs | write_only | 0.1456 → 0.1456 | 108.05 → 108.05 | 125 → 125 |
| strict_fcfs | same_address | 0.4963 → 0.4963 | 31.00 → 31.00 | 31 → 31 |
| frfcfs | row_hit | 0.4963 → 0.4960 | 31.00 → 31.00 | 31 → 32 |
| frfcfs | sequential | 0.4812 → 0.4810 | 32.00 → 32.00 | 35 → 36 |
| frfcfs | row_conflict | 0.4486 → 0.4486 | 34.35 → 34.35 | 68 → 68 |
| frfcfs | random | 0.4153 → 0.4173 | 37.20 → 37.01 | 71 → 72 |
| frfcfs | hot_cold | 0.4817 → 0.4815 | 31.86 → 31.86 | 333 → 333 |
| frfcfs | hol | 0.4952 → 0.4952 | 30.90 → 30.90 | 101 → 102 |
| frfcfs | read_only | 0.4128 → 0.4128 | 37.44 → 37.44 | 67 → 67 |
| frfcfs | read_write_50 | 0.4131 → 0.4167 | 37.39 → 37.06 | 70 → 72 |
| frfcfs | write_only | 0.4181 → 0.4181 | 36.93 → 36.93 | 76 → 76 |
| frfcfs | same_address | 0.4963 → 0.4963 | 31.00 → 31.00 | 31 → 31 |
| frfcfs_aging | row_hit | 0.4963 → 0.4960 | 31.00 → 31.00 | 31 → 32 |
| frfcfs_aging | sequential | 0.4812 → 0.4810 | 32.00 → 32.00 | 35 → 36 |
| frfcfs_aging | row_conflict | 0.4486 → 0.4486 | 34.35 → 34.35 | 68 → 68 |
| frfcfs_aging | random | 0.4153 → 0.4173 | 37.20 → 37.01 | 71 → 72 |
| frfcfs_aging | hot_cold | 0.4617 → 0.4617 | 33.34 → 33.34 | 137 → 137 |
| frfcfs_aging | hol | 0.4952 → 0.4952 | 30.90 → 30.90 | 101 → 102 |
| frfcfs_aging | read_only | 0.4128 → 0.4128 | 37.44 → 37.44 | 67 → 67 |
| frfcfs_aging | read_write_50 | 0.4131 → 0.4167 | 37.39 → 37.06 | 70 → 72 |
| frfcfs_aging | write_only | 0.4181 → 0.4181 | 36.93 → 36.93 | 76 → 76 |
| frfcfs_aging | same_address | 0.4963 → 0.4963 | 31.00 → 31.00 | 31 → 31 |

The benefit is larger while draining completions accumulated under backpressure.
For random traffic with FR-FCFS + aging (the same deterministic 100-cycle ready pattern):

| Ready duty cycle | Responses/cycle, old → new | Mean latency, old → new | p99 latency, old → new |
|---|---:|---:|---:|
| 80% | 0.3889 → 0.4066 | 39.77 → 38.09 | 67 → 75 |
| 50% | 0.2491 → 0.3201 | 63.00 → 48.47 | 81 → 90 |
| 20% | 0.0999 → 0.1956 | 158.60 → 80.42 | 191 → 98 |

Even with tCCD unchanged, response timing changes transaction-slot availability and
therefore which requests are visible to the scheduler. Throughput or tail latency
need not improve on every workload; no scheduler policy or aging rule was changed.

## Local Yosys implications

Paired default-Q=16 generic synthesis, identical source files except mc_response,
same Yosys flow and settings. Cells are generic one-bit mapped primitives, not
standard-cell ASIC area. Logic depth is Yosys `ltp -noff` for the response module.

| Metric | Before | After |
|---|---:|---:|
| controller_cells | 28923 | 29582 |
| controller_flops | 1974 | 1974 |
| response_cells | 6320 | 6717 |
| response_flops | 5 | 5 |
| response_logic_depth | 30 | 29 |
| latches | 0 | 0 |

The mask adds held-slot exclusion to the arbitration cone. The register-update enable
now permits consume/refill; the held payload still comes from the existing table.
This changes a register-to-register feedback path from held slot/valid through winner
selection to the next held slot/valid. Cell-count and topological-depth differences
are structural observations only: Yosys has no lab library or SDC-based delay analysis
here. DC/PrimeTime must establish mapped setup slack and frequency; no Fmax is inferred.
The unchanged transaction table also maps to a different generic cell count in
these runs, so the whole-controller delta is not entirely added response logic.
No other controller RTL changed; mapping heuristics depend on the synthesis context.

## Reproduce

```sh
make lint test
make regress SEEDS=100 N=10000 JOBS=4
make formal
# Only after the correctness commands pass:
make perf
python3 scripts/response_capacity.py --label after
make synth-local-sanity
mkdir -p build/response_refill     # report log destination in a clean checkout
python3 scripts/response_refill_report.py
make report
```

The pre-change measurements, RTL hashes, and synthesis summary are retained in
`results/response_capacity_before.json` and `results/response_refill_before.json`.
To rebuild the old revision, reverse the published patch in a separate copy; do not
replace the working controller. Local raw baseline snapshots are under
`build/response_refill/before/`. The private Traditional Chinese notebook records the
decision, baseline, verification, and before/after experiment results; it is excluded
from Git and all export bundles.
