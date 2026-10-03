# Increase mapped setup margin without reopening hold failures

**Result:** Q16 FR-FCFS+aging setup margin increases from **0.038 to 50.054 ps
at 3 ns**, and **1.984 to 55.773 ps at 4 ns**. Setup and hold violations remain
zero under the original constraints. Area increases **0.77348% / 0.03285%**
relative to the independently retained hold-repaired mappings; capacitance and
transition violation counts do not increase. Both mapped comparisons and their
negative controls pass the acceptance checks. RTL is unchanged.

## Paired measurements

| Q16 FR-FCFS+aging | 3 ns hold-repaired baseline | 3 ns improved | 4 ns hold-repaired baseline | 4 ns improved |
|---|---:|---:|---:|---:|
| Area (µm²) | 70,381.388764 | **70,925.776764** | 65,714.200315 | **65,735.788116** |
| Worst setup slack (ns) | +0.000038 | **+0.050054** | +0.001984 | **+0.055773** |
| Register-to-register setup slack (ns) | +0.000186 | **+0.074053** | +0.001984 | **+0.068570** |
| Worst hold slack (ns) | +0.008031 | **+0.008031** | +0.008031 | **+0.008031** |
| Setup / hold violations | 0 / 0 | **0 / 0** | 0 / 0 | **0 / 0** |
| Sequential cells | 1,974 | 1,974 | 1,974 | 1,974 |
| Buffer cells | 943 | 970 | 837 | 837 |
| Zero-limit capacitance violations | 5,504 | 5,504 | 5,334 | 5,334 |
| Transition violations / unconstrained endpoints | 0 / 0 | 0 / 0 | 0 / 0 | 0 / 0 |

The [summary](../../results/setup_margin/summary.json) retains baseline DDC,
RTL, library, configuration, flow, report, cell-model and checker hashes.
Paired [3 ns reports](../../results/setup_margin/reports/q16_3ns/) and
[4 ns reports](../../results/setup_margin/reports/q16_4ns/) include the complete
violation lists and before/after exported SDCs. The worst 3 ns setup path remains
register-to-output: `table_i/addresses_reg_77_` to `cmd_wdata[11]`.
Each clock point uses its own mapped baseline and optimized netlist.

## Hypothesis, screen and adopted flow

The [hold repair](hold-repair-experiment.md) solved minimum-delay failures but
left a 0.038 ps setup margin at 3 ns. Before experimenting, the adoption screen
required at least **20 ps at 3 ns**, no worse setup at 4 ns, zero setup/hold
failures, at most 5% area increase at each point, no additional capacitance or
transition violations, no unconstrained endpoints, identical final SDC commands,
and mapped functional equivalence. These criteria were not relaxed after trials.

The hypothesis was that incremental gate mapping against an extra 50 ps setup
guard could produce useful margin when measured again under the original SDC.
Exploratory screens showed why optimizing delay alone was insufficient:

| 3 ns exploratory screen | Setup margin (ps) | Capacitance violations | Decision |
|---|---:|---:|---|
| Unrestricted incremental mapping | 50.030 | 5,630 | Reject: 126 more capacitance violations; this pilot also had an internal-path report-query diagnostic |
| Size-only mapping | 6.769 | 5,504 | Reject: below the predeclared 20 ps minimum |
| Preserve existing NAND2, exclude new NAND2 | 50.001 | 5,561 | Reject: 57 more capacitance violations |

These pilots were screened before functional proof and are **not adopted
mappings**. Their [frozen metrics and raw report hashes](../../results/setup_margin/screened_trials.json)
identify the retained private runs. A separate trial excluding NAND2 without
protecting existing instances was stopped during broad remapping; it has no
final PPA claim.

The adopted [DC script](../../synth/dc/improve_setup_margin.tcl), executed on
2026-10-03 with DC R-2020.09-SP4, performs the following:

1. Load the exact retained hold-repaired DDC and matching GSCL45nm typical DB;
   reproduce its before measurements and saved 0.1 ns clock uncertainty.
2. Confirm that AOI21X1, AOI22X1, NAND2X1, NAND3X1 and NOR2X1 have zero output
   `max_capacitance` in the loaded DB. Preserve their existing instances with
   temporary `dont_touch`, and exclude these references with temporary `dont_use`.
3. Increase **setup** uncertainty from 0.1 to 0.15 ns while leaving hold
   uncertainty at 0.1 ns. Run `compile -incremental_mapping -map_effort high
   -no_design_rule`.
4. Restore library/cell attributes and the original common 0.1 ns uncertainty;
   run `set_fix_hold core_clk` and `compile -only_hold_time`.
5. Assess all final timing and design-rule constraints, area and equivalence.

The installed Synopsys command documentation was inspected for incremental
mapping and attribute behavior; the [R-2020.09 User Guide](https://studylib.net/doc/28208562/design-compiler-user-guide)
describes incremental optimization of a mapped design. Excluding a reference
also remaps existing instances unless they are protected, which motivated the
combined preservation/exclusion step.

No numerical library limit is edited or waived. Skipping design-rule fixing
during optimization does not remove those constraints from final assessment:
the full final reports still contain all 5,504 / 5,334 inherited zero-limit
capacitance violations. Exported final SDC commands match the corresponding
before commands, excluding comments. There is no retiming, new state or added
pipeline latency.

## Complete state, clock and output comparison

Incremental mapping reuses numbered combinational instance names for different
logic, so name-matched intermediate wires are unsuitable proof assumptions.
The [checker](../../scripts/setup_margin_check.py) instead identifies all
**1,974 physical DFFPOSX1 instances**, requires matching before/after identities
and FF semantics, and constructs a combinational model for each netlist:

- Each corresponding FF Q becomes the same symbolic state input.
- Every FF D and CLK becomes a comparison output; all original I/O is retained.
- The flattened cell models must account for every physical FF, with matching
  D/CLK connections. Exported AIGs must contain zero latches and identical port maps.

ABC CEC proves all **4,042 output bits** (1,974 D, 1,974 CLK, 94 original outputs)
for all **2,068 input bits** (1,974 state Q, 94 original inputs) at each clock
point. Matching initial/reset state and identical positive-edge FF semantics
establish corresponding state transitions. This is a functional proof of the
mapped change; it does not assert analog clock behavior or timing equivalence.
The proof uses the associated GSCL45nm Liberty models, Yosys 0.68+post and ABC
1.01; their versions and model/netlist/AIG/map hashes are recorded.

At each point, a negative control replaces one INVX1 with BUFX2. ABC produces a
genuine non-equivalence counterexample at `state_d_0382` and the checker requires
rejection, rather than treating timeout or incomplete proof as success. See the
[3 ns proof status and port maps](../../results/setup_margin/checks/q16_3ns/) and
[4 ns proof status and port maps](../../results/setup_margin/checks/q16_4ns/).
Existing [300-run RTL verification](../../results/parallel_arbitration/validation_summary.json)
remains applicable by unchanged source hashes; no new 300-run result is claimed.

## Reproduction

`make check-evidence` audits committed hashes, paired measurements, original
constraints, acceptance conditions, model coverage and recorded proof status.
It requires only Python/Git and does not rerun synthesis or equivalence.

New mapping requires the matching private DB, lab configuration and retained
hold-repaired DDC; none of those licensed inputs or mapped netlists are
redistributed. From the repository root on the lab server:

```sh
# Example: the independently hold-repaired 3 ns mapping.
export MC_LAB_CONFIG=/path/to/matching/lab_config.tcl
export MC_MAPPED_DDC=/path/to/hold_repair/after.ddc
export MC_ANALYSIS_TOP=mc_top_Q_DEPTH16_SCHED_POLICY1_AGING_ENABLE1
export MC_ANALYSIS_OUT=/path/to/new/setup_margin_output
export MC_SETUP_GUARD_NS=0.05
export MC_SETUP_MODE=preserve_zero_caps
dc_shell -f synth/dc/improve_setup_margin.tcl
```

The output directory must be new. Repeat independently with the 4 ns baseline
and another new output directory. `SUCCESS` means tool-flow completion only.
With paired mapped Verilog and the associated Liberty models available:

```sh
python3 scripts/setup_margin_check.py \
  --before /path/to/setup_margin_output/before.v \
  --after /path/to/setup_margin_output/after.v \
  --liberty /path/to/gscl45nm.lib \
  --top mc_top_Q_DEPTH16_SCHED_POLICY1_AGING_ENABLE1 \
  --out build/new_setup_equivalence
```

The checker requires `yosys` and `yosys-abc` on PATH (or `--abc`), and always
runs the negative control. The collector `scripts/setup_margin_report.py`
consumes retained paired runs, provenance and final checker summaries in
`build/setup_margin/preserve_zero_caps_50ps/`; its public destination must be new.
It verifies the predeclared criteria and provenance before publishing selected
reports. It does not generate the private synthesis inputs or run DC.

## Remaining boundary

The extra setup margin is measured for **two Q16 FR-FCFS+aging, ideal-clock,
GSCL45nm typical (1.1 V, 27°C), pre-layout mappings**. It does not resolve the
inherited library capacitance issue or establish physical/multicorner timing
closure. Next work is to resolve those library/implementation constraints with
a suitable characterized library and evaluate timing after physical
implementation and across corners.
