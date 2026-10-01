# Q16 / 3 ns critical-path analysis

This analysis uses the shared-address implementation at commit `12db399`,
FR-FCFS with aging, and the recorded GSCL45nm typical corner at 1.1 V / 27°C.
It separates delay by mapped hierarchy boundaries to choose the next RTL
experiment. No RTL, clock constraint, pipeline, or synthesis optimization is
changed by this analysis.

The subsequent [candidate-mask experiment](candidate-mask-optimization.md) tests
the interface change proposed here. Its measurements are separate; the path
delays below remain those of the original shared-address checkpoint.

## Budget and worst path

The worst recorded path is `table_i/addresses_reg[7]` → `cmd_wdata[21]`.
The launch register contains an **address**, so this is a command-selection
control path through the write-data mux, not a launch from stored write data.
At the default address geometry, address bit 7 is slot 0's column bit 5.

```text
Clock period                           3.000000 ns
  minus clock uncertainty              0.100000 ns
  minus output external delay          1.000000 ns
Required arrival                       1.900000 ns
Measured arrival                       2.101311 ns
Setup slack                           -0.201311 ns
```

The target requires removing at least 0.201311 ns from this path at unchanged
constraints, about 9.58% of its current arrival time. The previous candidate-
decode revision had −0.166662 ns worst slack at 3 ns. Its worst endpoint and
mapped path differ, so the 0.034649 ns regression cannot be assigned to one RTL
operation by subtracting individual gate delays across the two netlists.

## Delay decomposition

<!-- stage-table -->

| Stage | Delay (ns) | Arrival (ns) | Share of arrival | Cells on path |
|---|---:|---:|---:|---:|
| Launch clock-to-Q | 0.113487 | 0.113487 | 5.40% | 1 |
| Shared address comparison / buffering | 0.234201 | 0.347688 | 11.15% | 7 |
| Dependency filtering + bank candidate selection / encoding | 0.727266 | 1.074954 | 34.61% | 28 |
| FR-FCFS / aging arbitration + slot encoding | 0.696368 | 1.771322 | 33.14% | 28 |
| Slot decode + command output selection / buffering | 0.329989 | 2.101311 | 15.70% | 12 |

<!-- /stage-table -->

The table describes the **single worst path**, not an average over endpoints.
Stage delays are differences between cumulative arrivals at consecutive
hierarchy boundaries. Summed printed cell increments can differ by a few units
in the sixth decimal place due to rounding. Cell counts include buffers and
inverters; they are not counts of RTL operators. Synthesis merges logic, so the
candidate stage is not further presented as exact per-statement delay.

The path traverses `candidates_i/same_address[208]` (slot pair 13,0), leaves the
candidate block on `candidate_slots[0]` (bank 0's encoded slot bit 0), and leaves
the scheduler on `select_slot[1]`. This directly exposes a candidate-slot encode /
decode boundary followed by global selection and a final output decode/mux.

The candidate and scheduler stages contribute **1.423634 ns (67.75%)** together.
There are 75 combinational cell arcs plus one launch clock-to-Q arc. The output
selection stage contributes 0.329989 ns (15.70%). Improving only that stage would
need to remove about **61% of its delay** to fix this particular path, before
considering other failing endpoints. That is a budget calculation, not a forecast
that a mux rewrite can achieve it.

## Fanout, capacitance and cell delays

On the reported worst path:

- The maximum explicitly reported net fanout is **13**, at top-level `n7748`
  (driven by `U5289/Y`, INVX8) and `candidates_i/n2698`
  (driven by `candidates_i/U2068/Y`, INVX4).
- `n7748` has 66.863 fF reported load; `candidates_i/n2698` has 25.493 fF.
  The scheduler's `select_slot[1]` net itself has fanout 4 and 6.686 fF;
  downstream buffered selection nets reach fanout 8 and 9. Looking only at the
  unbuffered slot output would understate downstream distribution.
- The largest combinational cell arc is the final `U773` MUX2X1, 0.073690 ns,
  driving the constrained 10 fF output load. Its reported output transition is
  0.077554 ns. Launch clock-to-Q is a separate 0.113487 ns.
- Every net-delay increment printed on this path is zero. The design has no
  extracted interconnect or wire-load model. Cell delays still depend on
  transition and pin/load capacitance. Zero reported net delay does **not** imply
  zero physical wire delay or resolved routing/fanout concerns.

Capacitance is converted from the report's pF units to fF. Hierarchical alias
rows repeat net loads and are not summed. The timing header's high-fanout
computation setting of 1000 is not the fanout measured on this path. Inherited
zero-limit library max-capacitance violations and hold violations remain.

## Other endpoints and supplementary STA

<!-- endpoint-analysis -->

The same mapped DDC was reopened in DC R-2020.09-SP4, linked to the same
hash-checked library, and queried using its saved constraints. Cell area exactly
reproduces **72,879.472659 µm²**, and worst setup slack reproduces **−0.201311 ns**.
All 51 setup endpoints and their slacks match the earlier constraints within
printed precision; the actual `check_timing` checks match as well. This is a new
read-only STA query of the existing mapping, not a new compile.

The expanded overall report contains 100 distinct endpoints: 51 failing
register-to-output paths and 49 passing register-to-register paths. Every failing
path crosses both `candidates_i` and the FR-FCFS scheduler. Of those paths, 32
launch from address register bit 7 and 19 from address register bit 32. Saved-DDC
names use `addresses_reg_7_` / `frfcfs_scheduler_i` because the synthesis flow
writes the DDC after `change_names`; the original reports use bracketed register
names and `frfcfs.scheduler_i`.

| Path class | Worst setup slack (ns) | Reported worst path |
|---|---:|---|
| Register → output | −0.201311 | Address register bit 7 → `cmd_wdata[21]` |
| Register → register | +0.001500 | `table_i/occupied_reg_0_` → `table_i/writes_reg_4_` |
| Input → register | +0.475024 | `rst` → `table_i/ages_reg_112_` |
| Input → output | +0.604270 | `rst` → `req_ready` |

Focused queries retain ten register-to-register paths, ten input-to-register
paths and all three reported input-to-output paths. Their worst slacks are
positive, but the internal register path has almost no margin; keep it in the
next experiment's acceptance checks. These constrained static paths do not imply
simultaneous functional sensitization or physical timing closure.

A private register-to-output query also returned 100 alternatives, but only 12
unique endpoints. An explicit `-from` collection can return alternatives from
different starts even with `-nworst 1`. Coverage here is checked against the
100-unique-endpoint **overall** report and the full constraint list, rather than
inferred from command flags or the number of printed paths.

<!-- /endpoint-analysis -->

Nine of the original top-ten paths launch at address register bit 7 and share
69 cell arcs through top-level `U5302/Y` before diverging. The seventh path starts
at bit 32, slot 2's bank bit 0, and enters `candidates_i/addresses[32]` without
traversing a shared address-equality comparator. Its slack is −0.201065 ns, only
0.000246 ns better than the worst path. Its candidate and scheduler stages take
0.963276 and 0.670704 ns respectively. Optimizing only the shared comparator
would leave this almost equally slow alternative.

The constraint report has 51 violating endpoints: 32 write-data, 8 row, 6 column,
2 bank, 2 operation, and 1 command-valid output. `cmd_valid` alone has −0.058517 ns
slack in the constraint report; its path is not the write-data output mux.
A write-data-only change therefore leaves other command output violations to
address. The ten worst paths are correlated branches and alternatives of the
command-selection structure, not ten independent microarchitectural bottlenecks.

## Next experiment, ranked by the measured path

1. **Remove avoidable encoding/decoding between bank candidates and the global
   scheduler.** Preserve the existing bank winner policy, but investigate passing
   winner masks to the scheduler instead of encoding slots and decoding them
   again. The path crosses that interface at 1.074954 ns; the candidate and
   scheduler stages together dominate the path. This hypothesis is narrower than
   the earlier rejected bank-ranking rewrite, which changed the ranking logic.
2. **Evaluate final winner encoding and command selection together.** If a final
   one-hot winner can directly select command address, operation and write data,
   it may shorten both encoding and output selection. Merely decoding the current
   binary `select_slot` into another one-hot vector would retain the existing
   upstream delay. Account for the command-valid path, aging override, owner
   drain, reset/default outputs, and existing winner tie behavior.
3. **Use fanout buffering/logic duplication only as a measured tradeoff.** The
   reported fanout/load hot spots are useful places to inspect, but the measured
   path has many serial logic arcs. The current reports do not establish fanout
   as the sole cause or predict post-route timing.

Keep the initial experiment cycle-equivalent and change one interface/selection
stage at a time. Reuse the current source-matched Q16/3 ns and Q16/4 ns baselines;
run equivalence, the directed/unit checks, regression and complete trace pairs
before accepting matched DC results. Report both setup and area: measure progress
against −0.201311 ns at 3 ns while retaining the 4 ns setup result and as much of
its 67,387.25 µm² area benefit as practical. Any acceptance threshold for area
should be set before comparing variants. A pipeline would change the controller's
cycle behavior and requires a separate architecture experiment.

No timing-improvement result is claimed here; this report chooses what to test.

## Reproduction and artifacts

```sh
python3 scripts/critical_path_report.py
```

The collector checks the source RTL, SDC and timing-report hashes; validates
arrival/slack arithmetic and printed increment totals; validates the reopened
DDC reports; and accounts for every retained setup violation. Run it with the
source RTL matching commit `12db399`. The original synthesis evidence remains unchanged.

For supplementary queries, `synth/dc/analyze_paths.tcl` reads an existing mapped
DDC and its saved constraints using an authorized site library configuration.
Set `MC_LAB_CONFIG`, `MC_MAPPED_DDC`, `MC_ANALYSIS_TOP` and `MC_ANALYSIS_OUT`, then
run `dc_shell -f synth/dc/analyze_paths.tcl`. The script performs no `compile`,
retiming, constraint relaxation or DDC rewrite.

- [Machine-readable analysis](../results/critical_path_3ns/summary.json)
- [Worst-path stages](../results/critical_path_3ns/worst_stages.csv)
- [All worst-path cell arcs](../results/critical_path_3ns/worst_arcs.csv)
- [Worst-path nets, fanout and load](../results/critical_path_3ns/worst_nets.csv)
- [Original ten path endpoints](../results/critical_path_3ns/top_paths.csv)
- [Violating output groups](../results/critical_path_3ns/violating_endpoints.csv)
- [Expanded paths](../results/critical_path_3ns/expanded_paths.csv)
- [Path-class comparison](../results/critical_path_3ns/path_classes.csv)
- [Supplementary STA reports and provenance](../results/critical_path_3ns/reports/)
- [Original full timing report](../results/address_sharing/reports/q16_3ns/timing.rpt)
