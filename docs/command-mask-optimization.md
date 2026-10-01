# Direct command-selection mask experiment

This is the measured checkpoint at `9d40e16`. The current RTL subsequently
adopts [parallel command-class arbitration](parallel-arbitration-experiment.md).
Reproduce this historical experiment's collector at its checkpoint; its source
guards deliberately do not accept a later scheduler as the measured snapshot.

The selected **direct mask plus fixed-slot storage** reduces the magnitude of
the Q16/3 ns worst setup violation by **40.95%**, from −0.116465 to −0.068773 ns,
while reducing mapped area by **1.89%**. All 34 internal setup failures disappear.
Q16/4 ns retains a setup pass with **2.56% less area**, and hold improves at both
targets. **3 ns setup and hold still fail; this is not timing closure.**

The subsequent [remaining command-path analysis](command-path-3ns.md) queries
this selected implementation's saved DDC, reproduces all violations, and breaks
down the remaining 68.773 ps without another compile or RTL change.

This experiment targets the scheduler-to-command-output path after the
[candidate-mask revision](candidate-mask-optimization.md) and
[storage timing study](storage-timing-experiment.md). The storage alternatives
remain excluded from the starting RTL: each trial starts from the exact
compact-mask baseline. The two direct-mask trials change only
`mc_scheduler_frfcfs` and `mc_top`; a third trial combines the direct mask with
the previously measured fixed-slot transaction-table writes.

## Direct payload selection

The previous scheduler encodes its winning slot. The top then uses that index
to select the command's operation, bank, row, column, and write data. The new
interface also exports a slot mask computed directly from scheduler winners.
The top uses masked OR reductions over constant slot slices. The encoded slot
remains available for transaction-table and bank-owner state updates.

```text
Before: arbitration → encoded slot → indexed command payload mux
Trial:  arbitration → winner mask  → masked-OR command payload
                   → encoded slot → existing state updates
```

This is a combinational representation change. It adds no pipeline, storage,
command cycle, timing exception, or scheduling-policy change. Existing
candidate eligibility, column-first preference, oldest selection, and aging
owner-drain priority are retained. If several incomparable winners exist, the
highest slot index still wins, matching the original last-assignment priority.

Command payloads are defined even when `cmd_valid` is low. FR-FCFS normally
defaults to slot zero when no winner exists, so the payload mask must select
slot zero in that case. It must not simply be gated by `select_valid` or reset.
The aging service override replaces the mask and encoded slot together. The
Strict-FCFS branch decodes its existing slot index: a timing-blocked oldest
request can still supply payload while its valid bit is low.

Three logically equivalent implementations are measured:

- **`direct_mask`:** form the highest-winner mask, then explicitly set bit zero
  if the winner vector is empty.
- **`folded_default`:** fold the idle fallback into bit zero. For bit zero,
  `(winner[0] AND no_higher) OR no_winners` simplifies to `no_higher`.
  For every other bit, require that bit's winner and no higher winner.
  Validity is still calculated separately: a nonzero payload mask is not a
  valid-command indication.
- **`mask_and_storage`:** combine `direct_mask` with the fixed-slot writes from
  the storage study. The standalone direct mask improved 3 ns worst setup but
  failed TNS and hold-count criteria. The combination tests whether the storage
  change can address those regressions; the prior improvements are not assumed
  to add together. This third trial uses the same adoption screen.

## Adoption screen and measurements

The screen was recorded before measurement: whole-controller equivalence;
strictly better Q16/3 ns worst setup slack; no worse 3 ns internal setup count
or setup TNS; passing 4 ns setup; no worse hold slack or hold count at either
target; and at most 5% extra 4 ns area. If several alternatives qualify, choose the
one with better 3 ns worst setup slack, then validate the selected source fully.

All points use FR-FCFS+aging, Q=16, DC R-2020.09-SP4, GSCL45nm typical at
1.1 V/27°C, identical library/configuration/SDC/DRAM timing parameters, and
`compile -map_effort medium`. Six fresh isolated mappings are compared with
the two **reused** compact-mask baseline points. A target-specific compile
produces each netlist; these are not two clock periods applied to one netlist.

<!-- measured-table -->

| Variant | Target (ns) | Area (µm²) | Setup slack (ns) | Setup TNS (ns) | Setup endpoints | Internal setup endpoints | Hold slack (ns) | Hold endpoints |
|---|---:|---:|---:|---:|---:|---:|---:|---:|
| compact_baseline | 3 | 73,105.21 | -0.116465 | -5.655077 | 84 | 34 | -0.002538 | 17 |
| compact_baseline | 4 | 67,729.84 | +0.000518 | 0.000000 | 0 | 0 | -0.050676 | 39 |
| direct_mask | 3 | 71,259.45 | -0.098674 | -5.782456 | 66 | 16 | -0.002538 | 23 |
| direct_mask | 4 | 65,884.56 | +0.001552 | 0.000000 | 0 | 0 | -0.002538 | 10 |
| folded_default | 3 | 71,404.93 | -0.086960 | -5.395905 | 76 | 25 | -0.003357 | 24 |
| folded_default | 4 | 65,471.57 | +0.000048 | 0.000000 | 0 | 0 | -0.002538 | 9 |
| mask_and_storage | 3 | 71,720.77 | -0.068773 | -3.396384 | 50 | 0 | -0.000661 | 8 |
| mask_and_storage | 4 | 65,996.72 | +0.000109 | 0.000000 | 0 | 0 | -0.000659 | 2 |

<!-- /measured-table -->

<!-- decision -->

Only `mask_and_storage` passes every predeclared criterion and is selected.
At 3 ns, setup TNS improves from −5.655077 to −3.396384 ns. Setup failures decrease
from 84 to 50, all now command outputs; internal failures decrease from 34 to
zero. Worst hold improves from −0.002538 to −0.000661 ns and failing hold endpoints
decrease from 17 to eight. At 4 ns, setup slack is +0.000109 ns; worst hold improves
from −0.050676 to −0.000659 ns and failing hold endpoints decrease from 39 to two.
All six new mappings retain 1,974 sequential cells.

The alternatives are retained as evidence of the tradeoff:

- `direct_mask` improves worst setup and area, but 3 ns TNS worsens to −5.782456 ns
  and hold endpoints increase to 23. Its 16 internal setup failures are age bits.
- `folded_default` improves 3 ns worst setup to −0.086960 ns and TNS to −5.395905 ns,
  but worst hold regresses to −0.003357 ns on `rst → cmd_valid`, with 24 hold
  failures. Its 25 internal setup failures comprise 16 age, six write-data, and
  three tag bits. Its +0.000048 ns 4 ns setup margin is also very small.

The standalone fixed-slot storage change failed the preceding experiment's
overall setup criterion. Its combination with a direct command mask succeeds
under this round's screen; this is a fresh combined measurement, not a sum of
separately measured improvements. The selected 3 ns setup violation is still
0.068773 ns and the 4 ns positive margin is tiny. No higher supported frequency
or robust corner margin is inferred.

<!-- /decision -->

## Where the delay moves

The standalone direct mask shortens the final payload-selection stage but
increases the load on the scheduler's selection output. The representative
worst paths from the two independently mapped 3 ns designs show:

| Observation | Compact baseline | Direct mask |
|---|---:|---:|
| Launch address register bit | 77 | 93 |
| Endpoint | `cmd_wdata[17]` | `cmd_row[3]` |
| Scheduler boundary signal | `select_slot[2]` | `select_mask[3]` |
| Boundary arrival (ns) | 1.728987 | 1.824616 |
| Reported boundary-net fanout | 6 | 48 |
| Reported boundary-net capacitance (fF) | 10.958 | 135.611 |
| Command-output arrival (ns) | 2.016465 | 1.998675 |
| Delay after scheduler boundary (ns) | 0.287478 | 0.174059 |

The final stage is 0.113419 ns shorter, while the selection boundary arrives
0.095629 ns later. Their difference is about 0.017790 ns of net improvement.
These are different worst paths and endpoints, not an arc-for-arc causal
comparison or a physical interconnect estimate. They demonstrate that removing
the index decode shifts load into the selection logic; a local depth reduction
does not guarantee the same end-to-end gain.

## Verification scope

Each isolated alternative passes Verilator lint and five whole-controller equivalence
configurations: Q1/aging, Q3/all three policies, and Q16/aging. The other five
RTL modules are identical to the compact-mask baseline for the first two trials;
the combined trial also changes the transaction table. Flattening checks the
actual mask wiring; memory mapping and identical-cell merging precede
`equiv_simple -undef -short`. Every matched-node equivalence cell must be proved.
Corresponding state shares synchronous reset. This is implementation equivalence,
not an independent unbounded proof of arbitrary functionality, initial state,
or every parameter configuration.

A negative control removes the idle slot-zero fallback in an isolated Q3
FR-FCFS copy of `direct_mask`. The same checker rejects it with **50 unproved
cells**, including command-payload outputs. Thus the comparison also checks
invalid-cycle payload behavior rather than considering only valid commands.
The mutation is never used for synthesis or retained in production RTL.
The same negative control is also run against the selected combined controller.
It is rejected with the same 50 unproved cells.

<!-- selected-validation -->

Selected-source validation uses:

```sh
make lint test
make regress SEEDS=100 N=10000 JOBS=4
make formal
make formal-command-mask
make compare-command-mask
```

All checks pass on the exact selected source: lint; 42 directed/workload/reset/
parameter-corner simulations plus model legality/negative and scheduler/response
unit checks; 300 regression runs with 3,003,000 accepted transactions; nine
whole-controller equivalence configurations; and 120 identical trace pairs
(240 simulations, 122,400 accepted transactions). The existing formal suite
passes three depth-12 controller BMC tasks and two reduced unbounded bank/progress
control proofs. BMC passes are bounded evidence, and the reduced proofs do not
prove every full-width data-path configuration.

`formal-command-mask` freezes and hash-checks the compact baseline's top,
FR-FCFS scheduler, and transaction table; the other four modules must match the
baseline hashes. It checks Q=1/3/16 across all three policies (nine configurations;
CI uses Q=1/3). `compare-command-mask` compares 120 complete event-trace pairs
at Q=16 across three policies, ten workloads, seeds 1/42, and ready 100%/30%.
Their summaries must match the selected mapped RTL hashes before publication.
The original candidate-mask checker and report now describe a frozen preceding
snapshot, reconstructed as explained below; they do not target the current RTL.

<!-- /selected-validation -->

## Reproduction and evidence

The seven-file compact baseline can be reconstructed from commit `12db399`
plus the three files in `results/candidate_mask/variants/compact_mask/rtl/`.
Verify the resulting seven hashes against this experiment's summary. Each
trial then replaces only the files published under its variant directory.
Use isolated controller-only bundles with the authorized library and matching
site configuration, and run both points in each bundle:

```sh
python3 scripts/synth.py dc --lab --policy frfcfs_aging --point 16 3
python3 scripts/synth.py dc --lab --policy frfcfs_aging --point 16 4
```

For an isolated equivalence reproduction, use `proof_script()` from
`scripts/candidate_mask_equiv.py` with the compact baseline and trial directories,
the seven-file synthesis manifest, and the Q/policy combinations above. The
[storage study](storage-timing-experiment.md#validation-and-reproduction) gives
the invocation pattern for this shared generator.

`python3 scripts/command_mask_report.py` collects retained manifests and runs in
`build/command_mask_opt/`, `build/command_mask_folded/`, and
`build/command_mask_storage/`. It checks source,
flow, configuration, library identity, and the adoption criteria before
publishing results. A fresh checkout lacks private run directories and the
licensed technology library. Public report copies redact the private library
path and retain both raw and public hashes.

- [Metrics CSV](../results/command_mask/summary.csv)
- [Source hashes, adoption checks, proof scope, and full metrics](../results/command_mask/summary.json)
- [All measured RTL variants](../results/command_mask/variants/)
- [Mapped reports](../results/command_mask/reports/)

These are typical-corner pre-layout measurements with ideal clocks and no
extracted interconnect. Remaining hold and inherited zero-limit max-capacitance
violations are not waived. This study does not establish power, exact Fmax,
Q32 mapped PPA, physical timing, or signoff.
