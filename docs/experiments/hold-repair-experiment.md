# Mapped hold repair at 3 ns and 4 ns

This records the hold-only repair before the subsequent
[setup-margin experiment](setup-margin-experiment.md). Its paired numbers remain
frozen; the later mapping increases setup margin while preserving zero hold failures.

**Result:** the Q16 FR-FCFS+aging mappings now have **zero setup and hold
violations** at both tested clock periods. Hold-only Design Compiler repair
inserts eight buffers at 3 ns and two at 4 ns, preserves setup slack, and passes
mapped-netlist equivalence. RTL and timing constraints are unchanged.

## Paired measurements

| Q16 FR-FCFS+aging | 3 ns before | 3 ns repaired | 4 ns before | 4 ns repaired |
|---|---:|---:|---:|---:|
| Area (µm²) | 70,362.616764 | **70,381.388764** | 65,709.507315 | **65,714.200315** |
| Worst setup slack (ns) | +0.000038 | **+0.000038** | +0.001984 | **+0.001984** |
| Setup violations | 0 | **0** | 0 | **0** |
| Worst hold slack (ns) | −0.000659 | **+0.008031** | −0.000659 | **+0.008031** |
| Hold violations | 8 | **0** | 2 | **0** |
| Buffer cells | 935 | 943 | 835 | 837 |
| Sequential cells | 1,974 | 1,974 | 1,974 | 1,974 |
| Zero-limit capacitance violations | 5,504 | 5,504 | 5,334 | 5,334 |

The area increases are **0.02668% at 3 ns** and **0.00714% at 4 ns**.
The [machine-readable summary](../../results/hold_repair/summary.json) contains
source, DDC, library, configuration, flow, report and netlist hashes. Paired
reports are retained for [3 ns](../../results/hold_repair/reports/q16_3ns/)
and [4 ns](../../results/hold_repair/reports/q16_4ns/).

## Diagnosis and repair

The [parallel-arbitration experiment](parallel-arbitration-experiment.md)
removed setup violations but retained hold failures. All eight 3 ns hold failures
were short feedback paths in the bank tracker's tRAS/tRCD countdown registers.
The worst deficit was 0.659 ps. The 3 ns setup margin was only 0.038 ps, so any
repair also had to preserve the setup pass.

On 2026-10-03, each retained mapped DDC was loaded independently in Synopsys DC
R-2020.09-SP4 with its original GSCL45nm typical library (1.1 V, 27°C). Original
DDC/library/configuration/SDC hashes matched the prior experiment. Before reports
reproduced the published area, setup, hold and violation counts exactly.

The [repair script](../../synth/dc/repair_hold.tcl) sets `set_fix_hold core_clk`
and runs `compile -only_hold_time`. The installed command manual confirms that
this combination performs hold fixing and ignores other design-rule repair;
see the Synopsys [R-2020.09 User Guide](https://studylib.net/doc/28208562/design-compiler-user-guide).
Each run uses a new output directory and preserves the original DDC.

DC inserts BUFX2 cells on the failing register-input paths. The loaded DB reports
BUFX2's output function as `A` and cell area as 2.346500 µm². Eight/two added
buffers explain the respective 18.772000/4.693000 µm² area increases. The clock
period, uncertainty, I/O timing, loads, operating condition and path exceptions
remain unchanged: before/after exported SDC commands are identical, excluding
comments. The complete constraint reports and QoR counts agree that setup and
hold violations are zero. `check_timing` reports no unconstrained endpoints.

## Functional validation

The [mapped-netlist checker](../../scripts/hold_repair_check.py) loads the
associated GSCL45nm Liberty models from the same lab library installation,
flattens both netlists, and checks matched nodes including state and outputs.
All 20,106 equivalence cells at 3 ns and 19,962 at 4 ns are proven, with zero
unproven cells. Cell-model and paired netlist hashes are recorded. This check
compares the repaired netlist with the retained mapped baseline; existing
[source-matched RTL verification](../../results/parallel_arbitration/validation_summary.json)
remains the RTL evidence. No new RTL regression result is claimed.

A negative control replaces one newly inserted BUFX2 with INVX1 in each repaired
netlist. Both checks reject the mutation and leave the affected bank-counter
D-input equivalence cell unproven. See the retained proof-status excerpts for
[3 ns](../../results/hold_repair/checks/q16_3ns/) and
[4 ns](../../results/hold_repair/checks/q16_4ns/).

## Reproduction

`make check-evidence` checks committed measurements, report hashes, source
identity, SDC equality and recorded proof counts without licensed tools.

New execution requires the matching lab configuration, GSCL45nm DB/Liberty
models and mapped baseline. The library, mapped Verilog and DDCs remain private.
If the retained DDCs are unavailable, regenerate the parallel-arbitration
baseline with the frozen RTL and original synthesis flow before comparing a
repair; verify its before measurements and record its new provenance.

```sh
# On the lab server, from the repository root; example for the 3 ns mapping.
export MC_LAB_CONFIG=/path/to/matching/lab_config.tcl
export MC_MAPPED_DDC=/path/to/baseline/mapped.ddc
export MC_ANALYSIS_TOP=mc_top_Q_DEPTH16_SCHED_POLICY1_AGING_ENABLE1
export MC_ANALYSIS_OUT=/path/to/new/hold_repair_output
dc_shell -f synth/dc/repair_hold.tcl
```

The output directory must not already exist. The DDC supplies its saved
constraints; the script does not reload or relax the SDC. It writes before/after
reports, SDC, mapped Verilog and DDC snapshots. `SUCCESS` records tool-flow
completion; inspect timing and prove equivalence before adopting the mapping.
Repeat independently with the 4 ns baseline and a second new destination.

```sh
# With the paired mapped netlists and associated lab Liberty file available.
python3 scripts/hold_repair_check.py \
  --before /path/to/hold_repair_output/before.v \
  --after /path/to/hold_repair_output/after.v \
  --liberty /path/to/gscl45nm.lib \
  --top mc_top_Q_DEPTH16_SCHED_POLICY1_AGING_ENABLE1 \
  --out build/new_hold_equivalence --negative-control
```

The published collector, `scripts/hold_repair_report.py`, consumes retained
paired runs, provenance and checker summaries in `build/hold_repair/final/`.
Its output must be new. It validates exact retained baseline identity and all
acceptance conditions before publishing selected reports. It is a report
collector, not a replacement for running licensed synthesis.

## Limits and next work

This resolves the measured hold failures for **two Q16, FR-FCFS+aging,
ideal-clock, typical-corner pre-layout mappings**. Immediately after this hold-only
repair, the 3 ns setup margin was only **0.038 ps**; the subsequent
[setup-margin experiment](setup-margin-experiment.md) raises it to 50.054 ps.
Inherited zero-limit capacitance violations remain unchanged;
this experiment does not waive or repair them. Resolving the
library/implementation capacitance issue and evaluating timing
across corners and physical implementation remain separate engineering work.
This is not physical timing signoff or an all-configuration timing claim.
