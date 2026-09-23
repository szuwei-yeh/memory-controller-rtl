# UCSB Design Compiler baseline — frozen v1.1

## Verified environment and provenance

Private account, SSH host, installation paths, and license configuration are
redacted from the public evidence. Obtain the authorized site's setup from its
administrator; source that setup so `dc_shell` and its license are available.
No module load was needed in the measured session. The measured tool was
**Design Compiler R-2020.09-SP4, linux64, build Mar 02, 2021**; the runner used
Python 3.11 because the host default was Python 3.6.8.

Paths below are placeholders, not a distributed technology library. Set
`TECH_LIBRARY_DIR` privately to the directory containing the verified database.
For Tcl configuration, use `$env(TECH_LIBRARY_DIR)` to expand that environment
variable. The library name, corner, checksums, and all measured values are retained.

Two previously successful project flows were found under `${PROJECT_HOME}`:

| Project / evidence | Actual library | Flow |
|---|---|---|
| `flashattn-accelerator/syn/scripts/dc_run.tcl`; completed run `syn/runs/2026-09-03_registered_scale_d16/core/manifest.txt` and `reports/timing_setup.rpt` | `${TECH_LIBRARY_DIR}/gscl45nm.db` | `target_library = [list $TARGET_DB]`; `link_library = [concat "*" $target_library]`; `compile` |
| `work/mac-accel-cdc/syn/dc_baseline.tcl`; completed run `syn/runs/mac_dma_rob_mo8_clock_sweep_5ns_20260905/manifest.txt`, `dc.log`, and timing report | `${LEGACY_LIBRARY_DIR}/osu018_stdcells.db` | `target_library = [list $TARGET_LIB]`; `link_library = [list * $TARGET_LIB]`; `compile_ultra` |

This baseline reuses the **FlashAttention 45 nm library**, not a mixture of the two
technologies. Its internal library name is `gscl45nm`; the selected operating
condition is **typical**, process factor **1**, supply **1.1 V**, temperature **27°C**.
The companion `gscl45nm.lib` specifies `time_unit = 1ns` and capacitance `1 pF`;
loaded `.db` attributes and the design report provide an independent runtime check.
The initial `report_lib` probe failed with LCSH-3 because Library Compiler could not
be launched; this does not prevent DC from reading and mapping against the `.db`.

## Exact configuration and constraints

The server-only `synth/lab_config.tcl` contains:

```tcl
set TARGET_LIBRARIES [list "$env(TECH_LIBRARY_DIR)/gscl45nm.db"]
set TARGET_LIBRARY_NAMES [list gscl45nm]
set LIB_SEARCH_PATH [list $env(TECH_LIBRARY_DIR)]
set LIB_CORNER "gscl45nm typical; process=1; voltage=1.1V; temperature=27C"
set OPERATING_CONDITION typical
set LIB_TIME_NS 1.0
set LIB_CAP_FF 1000.0
```

DC receives the target list above and link list `*` followed by that same `.db`.
The existing DC search path is extended with that library directory.

Only the seven controller SystemVerilog files in `synth/rtl_files.f` are analyzed,
with `SYNTHESIS` defined. Elaboration starts at `mc_top` with Q=16, FR-FCFS and aging
enabled; the specialized top is `mc_top_Q_DEPTH16_SCHED_POLICY1_AGING_ENABLE1`.
Rows=256, columns=64, data=32 bits, read latency=3 and all timing/aging parameters
retain the frozen defaults. The compile command is `compile -map_effort medium`;
there is no retiming or additional RTL pipeline stage.

The unchanged `synth/constraints/controller.sdc` applies:

- Clock `core_clk`: **5 ns** (200 MHz target), ideal clock network.
- Clock uncertainty: **0.1 ns**.
- Every nonclock input, including synchronous reset: maximum/minimum delay **1/0 ns**.
- Every output: maximum/minimum delay **1/0 ns**.
- Input transition: **0.1 ns**.
- Output capacitance: **10 fF = 0.010 pF**.
- No false paths or multicycle exceptions. In particular, the older FlashAttention
  reset exception is not copied into this controller's synchronous-reset flow.

## Run location and reproduction

The original run used a private temporary workspace because the home filesystem
quota was exhausted. Exact account, host, and workspace identifiers are redacted.
Set `LAB_SSH_TARGET`, optional `LAB_SSH_CONTROL_PATH`, and `LAB_BASELINE_DIR`
privately before using the remote sweep helper. Never commit their values.

```sh
# Locally: an explicit allowlist excludes testbenches, models, formal, workloads,
# libraries and all local_notes content.
python3 scripts/lab_bundle.py
scp -o ControlPath=${LAB_SSH_CONTROL_PATH} build/lab_bundle.tar.gz \
  ${LAB_SSH_TARGET}:${LAB_BASELINE_DIR}/

# On redacted-lab-host, after extracting the bundle and creating the verified config:
cd ${LAB_BASELINE_DIR}
/usr/bin/python3.11 scripts/synth.py dc --lab --baseline --config synth/lab_config.tcl
```

The `--baseline` option runs only this one point, not the full clock/policy sweep.
`--lab` prevents creating a private notebook remotely. Runtime metadata records
hostname, controller hashes, flow/SDC/manifest hashes and the configuration hash.

The first two attempts stopped before mapping due to Tcl portability problems: the original
flow looked up an unspecialized top and invoked an unsupported `version` command;
the next attempt called `report_operating_conditions` without its required library
argument. The flow now retains the elaborated top, uses the tool startup banner
for version evidence, and records operating conditions through `report_design`.
A third attempt completed mapping but stopped at unsupported `check_timing -verbose`.
The flow now uses supported `check_timing` and saves a mapped DDC before diagnostics.
Failed runs are preserved locally under `build/ucsb_baseline/attempt1`, `attempt2`,
and `attempt3`.
These were flow-only corrections; controller RTL was not changed.

## Measured result

The final run completed successfully on September 22, 2026. **Setup meets the
5 ns target, but this is not a clean timing/DRC result.**

| Metric | Result |
|---|---:|
| Total mapped cell area | 80,975.366581 µm² |
| Combinational area | 65,226.597531 µm² |
| Sequential area | 15,748.769051 µm² |
| Leaf cells / sequential cells | 26,798 / 1,974 |
| Macros / black boxes | 0 |
| Worst setup slack | **+0.001615 ns** |
| Setup WNS / violating paths | 0 ns / 0 |
| Worst hold slack / violating endpoints | **−0.002538 ns / 14** |
| Max-capacitance violations | **5,556** |
| Max-transition violations | 0 |
| Unconstrained endpoints | None reported by `check_timing` |

WNS is zero when there is no negative setup slack; the actual worst slack is only
1.615 ps positive. This single point does not establish a maximum clock frequency.
Area is the sum of library cell areas. As a unit cross-check, `INVX1` has Liberty
area 1.4079 and LEF size 0.57 × 2.47 µm. DC reports total physical area as undefined:
there is **no wire-load model and no extracted interconnect**, and the clock network
is ideal. These are pre-layout estimates, not signoff timing or core area.

### Critical path

`table_i/addresses_reg[80]` → `candidates_i/hit[5]` →
`candidates_i/candidate_slots[0]` → `frfcfs.scheduler_i/select_slot[1]` →
`cmd_wdata[9]`.

The address's bank/row qualification feeds bank candidate selection, then global
FR-FCFS selection and the command write-data mux. The reported cumulative arrival
is 1.7380 ns at the bank candidate slot, 3.3503 ns at the global selected slot, and
3.898385 ns at the command output. Required arrival is 3.9000 ns, from the 5 ns
clock less 0.1 ns uncertainty and 1 ns output delay. This is the critical path for
this mapped design; it is not the host-response holding register.

### Remaining violations and warnings

- The 14 hold violations include `table_i/done_reg[0,4,5,6]` feedback paths at
  −0.002538 ns, plus smaller violations on other DONE registers and bank timers.
  Detailed hold reports were generated by reopening the saved DDC without compile.
- All 5,556 capacitance violations report a **0 pF allowed load**. For example,
  `candidates_i/n2557`, driven by `NAND2X1 U1845`, has 0.003852 pF actual load.
  A separate database query confirms `NAND2X1/Y max_capacitance=0`; the companion
  Liberty also explicitly contains zero. `INVX1/Y`, in contrast, reports 0.238796 pF.
  This requires review of the inherited library constraints before claiming a clean
  ASIC result. The library was not edited, substituted, or waived, and no RTL change
  was made in response.
- `VER-318`: 17 signed/unsigned conversion warnings during elaboration.
- Precompile checks: 38 `LINT-1` unused cells and 53 `LINT-2` unloaded nets.
- Postcompile `check_design`: 224 `LINT-28` unused scheduler address-port bits;
  the scheduler uses the bank bits, so the remaining address bits have no loads.
- `TIM-134`: clock fanout of 1,974 loads; DC reports using its high-fanout threshold
  of 1,000 for delay calculations. The SDC clock network remains ideal.
- Final synthesis and read-only inspection transcripts contain no `Error:` lines.
  `check_timing` reports no unconstrained endpoints, missing input delays, or loops.

No controller change is needed to report this baseline. Hold and inherited-library
capacitance limits remain unresolved; neither is silently treated as a pass.
No PrimeTime run or clock sweep was performed in the initial baseline task.
The subsequent [frozen 30-point comparison sweep](asic-results.md) is now complete;
its [report-only diagnostics](asic-diagnostics.md) classify all 14 baseline hold paths.

### Evidence

- [Machine-readable summary and source hashes](../results/dc_baseline/summary.json)
- [Mapped area](../results/dc_baseline/area.rpt)
- [Ten longest setup paths](../results/dc_baseline/timing.rpt) and
  [six-digit worst setup path](../results/dc_baseline/setup_precise.rpt)
- [Hold paths](../results/dc_baseline/hold.rpt) and
  [precise constraint violations](../results/dc_baseline/constraints_precise.rpt)
- [Timing checks](../results/dc_baseline/check_timing.rpt),
  [design checks](../results/dc_baseline/check_design.rpt), and
  [QoR](../results/dc_baseline/qor.rpt)
- [Applied SDC](../results/dc_baseline/mapped.sdc),
  [environment](../results/dc_baseline/environment.rpt), and
  [run metadata](../results/dc_baseline/run.json)

The full logs, mapped Verilog/DDC and failed attempts are retained locally under
`build/ucsb_baseline/`. `results/dc_baseline/inspect.tcl` reproduces the supplementary
reports from the mapped DDC when invoked from the remote run root. Report identifiers
in that second pass use the Verilog-normalized names saved by `change_names`.
The private Traditional Chinese notebook records each attempt and the final
interpretation locally; it was never part of any transfer.
