# Frozen v1.1 performance stability study

The controller RTL and testbench are unchanged. All **540 final-design runs** and
**60 historical paired runs** passed their existing self-checks and drained completely:
1,326,000 accepted transactions, including 1,200,000 measured transactions.

## Experiment design

- Seeds: **1–19 and 42**, fixed before running; 20 seeds per condition.
- Final design: random, hot_cold, hol × ready 100%, 50%, 20% × strict_fcfs, frfcfs, frfcfs_aging.
- Historical comparison: random/50% for every policy and the same 20 seeds.
- Per run: fixed ten-request directed prelude, 200 workload warm-up requests, 2,000 measured requests, complete drain.
- Four banks, simulation ROWS=8 and COLS=8, 32-bit data, Q=16, read latency 3, tRCD/tRP/tRAS/tCCD/tWR=3/3/6/2/3, aging threshold 128.
- Offered interval one cycle, offered load 100%, 25% writes. Ready is asserted when cycle modulo 100 is below the requested percentage; final drain forces ready high.
- Latency is acceptance to response consumption, in cycles. Throughput is measured responses divided by the inclusive interval from first measured acceptance to last measured response.
- Per-run p95/p99 use sorted samples at floor(q × (n−1)), matching prior results. Cross-seed summaries treat each run equally; percentiles are not pooled.

The historical controller is reconstructed under ignored `build/` using the reverse
of `results/response_refill.patch`; all seven historical RTL hashes are checked.
All 60 paired acceptance address/operation sequences match, and seed 42 reproduces
all five earlier metrics exactly for both revisions and all three policies.

## Random traffic at 50% ready: paired old → v1.1

Values below are averages of the 20 per-seed metrics. Δ is v1.1 minus old.

| Policy | Responses/cycle | Mean latency | p95 | p99 | Maximum |
|---|---:|---:|---:|---:|---:|
| strict_fcfs | 0.1464 → 0.1463 | 107.45 → 107.48 | 156.65 → 155.60 | 164.55 → 163.85 | 173.55 → 172.95 |
| frfcfs | 0.2491 → 0.3203 | 63.00 → 48.42 | 81.00 → 86.45 | 81.20 → 90.00 | 88.60 → 94.60 |
| frfcfs_aging | 0.2491 → 0.3203 | 63.00 → 48.42 | 81.00 → 86.45 | 81.20 → 90.00 | 88.60 → 94.60 |

| Policy | Mean p99 Δ | Median Δ | Δ range | Higher / equal / lower | 95% bootstrap interval for mean Δ | Sign-test p |
|---|---:|---:|---:|---:|---:|---:|
| strict_fcfs | -0.70 | -1.00 | -2–1 | 3 / 5 / 12 | [-1.15, -0.25] | 0.0351562 |
| frfcfs | 8.80 | 9.00 | 7–10 | 20 / 0 / 0 | [8.50, 9.05] | 1.90735e-06 |
| frfcfs_aging | 8.80 | 9.00 | 7–10 | 20 / 0 / 0 | [8.50, 9.05] | 1.90735e-06 |

Intervals use 10,000 paired-seed bootstrap resamples with fixed analysis RNG seed
20260922. The two-sided sign test excludes ties. These are descriptive intervals
for this seed set and generator, without adjustment for multiple comparisons.

## Final v1.1 distributions

Each cell is **cross-seed mean [minimum, maximum]**. Full sample standard
deviation and median for every metric are in the linked distribution CSV.

| Workload | Ready | Policy | Responses/cycle | Mean latency | p95 | p99 | Maximum |
|---|---:|---|---:|---:|---:|---:|---:|
| hol | 100% | frfcfs | 0.4952 [0.4952, 0.4952] | 30.90 [30.90, 30.90] | 85.00 [85.00, 85.00] | 102.00 [102.00, 102.00] | 105.00 [105.00, 105.00] |
| hol | 100% | frfcfs_aging | 0.4952 [0.4952, 0.4952] | 30.90 [30.90, 30.90] | 85.00 [85.00, 85.00] | 102.00 [102.00, 102.00] | 105.00 [105.00, 105.00] |
| hol | 100% | strict_fcfs | 0.3054 [0.3054, 0.3054] | 51.00 [51.00, 51.00] | 51.00 [51.00, 51.00] | 51.00 [51.00, 51.00] | 51.00 [51.00, 51.00] |
| hol | 50% | frfcfs | 0.3772 [0.3772, 0.3772] | 40.94 [40.94, 40.94] | 78.00 [78.00, 78.00] | 83.00 [83.00, 83.00] | 83.00 [83.00, 83.00] |
| hol | 50% | frfcfs_aging | 0.3772 [0.3772, 0.3772] | 40.94 [40.94, 40.94] | 78.00 [78.00, 78.00] | 83.00 [83.00, 83.00] | 83.00 [83.00, 83.00] |
| hol | 50% | strict_fcfs | 0.2921 [0.2921, 0.2921] | 53.49 [53.49, 53.49] | 86.00 [86.00, 86.00] | 86.00 [86.00, 86.00] | 86.00 [86.00, 86.00] |
| hol | 20% | frfcfs | 0.1997 [0.1997, 0.1997] | 79.00 [79.00, 79.00] | 95.00 [95.00, 95.00] | 96.00 [96.00, 96.00] | 96.00 [96.00, 96.00] |
| hol | 20% | frfcfs_aging | 0.1997 [0.1997, 0.1997] | 79.00 [79.00, 79.00] | 95.00 [95.00, 95.00] | 96.00 [96.00, 96.00] | 96.00 [96.00, 96.00] |
| hol | 20% | strict_fcfs | 0.1995 [0.1995, 0.1995] | 78.85 [78.85, 78.85] | 95.00 [95.00, 95.00] | 95.00 [95.00, 95.00] | 95.00 [95.00, 95.00] |
| hot_cold | 100% | frfcfs | 0.4815 [0.4815, 0.4815] | 31.86 [31.86, 31.86] | 93.00 [93.00, 93.00] | 333.00 [333.00, 333.00] | 403.00 [403.00, 403.00] |
| hot_cold | 100% | frfcfs_aging | 0.4617 [0.4617, 0.4617] | 33.34 [33.34, 33.34] | 47.00 [47.00, 47.00] | 137.00 [137.00, 137.00] | 137.00 [137.00, 137.00] |
| hot_cold | 100% | strict_fcfs | 0.3608 [0.3608, 0.3608] | 43.00 [43.00, 43.00] | 44.00 [44.00, 44.00] | 44.00 [44.00, 44.00] | 44.00 [44.00, 44.00] |
| hot_cold | 50% | frfcfs | 0.3503 [0.3503, 0.3503] | 44.49 [44.49, 44.49] | 79.00 [79.00, 79.00] | 96.00 [96.00, 96.00] | 99.00 [99.00, 99.00] |
| hot_cold | 50% | frfcfs_aging | 0.3503 [0.3503, 0.3503] | 44.49 [44.49, 44.49] | 79.00 [79.00, 79.00] | 96.00 [96.00, 96.00] | 99.00 [99.00, 99.00] |
| hot_cold | 50% | strict_fcfs | 0.3175 [0.3175, 0.3175] | 48.94 [48.94, 48.94] | 83.00 [83.00, 83.00] | 83.00 [83.00, 83.00] | 83.00 [83.00, 83.00] |
| hot_cold | 20% | frfcfs | 0.1996 [0.1996, 0.1996] | 78.88 [78.88, 78.88] | 95.00 [95.00, 95.00] | 97.00 [97.00, 97.00] | 97.00 [97.00, 97.00] |
| hot_cold | 20% | frfcfs_aging | 0.1996 [0.1996, 0.1996] | 78.88 [78.88, 78.88] | 95.00 [95.00, 95.00] | 97.00 [97.00, 97.00] | 97.00 [97.00, 97.00] |
| hot_cold | 20% | strict_fcfs | 0.1996 [0.1996, 0.1996] | 78.88 [78.88, 78.88] | 95.00 [95.00, 95.00] | 95.00 [95.00, 95.00] | 95.00 [95.00, 95.00] |
| random | 100% | frfcfs | 0.4187 [0.4150, 0.4234] | 36.85 [36.44, 37.14] | 59.35 [58.00, 61.00] | 69.35 [66.00, 74.00] | 86.60 [74.00, 95.00] |
| random | 100% | frfcfs_aging | 0.4187 [0.4150, 0.4234] | 36.85 [36.44, 37.14] | 59.35 [58.00, 61.00] | 69.35 [66.00, 74.00] | 86.60 [74.00, 95.00] |
| random | 100% | strict_fcfs | 0.1462 [0.1446, 0.1496] | 107.58 [105.29, 108.80] | 120.25 [117.00, 122.00] | 123.95 [121.00, 125.00] | 127.60 [123.00, 131.00] |
| random | 50% | frfcfs | 0.3203 [0.3174, 0.3228] | 48.42 [48.13, 48.94] | 86.45 [86.00, 87.00] | 90.00 [89.00, 91.00] | 94.60 [93.00, 97.00] |
| random | 50% | frfcfs_aging | 0.3203 [0.3174, 0.3228] | 48.42 [48.13, 48.94] | 86.45 [86.00, 87.00] | 90.00 [89.00, 91.00] | 94.60 [93.00, 97.00] |
| random | 50% | strict_fcfs | 0.1463 [0.1449, 0.1496] | 107.48 [105.14, 108.72] | 155.60 [153.00, 157.00] | 163.85 [162.00, 165.00] | 172.95 [169.00, 179.00] |
| random | 20% | frfcfs | 0.1958 [0.1952, 0.1971] | 80.28 [79.61, 80.63] | 97.00 [97.00, 97.00] | 98.05 [98.00, 99.00] | 99.05 [99.00, 100.00] |
| random | 20% | frfcfs_aging | 0.1958 [0.1952, 0.1971] | 80.28 [79.61, 80.63] | 97.00 [97.00, 97.00] | 98.05 [98.00, 99.00] | 99.05 [99.00, 100.00] |
| random | 20% | strict_fcfs | 0.1466 [0.1449, 0.1499] | 107.42 [105.35, 108.55] | 184.95 [183.00, 186.00] | 187.85 [187.00, 189.00] | 189.45 [188.00, 191.00] |

## Interpretation and limits

**The random-traffic p99 increase at 50% ready is systematic in this study, not
just a seed-42 fluctuation.** For both FR-FCFS configurations, all 20 paired seeds
increase by 7–10 cycles: mean +8.80 cycles, median +9, paired bootstrap 95% interval
[+8.50, +9.05]. Average per-seed p99 moves from 81.20 to 90.00 cycles. These two
configurations produce identical metrics on the tested random streams, so they
are not two independent confirmations. In exchange, average throughput increases
28.60% (0.24906 → 0.32029 responses/cycle), while mean latency decreases 23.14%
(63.00 → 48.42 cycles). p95 increases 5.45 cycles and the average per-run maximum
increases 6.00 cycles. The result is a repeatable throughput/mean-versus-tail tradeoff.

Strict Request FCFS does not share that tail regression: its mean paired p99 change
is −0.70 cycles, and throughput remains approximately 0.1463 responses/cycle.
Its small changes should not be confused with the much larger FR-FCFS effect.

Across the final random-traffic runs, FR-FCFS with and without aging averages
0.4187 / 0.3203 / 0.1958 responses/cycle at ready 100% / 50% / 20%, respectively.
Corresponding average per-run p99 values are 69.35 / 90.00 / 98.05 cycles.
Throughput spans 0.4150–0.4234, 0.3174–0.3228, and 0.1952–0.1971 across seeds;
the qualitative policy comparison is stable. Strict Request FCFS stays near
0.146 responses/cycle and remains limited by command scheduling in these streams.

At 100% ready, hot/cold traffic exposes the aging tradeoff: FR-FCFS p99/max are
333/403 cycles; aging reduces both to 137 cycles while throughput decreases from
0.4815 to 0.4617 responses/cycle. HOL throughput is 0.4952 for either FR-FCFS policy
versus 0.3054 for Strict Request FCFS, although the reordering policies have higher
p99 (102 versus 51 cycles). At 50% ready, FR-FCFS hot/cold and HOL throughput is
0.3503 and 0.3772; at 20% ready, those workloads converge near the host limit of
0.200 responses/cycle across policies. Aging does not change their measured
50%/20% metrics in this study. These are comparisons among the frozen final-design
policies; historical paired measurements here cover only random/50%.

**Hot/cold and HOL are deterministic timing experiments.** Their seeds change
write data, but not addresses or read/write operations. All five metrics have
zero cross-seed variation in every such condition. Twenty passing payload seeds
do not establish robustness across twenty different locality or arrival patterns.

Random traffic does vary addresses. Paired seed comparisons isolate the response
implementation under the same offered transaction sequence. Different response
timing changes slot availability and the requests visible to the scheduler;
higher throughput and lower mean latency do not imply a lower p99.

These runs characterize saturated small-memory simulation with periodic stalls,
not arbitrary traffic or Bernoulli readiness. Each p99 has only about 20 samples
above it; longer runs could further characterize tails. Forced-ready final drain
is retained for exact comparability and means throughput is a finite-cohort metric.
The study supports conclusions within this configuration, not a universal latency guarantee.

No RTL, testbench, architecture, scheduler, constraints, or synthesis settings were
changed. This task ran performance self-checks, not a new regression, formal,
or synthesis campaign; earlier correctness evidence remains associated with the same RTL.

## Reproduce and inspect

```sh
python3 scripts/perf_stability.py
python3 scripts/perf_stability_report.py
```

- [All 600 per-seed records](../results/perf_stability/per_seed.csv)
- [All cross-seed distributions](../results/perf_stability/distributions.csv)
- [Summary, paired deltas, configuration and build hashes](../results/perf_stability/summary.json)
- [Frozen source hashes](../results/perf_stability/frozen_sources.json)
- [Verification accounting](../results/perf_stability/verification.json)

Raw simulation commands, logs and timestamp traces stay under ignored
`build/runs/stability_*`; build commands are in `build/perf_stability/commands.json`.
The private notebook is append-only and excluded from Git and export artifacts.
