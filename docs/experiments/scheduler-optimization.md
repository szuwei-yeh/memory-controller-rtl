# Candidate-decode optimization

The FR-FCFS scheduler now constructs its candidate mask with fixed slot accesses.
It preserves scheduling policy, aging, ordering, interface timing, and all state
registers. This is a combinational implementation change, with separate evidence
from the [frozen v1.1 ASIC sweep](../asic-results.md).

## Change and hypothesis

Previously the scheduler read `legal[idx]` and `next_ops[idx*2+:2]` for each bank
candidate and updated `choices[idx]`. It now iterates over transaction slots,
compares each slot number with the four bank-candidate indices, and uses fixed
accesses to that slot's legality and operation. Bank-specific aging suppression,
ready-column preference, oldest selection, and protection state are unchanged.

For each slot `i`, both versions implement `legal[i] AND any bank b whose
candidate is valid, whose candidate slot equals i, and whose command is allowed
by protection`. Changing the direction of that decode preserves the same mask,
including duplicate candidates; no new oldest-order assumption is needed.

The hypothesis was that explicit decoding would reduce dynamic selection and
mask-update circuitry. The queue-wide older-than matrix and pairwise oldest
selection remain; this change does not remove their quadratic scaling.

An initial four-candidate arbitration experiment increased scheduler-only Yosys
generic cells from 2,077 to 2,941 because compact RTL introduced dynamic selection
logic. The adopted decode-only version uses 1,861 cells in the same local Q=16
experiment (10.4% fewer). Generic counts are a screening result; the full-controller
mapped comparison below determines the ASIC conclusion. Rejected experiments and
raw local logs are retained privately.

## Matched mapped synthesis

All points use FR-FCFS with aging, DC R-2020.09-SP4, GSCL45nm typical at 1.1 V/27°C,
and `compile -map_effort medium`. Both variants use identical libraries, SDC,
geometry, and DRAM cycle timings. Only `rtl/mc_scheduler_frfcfs.sv` changes.
Each point is a fresh compile in an isolated workspace.

<!-- paired-table -->

| Q | Clock target (ns) | Area before (µm²) | Area after (µm²) | Area change | Worst setup slack before → after (ns) |
|---:|---:|---:|---:|---:|---:|
| 16 | 5 | 80,975.37 | 79,548.69 | -1.76% | +0.001615 → +0.012058 |
| 16 | 4 | 83,993.90 | 80,695.19 | -3.93% | +0.000617 → +0.000458 |
| 16 | 3 | 90,281.59 | 87,867.98 | -2.67% | -0.375142 → -0.166662 |
| 32 | 5 | 241,478.78 | 239,885.04 | -0.66% | +0.000001 → +0.000044 |

<!-- /paired-table -->

The smallest passing tested Q=16 clock period remains 4 ns. The 3 ns result is
still a setup failure, so this experiment does not establish a higher passing
frequency. Small positive slack is not implementation margin. No pipeline stage,
storage, or extra latency was introduced.

The area benefit is configuration-dependent: 1.76% at Q=16/5 ns, 3.93% at
Q=16/4 ns, 2.67% at the failing Q=16/3 ns point, and 0.66% at Q=32/5 ns.
Q16→Q32 still costs approximately three times the area. At Q=16/4 ns the positive
setup slack decreases slightly, while the 3 ns violation improves from −0.375142
to −0.166662 ns. The result supports an area improvement with preserved behavior,
not uniformly better timing or a solution to queue-scaling cost.

Hold violations and inherited zero-limit max-capacitance violations remain. The
reports retain both; no limits were relaxed or waived. These are pre-layout cell
areas with ideal clocks and no extracted interconnect. Power was not measured;
there is no post-layout or timing-signoff claim.

## Correctness and preserved behavior

- `make lint test`: 42 integrated directed/workload/reset/corner simulations,
  plus model legality/negative tests and scheduler/response unit checks.
- `make regress SEEDS=100 N=10000 JOBS=4`: 300 passing runs and 3,003,000 accepted
  transactions, including directed preludes.
- `make formal`: all five existing tasks pass. Three are depth-12 controller
  BMC checks; bank and reduced-control progress are unbounded proofs.
- `make formal-scheduler`: eight Yosys SAT equivalence configurations,
  Q=1/3/16/32 with aging off/on and default address/age parameters. All matched
  internal and output equivalence cells are proved. The unchanged synchronous
  reset establishes common state; this check is not a proof of arbitrary
  queue depths or unknown/out-of-range interface indices.
- The separate reset-based miter proves equivalence at Q=1/3/16, aging off/on,
  four-bit addresses and age limit three. Only slot-index range is assumed;
  ordering and candidate consistency are otherwise symbolic. Protection-slot
  equality is required when protection is active.
- `make compare-scheduler`: 120 old/new pairs (240 simulations) produce identical
  complete event CSVs, covering all three policies, ten workloads, seeds 1/42,
  and ready 100%/30%. Each run has 500 workload requests plus ten directed requests:
  122,400 accepted transactions across both revisions. This demonstrates preserved
  cycle-level behavior on these stimuli, rather than a new throughput improvement.
- A negative control inverted the ready-column preference condition. The
  equivalence checker rejected it with three unproved candidate-mask bits.

The complete Q=32 reset-miter PDR experiment was stopped after proving too slow;
Q=32 evidence uses the successful matched-signal SAT checks above. Small non-power-
of-two configurations use SMT/Z3 because ABC's AIG export rejected undefined
out-of-range array reads. An initial induction check of an inactive protection
slot was inconclusive; the final miter checks the valid-qualified interface.
These exploratory outcomes are not counted as passing proofs.

## Reproduction

This experiment is frozen at commit `27f522c`. Check out that revision to reproduce
the complete paired results and source checks below. Later address-sharing changes
have a [separate experiment](address-sharing-optimization.md); replacing only the
scheduler in a later controller does not reconstruct the v1.1 full-controller baseline.

```sh
make lint test
make regress SEEDS=100 N=10000 JOBS=4
make formal
make formal-scheduler
make compare-scheduler
# With SymbiYosys installed (or use the local .tools/sby/sbysrc/sby.py):
sby -f -j 2 --prefix build/scheduler_opt/equiv_final formal/scheduler_equiv.sby
```

For ASIC reproduction, create two isolated copies of the controller-only lab
bundle, using the same authorized site configuration. In the baseline copy,
replace only the scheduler with the v1.1 reference; `baseline_source()` in
`scripts/scheduler_equiv.py` returns the original module after checking its fixed
SHA-256. In each copy, run the four matched points:

```sh
python3 scripts/synth.py dc --lab --policy frfcfs_aging --point 16 5
python3 scripts/synth.py dc --lab --policy frfcfs_aging --point 16 4
python3 scripts/synth.py dc --lab --policy frfcfs_aging --point 16 3
python3 scripts/synth.py dc --lab --policy frfcfs_aging --point 32 5
```

Raw synthesis artifacts for this experiment reside under
`build/scheduler_opt/dc/{baseline,decode_trial}/q{Q}_{NS}ns/`. With those artifacts
and the verification outputs present, `python3 scripts/scheduler_optimization_report.py`
rebuilds the public evidence, verifies source/flow hashes and fresh baseline
reproduction, and checks that retained regression runs used the current RTL.
The collector also reads the retained experiment manifests `baseline.json`,
`lab_session.json` (for the library hash), and `mutation.json` in that local
directory. These contain run provenance and are not part of the public artifact.

- [Paired metrics CSV](../../results/scheduler_optimization/summary.csv)
- [Metrics, verification scope and source hashes](../../results/scheduler_optimization/summary.json)
- [Selected mapped reports](../../results/scheduler_optimization/reports/)

Published report copies replace the private library path with `${TECH_LIBRARY_DIR}`;
both raw and sanitized report hashes are recorded. Licensed libraries, full tool
transcripts, netlists, SSH details, and engineering notes remain local.
