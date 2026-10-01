# Shared address-comparison optimization

The controller computes one address-equality matrix in `mc_top` and shares it
between command dependency filtering and response arbitration. Relative to the
[candidate-decode revision](scheduler-optimization.md), full-controller mapped
area decreases by **16.71% at Q=16/5 ns**, **16.49% at Q=16/4 ns**, and
**24.19% at Q=32/5 ns**. Host timing, scheduling policy and storage are unchanged.
The failing 3 ns point becomes slightly slower; this is an area improvement,
not evidence of a higher achievable frequency.

## Design decision

Previously `mc_candidates` and `mc_response` each compared every pair of slot
addresses inside their dependency loops. These comparisons occurred in separate
synthesis modules. The new top-level matrix explicitly shares the comparison:

```text
same_address[i,j] = (address[i] == address[j])
command_blocked[i] = OR_j(pending[j]  AND older[j,i] AND same_address[j,i])
response_blocked[i] = OR_j(occupied[j] AND older[j,i] AND same_address[j,i])
```

Only one comparator per unordered pair is instantiated: the opposite triangle
is wired to it, and the diagonal is constant one. Q=16 has 120 unordered pairs;
Q=32 has 496. The matrix is combinational, not an array of new registers.
`mc_candidates` retains the original addresses for bank and row decoding;
`mc_response` now receives the equality matrix instead of addresses.

The two dependency lifetimes remain distinct. A predecessor stops blocking
command issue after its column command, but it continues blocking same-address
responses until the host consumes it. Sharing a pending-qualified dependency
mask with the response block would violate this rule. Full raw equality is the
shared input; each consumer retains its own qualification and arbitration.

A preceding attempt to share per-bank oldest-selection logic reduced generic
Yosys cells but increased mapped Q=16 area from 79,548.69 to 79,580.61 µm² at 5 ns
and from 80,695.19 to 81,217.06 µm² at 4 ns. It was discarded. The selected change
reduced the initial full-controller generic screening count from 29,260 to 25,684;
only mapped measurements below establish the ASIC benefit.

## Matched mapped measurements

All points use FR-FCFS with aging, DC R-2020.09-SP4, GSCL45nm typical at
1.1 V/27°C, identical SDC and DRAM timing parameters, and
`compile -map_effort medium`. The source manifest, Tcl, constraints, library and
site-config hashes are checked. The four new points ran in isolated workspaces.

The baseline is commit `27f522c408ac2c2028f486dca4d0d0e5d86d1b4c`.
Its four completed `decode_trial` runs are **reused from the preceding experiment**,
not rerun here. Their exact RTL and raw report hashes are checked against the
published first-round artifact. Only `mc_top`, `mc_candidates`, and `mc_response`
change in synthesis. Reports for the frozen v1.1 sweep remain untouched.

<!-- paired-table -->

| Q | Clock target (ns) | Area before (µm²) | Area after (µm²) | Area change | Worst setup slack before → after (ns) |
|---:|---:|---:|---:|---:|---:|
| 16 | 5 | 79,548.69 | 66,252.96 | -16.71% | +0.012058 → +0.010557 |
| 16 | 4 | 80,695.19 | 67,387.25 | -16.49% | +0.000458 → +0.000694 |
| 16 | 3 | 87,867.98 | 72,879.47 | -17.06% | -0.166662 → -0.201311 |
| 32 | 5 | 239,885.04 | 181,855.15 | -24.19% | +0.000044 → +0.000031 |

<!-- /paired-table -->

At Q=16/5 ns, `mc_candidates` area falls from 23,536.80 to 10,380.45 µm² and
`mc_response` from 17,615.64 to 4,402.03 µm². Some logic has moved into the top,
so those block reductions must not be added and presented as the overall saving.
The complete controller falls from 79,548.69 to 66,252.96 µm². Mapped sequential
cell count is unchanged at 1,974 for this point; all matched points retain their
respective sequential cell counts.

At Q=16 the smallest setup-passing **tested** target remains 4 ns (250 MHz).
At 3 ns setup slack worsens from −0.166662 to −0.201311 ns even as area decreases
17.06%. The 5 ns setup slack also decreases slightly, and Q=32/5 ns has only
0.000031 ns positive slack. These results do not establish robust timing margin
or exact Fmax. The Q16→Q32 area ratio at 5 ns falls from 3.02× to 2.74×;
quadratic pairwise comparisons and the older-than matrix still remain.

At 3 ns the worst path still begins at a transaction-table address register and
ends at `cmd_wdata` after dependency filtering, candidate selection, arbitration
and command output selection. Sharing the address comparisons removes repeated
logic but does not shorten that complete decision chain. Any subsequent timing
optimization should be measured against this path and preserve command legality.

Hold slack remains negative: Q16/5 and Q16/4 are −0.002538 ns, Q16/3 is
−0.006960 ns, and Q32/5 is −0.000833 ns. Inherited zero-limit max-capacitance
violations remain and are reported without waivers. These are pre-layout cell
areas with ideal clocks, not post-route area/timing, power measurements or signoff.

## Correctness evidence

- `make lint test`: 42 integrated directed/workload/reset/corner simulations,
  plus model legality/negative tests and scheduler/response unit checks.
- `make regress SEEDS=100 N=10000 JOBS=4`: 300 runs, 3,003,000 accepted transactions.
- `make formal`: the existing three depth-12 controller BMC checks and two reduced
  unbounded bank/progress proofs pass using the final source files.
- `make formal-address`: whole-controller matched-signal SAT equivalence at
  Q=1/3/16/32 for all three policies, using default address/data/age parameters.
  The original three modified modules are frozen with SHA-256 checks; the other
  four modules are identical on both sides. Flattening checks the real matrix
  wiring. `memory_map` exposes state, and `opt_merge` merges identical cells before
  `equiv_simple -undef -short`. Every remaining equivalence cell must be proved.
  Corresponding state has the same synchronous reset. This is equivalence via
  matched internal nodes, not a new unbounded proof of arbitrary controller
  functionality, arbitrary parameters, or unconstrained initial state.
- `make compare-address`: 120 pairs (240 simulations), with byte-identical complete
  event CSVs at Q=16 for three policies, ten workloads, seeds 1/42 and ready 100%/30%.
  Each simulation accepts 500 workload requests plus ten directed requests:
  122,400 transactions across both revisions. The unchanged traces support
  preserved cycle behavior on these stimuli; no throughput gain is claimed.
- An isolated Q=3 negative control forces slot pair {0,1} unequal. The same
  equivalence checker rejects it with four unproved command/response eligibility
  bits. The mutation is never used for synthesis or retained in production RTL.

The initial whole-controller proof without `memory_map` left bank-timer nodes
unproved. After mapping memories, Q=1/3/16 passed but an exploratory Q=32 run
without cell merging timed out at 300 seconds. Neither incomplete attempt is
counted as a proof; the final runner uses the procedure described above.
CI runs the six Q=1/3 checks across all policies; the full twelve configurations
are available through `make formal-address`.

## Reproduction and artifacts

```sh
make lint test
make regress SEEDS=100 N=10000 JOBS=4
make formal
make formal-address
make compare-address
```

For ASIC reproduction, use two isolated controller-only lab bundles with the
same authorized library/configuration. `baseline_sources()` in
`scripts/address_equiv.py` returns the three original RTL files after checking
their hashes; replace those three files in the baseline bundle. Keep the four
other files identical. Run each configuration in both bundles:

```sh
python3 scripts/synth.py dc --lab --policy frfcfs_aging --point 16 5
python3 scripts/synth.py dc --lab --policy frfcfs_aging --point 16 4
python3 scripts/synth.py dc --lab --policy frfcfs_aging --point 16 3
python3 scripts/synth.py dc --lab --policy frfcfs_aging --point 32 5
```

`python3 scripts/address_optimization_report.py` collects retained local runs from
`build/address_opt/dc/`, the reused `build/scheduler_opt/dc/decode_trial/` baseline,
verification outputs and experiment manifests (`baseline.json`, `lab_session.json`,
`mutation.json`). It refuses source, flow or verification mismatches. Raw tool
transcripts, netlists, site configuration and engineering notes stay local.

- [Metrics CSV](../results/address_sharing/summary.csv)
- [Source hashes, verification scope and complete metrics](../results/address_sharing/summary.json)
- [Selected mapped reports](../results/address_sharing/reports/)

Public report copies redact the private technology-library path and strip trailing
whitespace. Both raw and public hashes are retained. Baseline reports are linked
to the first-round artifact instead of duplicated.
