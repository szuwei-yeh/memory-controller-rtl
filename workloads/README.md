# Reproducible workloads

The generator lives in tb/tb_top.sv; scripts/run.py names and configures each case.
The sequence-indexed xorshift32 RNG is fixed by `+seed`; response stalls do not
change request addresses/data. All policies receive identical sequences.

| ID | Name | Pattern |
|---|---|---|
| 0 | row_hit | Bank 0, one row, cycling columns |
| 1 | sequential | Consecutive word addresses, low bank-bit interleaving |
| 2 | row_conflict | Two alternating bank-0 rows |
| 3 | random | Uniform address bits |
| 4 | hot_cold | Fifteen hot-row requests per cold conflicting request |
| 5 | hol | Periodic bank-0 conflicts mixed with other-bank hits |
| 6 | read_only | Random, 100% reads |
| 7 | read_write_50 | Random, alternating reads and writes |
| 8 | write_only | Random, 100% writes |
| 9 | same_address | One address, mixed RAW/WAR/WAW/RAR chains |

Default mix is 75% reads/25% writes. `make perf` uses seed 42, 200 warm-up requests,
2,000 measured requests, and excludes the ten directed prelude requests from metrics.
It adds random-workload offered intervals of 4/8/16 cycles and response-ready duty
cycles of 80/50/20%. Input can offer up to one request per cycle.

CSV events: A acceptance; C command; D internal completion; P protection activation;
E protection completion/duration; I classified idle cycle; O occupancy, preparing-bank
count and per-bank open/owner masks; R consumed response with sequence/address/operation and
offered/accepted/issued/completed/eligible/presented timestamps plus locality class.
Per-run metrics.json records distributions; run.json preserves the exact command.
Measurement throughput uses the first measured acceptance through the last measured
response, including drain. ACT/PRE per request use attributable request sequence IDs.
Row-hit classification is at the request's first attributable command, never at
its inevitably open-row column command.
