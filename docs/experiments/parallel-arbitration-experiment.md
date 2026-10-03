# Parallel command-class arbitration experiment

<!-- decision -->
**Adopted.** Parallel column/PRE-ACT arbitration changes Q16/3 ns setup slack
from **−0.068773 to +0.000038 ns**, removing all 50 failing setup endpoints and
reducing mapped area by **1.89%**. Q16/4 ns setup margin increases to +0.001984 ns
with **0.44% less area**. Every predeclared adoption criterion passes.

The 3 ns setup margin is only **0.038 ps**. Hold still fails at both targets,
with eight endpoints at 3 ns and two at 4 ns. This is a measured pre-layout
setup pass, not full timing closure. Production RTL matches the measured trial
byte for byte.
<!-- /decision -->

## Hypothesis and implementation

The [selected command-path analysis](command-path-3ns.md) found two nearly
equally critical command-output path families. Their bank-candidate and
scheduler stages account for roughly 71–74% of total arrival time. Improving
only the high-fanout mask would leave the other family violating.

This trial changes only `mc_scheduler_frfcfs`. It computes oldest winners for
eligible column commands and eligible PRE/ACT commands in parallel, then
selects the command class. The baseline first selects a class and then
arbitrates its oldest request. The trial trades duplicated arbitration logic
for a shorter dependency through the class-presence decision; synthesis must
establish whether this improves the mapped controller.

Class selection uses **`columns != 0`**, even if the column winner vector is
empty. An arbitrary cyclic `older` matrix can have eligible columns without
any oldest winner. Selecting PRE/ACT in that case would change the reference
function. Highest-slot tie priority, invalid-command slot-zero payload,
encoded slot state updates, aging qualification and owner-service override
are retained. No state, pipeline stage, interface or cycle latency is added.

## Verification

Nine whole-controller matched-node SAT equivalence checks pass: Q=1/3/16
crossed with Strict-FCFS, FR-FCFS and FR-FCFS+aging. Every check has zero
unproven cells. The gold design is checkpoint
`9d40e165e8b071bbe20c01e16d8a12e20b6a8bbc`; all unchanged module hashes must match.
The changed scan temporary is renamed because its intermediate meaning differs
from the reference. The proof retains the existing flatten/memory-map and
matched-node partitioning scope; it is not presented as a new monolithic
unbounded end-to-end proof.

A Q3 FR-FCFS negative control changes the class selector to
`column_winners != 0`. The checker rejects it with **three unproven cells**.
Verilator lint passes. Complete accepted-request/command/completion/response
event CSVs match for **120 pairs**, covering three policies, ten workloads,
two seeds and two response-ready rates: 240 simulations and 122,400 accepted
requests across both revisions. These finite traces supplement equivalence.

After adoption, lint and all **42** integrated workload/reset/parameter-corner
simulations pass, along with the DRAM-model negative tests and scheduler/response
unit checks. **300** regression runs pass with **3,003,000 accepted transactions**.
The three depth-12 controller BMC checks and two reduced unbounded bank/progress
proofs pass. All nine equivalence configurations are rerun on production RTL.
The 120 trace pairs are also rerun successfully through `make compare-parallel`.
Run manifests, formal source copies and binary-build hashes are checked against
the measured source and retained locally; the
[validation summary](../../results/parallel_arbitration/validation_summary.json)
records counts, hashes and proof scope. CI now checks the frozen selected
command-mask baseline against current RTL at Q=1/3 across all policies.

## Matched synthesis and adoption screen

Both trial points use fresh isolated DC mappings with FR-FCFS+aging, Q=16,
DC R-2020.09-SP4, `compile -map_effort medium`, and the same GSCL45nm typical
library at 1.1 V/27°C. RTL, configuration, library and flow hashes are checked.
The two baseline points are **reused** from the selected command-mask plus
storage experiment, not freshly rerun. Each clock target has its own mapping.
SDC, DRAM timing parameters and the 1,974 sequential cells are unchanged.

The screen was recorded before measurement in the command-path study:
strictly improve 3 ns WNS, do not worsen 3 ns TNS, retain zero internal setup
failures, pass 4 ns setup, do not worsen hold slack or endpoint count at either
target, and keep 4 ns area within 5% of baseline. All conditions must pass.

<!-- measurements -->
| Variant | Target (ns) | Area (µm²) | Setup slack (ns) | Setup TNS (ns) | Setup endpoints | Internal setup endpoints | Hold slack (ns) | Hold endpoints |
|---|---:|---:|---:|---:|---:|---:|---:|---:|
| selected_baseline | 3 | 71,720.770984 | −0.068773 | −3.396384 | 50 | 0 | −0.000661 | 8 |
| parallel_classes | 3 | 70,362.616764 | +0.000038 | 0.000000 | 0 | 0 | −0.000659 | 8 |
| selected_baseline | 4 | 65,996.718912 | +0.000109 | 0.000000 | 0 | 0 | −0.000659 | 2 |
| parallel_classes | 4 | 65,709.507315 | +0.001984 | 0.000000 | 0 | 0 | −0.000659 | 2 |
<!-- /measurements -->

The 3 ns worst setup path now launches from transaction-table address bit 175
and ends at `cmd_op[1]`. At 4 ns the worst path is internal, from occupancy bit 0
to address bit 191. The trial retains 5,504 max-capacitance violations at 3 ns
and 5,334 at 4 ns; the inherited library constraints are unchanged.

Read-only queries on the saved trial DDCs reproduce the setup/hold violation
sets without compiling or reapplying SDC. The worst **internal** 3 ns margin
is **+0.000186 ns**, from occupancy bit 0 to write-data bit 254. This is smaller
than the baseline's +0.002394 ns margin, although it satisfies the predeclared
zero-internal-failures criterion. At 4 ns the internal minimum is +0.001984 ns;
the query reports an equal-slack endpoint at write flag 11. The 4 ns
register-to-output minimum is +0.006386 ns. Different tied endpoints can be
reported after DDC reload/name changes; no physical significance is assigned
to their ordering. Query reports and DDC/configuration/source hashes are in the
[3 ns analysis](../../results/parallel_arbitration/analysis/q16_3ns/register_to_register.rpt)
and [summary](../../results/parallel_arbitration/summary.json).

The next implementation work should target hold repair and more setup margin
under the same constraints, followed by physical timing validation if a
suitable flow is available. This experiment does not waive hold or treat a
fractional-picosecond setup margin as robust closure.

These are pre-layout typical-corner measurements with ideal clocks. Hold and
inherited zero-limit max-capacitance violations remain visible, with no waiver.
The experiment does not establish routed timing, power, exact Fmax or signoff.

## Artifacts and reproduction

- [Summary, checks, source hashes and complete violation lists](../../results/parallel_arbitration/summary.json)
- [Experimental scheduler](../../results/parallel_arbitration/variant/rtl/mc_scheduler_frfcfs.sv)
- [Paired trace summary and build source hashes](../../results/parallel_arbitration/trace_summary.json)
- [3 ns timing](../../results/parallel_arbitration/reports/q16_3ns/timing.rpt) and
  [4 ns timing](../../results/parallel_arbitration/reports/q16_4ns/timing.rpt)

Using the hash-checked frozen scheduler reference and unchanged modules,
reconstruct a new isolated trial directory and run the nine equivalence
configurations (full Git history is not required):

```sh
python3 scripts/parallel_arbitration_check.py --prepare \
  --trial build/parallel_reproduction/trial --out build/parallel_reproduction
python3 scripts/parallel_arbitration_check.py --trace \
  --trial build/parallel_reproduction/trial --out build/parallel_reproduction
```

For current production RTL, use `make formal-parallel` and
`make compare-parallel`. The reconstruction option requires a new directory;
it refuses to overwrite an existing trial.

For DC, use the reconstructed RTL with the unchanged `scripts/synth.py`,
`synth/dc/run.tcl`, manifest and SDC, plus a matching licensed library
configuration. In separate workspaces run `scripts/synth.py dc --lab --policy
frfcfs_aging --point 16 3` and the corresponding `--point 16 4`. Licensed library
and mapped DDC files are not redistributed. The result collector
`scripts/parallel_arbitration_report.py` audits the original local experiment
folder, including equivalence, lint, negative-control and trace summaries,
and publishes sanitized reports with original/public hashes.
The additional margin queries use `synth/dc/analyze_arbitration_paths.tcl`
with the same four `MC_*` environment settings documented in the preceding
command-path analysis.
