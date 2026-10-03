# Candidate-mask timing experiment

This report records the compact-mask checkpoint. Current RTL continues with
the [command-mask plus storage experiment](command-mask-optimization.md); the
measurements and reproduction commands below apply to the frozen compact snapshot.

The selected Q-bit candidate mask reduces the magnitude of the **Q16/3 ns worst
setup violation by 42.15%**, from −0.201311 to −0.116465 ns, with **0.31% more
mapped area**. Q16/4 ns retains a setup pass at +0.000518 ns with 0.51% more area.
This is a setup-oriented research variant: **3 ns still fails, new internal setup
violations appear, and 4 ns hold gets worse**. No timing-closure or new frequency
claim follows from this experiment.

The baseline is the shared-address controller at commit
`12db3996def42219deb0d0d589ec2ac0c472f0cf`. Its
[3 ns path analysis](critical-path-3ns.md) attributed 67.75% of the worst path's
arrival time to candidates and scheduling. This experiment changes that interface
without adding a pipeline, storage, or command latency.

## Removing candidate encoding and decoding

Previously each bank selected a valid bit and encoded slot index. The scheduler
decoded those indices back into per-slot choices before legality, aging, and
column-preference arbitration. The candidate block now directly exports a mask.
Bank ownership, dependency filtering, and open-row-hit preference still precede
selection; timing legality is still applied after the per-bank candidate choice.
Moving legality earlier would change the scheduling policy.

For each bank, the existing eligible/hit-qualified `choices` produce:

```text
winner[i] = choices[i] AND NOT OR_j(choices[j] AND older[j,i])
bank_mask[i] = winner[i] AND NOT OR_k>i(winner[k])
candidate_mask[i] = OR_bank(bank_mask[i])
```

The suffix exclusion preserves the original loop's highest-slot-index fallback
even when an ordering matrix has multiple incomparable winners. It does not
assume a unique winner or a transitive order matrix. Since each slot has one bank
address, the selected mask needs Q bits. During aging, the scheduler checks the
slot's address-bank bits to allow only other-bank ACT/PRE choices; owner drain,
protected-request priority, and the protection state update are unchanged.
Strict-FCFS and the response path retain their implementation and behavior.

Two alternatives were measured: `bank_mask` exports four separate Q-bit masks;
`compact_mask` ORs them into one Q-bit mask and is the current RTL. Both preserve
cycle behavior. Three RTL files change: `mc_candidates`, `mc_scheduler_frfcfs`,
and their wiring in `mc_top`. All four mapped runs retain 1,974 sequential cells.

## Matched measurements and selection

All points use FR-FCFS with aging, Q=16, DC R-2020.09-SP4, GSCL45nm typical at
1.1 V/27°C, identical SDC/DRAM timing parameters, and
`compile -map_effort medium`. Source, flow, site configuration, and library hashes
are checked. Four new isolated DC runs measure the two alternatives at 3/4 ns.
The two baseline runs are **reused** from the
[shared-address experiment](address-sharing-optimization.md), not fresh reruns.

<!-- measured-table -->

| Variant | Target (ns) | Area (µm²) | Setup slack (ns) | Setup TNS (ns) | Setup endpoints | Hold slack (ns) | Hold endpoints |
|---|---:|---:|---:|---:|---:|---:|---:|
| baseline | 3 | 72,879.47 | -0.201311 | -9.964599 | 51 | -0.006960 | 24 |
| baseline | 4 | 67,387.25 | +0.000694 | 0.000000 | 0 | -0.002538 | 9 |
| bank_mask | 3 | 73,648.66 | -0.059765 | -5.505099 | 276 | -0.014064 | 256 |
| bank_mask | 4 | 67,664.14 | +0.001885 | 0.000000 | 0 | -0.050676 | 26 |
| compact_mask | 3 | 73,105.21 | -0.116465 | -5.655077 | 84 | -0.002538 | 17 |
| compact_mask | 4 | 67,729.84 | +0.000518 | 0.000000 | 0 | -0.050676 | 39 |

<!-- /measured-table -->

Before measurement, the screen required improved 3 ns worst setup slack, a 4 ns
setup pass, and at most 5% additional 4 ns area. Both alternatives pass that
screen. Full STA review then exposes tradeoffs that this initial screen misses:

- `bank_mask` has the best 3 ns worst setup slack (−0.059765 ns), but 276 setup
  and 256 hold endpoints fail. Its setup failures include 216 read-data bits,
  nine write-data bits, one write-control bit, and 50 command outputs.
- `compact_mask` has weaker 3 ns worst setup slack, but lower 3 ns area and only
  84 setup / 17 hold endpoints fail. Its 84 setup failures comprise 50 command
  outputs, 32 read-data bits, and two completion bits. The baseline's 51 setup
  failures were all command outputs, so this is still an internal timing regression.
- At 3 ns, compact-mask hold improves from −0.006960 to −0.002538 ns, with failing
  endpoints decreasing from 24 to 17. At 4 ns, hold worsens from −0.002538 to
  −0.050676 ns. Both alternatives have that same worst 4 ns hold slack; compact
  has 39 failing endpoints versus bank-mask's 26. The worst path launches at
  `rst` and ends at bank write-timer registers.

The compact mask is retained for further work because it trades some 3 ns setup
gain for fewer 3 ns internal setup/hold failures and lower 3 ns area. Neither
alternative dominates all metrics. No violations are waived. The next closure
work must track internal setup paths and reset/input hold alongside command-output
setup; optimizing only worst setup slack would hide these regressions.
The [follow-up storage experiment](storage-timing-experiment.md) investigates
these paths and evaluates fixed-slot writes and independent free-slot availability.

These are separate target-specific mappings, not the same netlist tested at two
clock periods. The inherited zero allowed-load/max-capacitance violations remain.
Results are typical-corner, ideal-clock, pre-layout measurements; they do not
establish exact Fmax, post-route timing, power, or signoff. Q32 mapped PPA was not
measured for this change, and preceding Q32/5 ns results belong to the old RTL.

## Correctness evidence

- `make lint test`: lint and 42 directed/workload/reset/parameter-corner runs,
  plus model legality/negative tests and scheduler/response unit checks.
- `make regress SEEDS=100 N=10000 JOBS=4`: 300 runs and 3,003,000 accepted
  transactions across all three policies, including the directed preludes.
- `make formal`: three depth-12 controller BMC checks and two reduced unbounded
  bank/progress control proofs. BMC passes are bounded evidence.
- `make formal-candidate-mask`: nine whole-controller matched-node SAT equivalence
  checks at Q=1/3/16 across Strict-FCFS, FR-FCFS, and FR-FCFS+aging. The three
  original modules are frozen and hash-checked; the other four are identical
  on both sides. Flattening includes actual mask wiring and bank identities.
  `memory_map` exposes state and `opt_merge` merges identical cells before
  `equiv_simple -undef -short`. Every equivalence cell must be proved. Corresponding
  state shares the same synchronous reset. This is implementation equivalence,
  not an independent unbounded proof of arbitrary controller functionality,
  unconstrained initial state, or every parameter configuration. CI runs Q=1/3.
- `make compare-candidate-mask`: 120 complete byte-identical old/new event-trace
  pairs at Q=16: three policies, ten workloads, seeds 1/42, ready 100%/30%.
  The 240 simulations accept 122,400 transactions in total. No cycle-throughput
  improvement is claimed; the experiment targets mapped timing.
- Negative control: forcing slot zero's candidate-mask bit low in an isolated
  Q3 FR-FCFS copy makes the same equivalence checker fail with four unproved
  cells. This mutation is absent from production RTL and mapped measurements.

Both experimental snapshots also passed an initial five-case integration screen
(Q1 aging, Q3 all policies, Q16 aging). The retained compact RTL's full validation
above is checked against the exact seven RTL hashes used for its DC runs.

## Reproduction and evidence

For this historical experiment, reconstruct the compact RTL from `12db399` plus
the three files in `results/candidate_mask/variants/compact_mask/rtl/`. With that
snapshot restored in a separate checkout, the historical commands below accept
the encoded final-selection interface again. The current interface instead uses
`make formal-command-mask` and `make compare-command-mask`.

```sh
make lint test
make regress SEEDS=100 N=10000 JOBS=4
make formal
make formal-candidate-mask
make compare-candidate-mask
```

Use isolated controller-only lab bundles with the same authorized library and
site configuration. The seven current RTL hashes and original baseline hashes
are in the summary. `baseline_sources()` in `scripts/candidate_mask_equiv.py`
returns the three original files; replace those in a baseline bundle while
keeping the other four identical. Alternatively use either published variant's
three changed files with the four unchanged files from commit `12db399`.
For each bundle run:

```sh
python3 scripts/synth.py dc --lab --policy frfcfs_aging --point 16 3
python3 scripts/synth.py dc --lab --policy frfcfs_aging --point 16 4
```

`python3 scripts/candidate_mask_report.py` collects retained private run metadata
from `build/candidate_mask_opt/`, `build/candidate_mask_compact/`, and the current
verification outputs. It checks matching source/flow/configuration hashes before
publishing results. It requires those experiment manifests; a fresh checkout
alone does not contain private run directories or the licensed technology library.
Public reports redact the private library path and preserve raw/public hashes.

- [Metrics CSV](../../results/candidate_mask/summary.csv)
- [Sources, validation scope, violations, and complete metrics](../../results/candidate_mask/summary.json)
- [Mapped reports](../../results/candidate_mask/reports/)
- [Both measured RTL variants](../../results/candidate_mask/variants/)

Earlier encoded-interface equivalence commands are historical: use checkpoint
`27f522c` for the candidate-decode study and `12db399` for address sharing. Their
frozen results remain intact. The current checker continues the evidence chain
from v1.1 through those checkpoints to the mask interface.
